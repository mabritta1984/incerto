#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Equações display (`$$…$$`) dos documentos aprovados pelo PO → candidatos a `:Equacao` em staging — JSONL.

Lê `<raiz>/conferidos/<onda>/**/*.md` (o portão `conferir_onda.py --aprovar` os copia para lá), com a
mesma lista de documentos e o mesmo tópico do `recortar_trechos.py` (título `## `, ou o do `--nivel`; antes
do primeiro, o tópico "(abertura)"; título repetido desambiguado do mesmo jeito), para que `fonte:
{documento, topico}` cite sempre um trecho que existe. `manifesto.json`, `*.report.json`, `lote-*.md` e `*.assets/` não são
documentos e são pulados.

"Parseável" (decisão 2 do PO, 28/09) é estrito, porque um parse errado em silêncio é o pior desfecho:
  1. comando sem leitura algébrica honesta (`NAO_SUPORTADOS`: `\\Pr`, `\\mathrm{d}`, `\\forall`,
     `\\begin{aligned}`, …) é perda `nao_suportado:<cmd>` antes do parse;
  2. normalização: `\\tag`, `\\label`, `\\left`/`\\right`, tamanhos e espaçamentos saem; símbolo composto
     com marcação explícita vira um símbolo único (`T_{max}` → `T_max`, `f^{*}` → `f_star`,
     `\\mathit{TC}` → `TC`, `x_{1}` → `x_1`); `\\mathbb{E}[X]` e `E[X]` → `E(X)`; `\\operatorname{Var}(X)` →
     função `Var`. Sequência de letras sem marcação (`TC`) NÃO é normalizada: não há como saber se é `T·C`;
     também são perda, por ambíguas: expoente seguido de `_` ou `(` (`x^{2}_{i}`, `f^{-1}(x)`), letra
     seguida de `[` e decorações (`\\overline`, `\\hat`, …); e, porque o SymPy os lê errado com `ok`,
     símbolo com subscrito seguido de `^` (`C_n^k` → Pow(C_n, k): `_{…}^`; não os limites de `\\sum`,
     `\\prod`, `\\int`, `\\lim`, …), chaves de conjunto `\\{…\\}` (e
     `\\left\\{…\\right\\}`, lidas como `x`), `^{(…)}` (lido como potência) e `\\Delta` seguido de letra
     (`\\Delta x` lido como `Delta·x`);
  3. `sympy.parsing.latex.parse_latex(..., strict=True)`; erro é perda `strict`;
  4. conferência: todo símbolo e toda função do resultado têm de ser um token inteiro do LaTeX
     normalizado (`TC` lido como `T·C` é `simbolo_partido:TC`); símbolo com nome de comando LaTeX
     (`mathrm`, `dots`, …), relação encadeada (`a = b = c`) e função aplicada que não veio de marcação
     explícita (`p(1-p)`, `\\alpha(1-\\alpha)`, `g(x)`: `nao_suportado:p(`) também são perda — salvo o
     nome que o PO declarou função no documento (decisão `declarar_funcoes`, 05/10: `f(x)`, `F(x, λ)`,
     `\\gamma(x)`); nome declarado usado também como símbolo na mesma equação é `nao_suportado:uso_misto:<f>`.
Perda é ⚠️ com o LaTeX preservado como veio; nunca some.

Uso:
  python3 extrair_equacoes.py --raiz <corpus> --onda <onda> --saida _esteira/incerto/equacoes-<onda>.jsonl \
      [--nivel 2] [--decisoes _esteira/incerto/decisoes-<onda>.jsonl]
`--nivel` é o nível do título que define o tópico (default 2), o MESMO do `recortar_trechos.py` da onda: se
o manifesto do recorte (`trechos-<onda>.manifesto.json`, na pasta da `--saida`) existe e registra outro
`nivel`, a extração recusa (o tópico citado não seria o de trecho nenhum).
`--decisoes` (default: `decisoes-<onda>.jsonl` na pasta da `--saida`, lido só se existir; explícito e ausente
falha): das decisões do PO, só as `declarar_funcoes` contam aqui — cada documento é parseado com as funções
declaradas para ele. Declaração malformada, repetida ou de documento fora da onda recusa sem gravar.

Saída: um candidato por linha (`status: "staging"`, `nome` = `<documento>#<ordem>` até o PO renomear,
`latex`, `srepr`, `simbolos`, `variaveis`, `forma` — `algebrica` com `=`, `funcional` sem `=`, `perda` —,
`motivo`, `fonte: {documento, topico}`, `funcoes_declaradas` — as do documento, ordenadas, `[]` sem declaração),
documentos em ordem de bytes, sem timestamp. A saída nunca é
sobrescrita com conteúdo diferente (o PO edita os `nome`): reexecução idêntica não muda nada.
`sympy` só é importado dentro de função (decisão A6).
"""
import argparse
import io
import json
import os
import re
import sys

import recortar_trechos   # vizinho em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo

CORPUS = "incerto"

GREGAS = ("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi "
          "rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi "
          "Psi Omega").split()

# Perda declarada antes do parse: (regex no LaTeX de origem). O motivo é `nao_suportado:<o que casou>`.
NAO_SUPORTADOS = (
    r"\\Pr(?![A-Za-z])",
    r"\\mathrm\s*\{\s*d\s*\}",
    r"\\forall(?![A-Za-z])",
    r"\\begin\s*\{aligned\*?\}",
    r"\\begin\s*\{[^{}]*\}",                                  # qualquer outro ambiente (matrizes, casos, …)
    r"\\exists(?![A-Za-z])",
    r"\\(?:dots|cdots|ldots|vdots|ddots)(?![A-Za-z])",        # reticência: a fórmula não está inteira
    r"\\\\",                                                  # quebra de linha
    # decorações: o SymPy as lê como operações (`\overline{x}` → conjugate(x)) ou como símbolos falsos
    r"\\(?:overline|underline|widehat|widetilde|hat|bar|tilde|check|breve|dot|ddot|vec|acute|grave|mathring|"
    r"overrightarrow|overleftarrow|underbrace|overbrace)(?![A-Za-z])",
    # leituras erradas em silêncio (o parse dava ok): `\{x\}` (chaves de conjunto, parte fracionária) vira `x`;
    # `x^{(n)}` (potência ascendente, n-ésima derivada) vira `x**n`; `\Delta x` (incremento) vira `Delta*x`
    r"\\\{",
    r"\^\s*\{\s*\(",
    r"\\Delta(?=\s*(?:[A-Za-z]|\\(?:%s)(?![A-Za-z])))" % "|".join(GREGAS),
)
# símbolo com subscrito seguido de `^` (`C_n^k`, binomial; `x_{i}^{2}`): o SymPy lê Pow(C_n, k) — perda;
# o `_{…}^{…}` logo depois de um operador (`\sum_{i=1}^{n}`, `\int_{0}^{1}`) é limite dele, não subscrito
_SUBSCRITO_E_EXPOENTE = r"_\s*(?:\{[^{}]*\}|\\[A-Za-z]+|[A-Za-z0-9])\s*\^"
_OPERADOR_ANTES = re.compile(r"\\(?:sum|prod|int|oint|lim|max|min|sup|inf|bigcup|bigcap)"
                             r"(?:\s*\\(?:no)?limits)?\s*$")


def _subscrito_e_expoente(latex):
    """Há símbolo com subscrito seguido de `^` (e não limite de operador)?"""
    return any(not _OPERADOR_ANTES.search(latex[:m.start()]) for m in re.finditer(_SUBSCRITO_E_EXPOENTE, latex))
# Marcação que sobrou depois da normalização: o parser a leria como símbolo (`Symbol('mathrm')`).
RESIDUAIS = r"\\(?:mathbb|mathrm|mathit|mathbf|mathcal|mathsf|boldsymbol|operatorname|text|textrm|mbox)(?![A-Za-z])"
COMANDOS_COMO_SIMBOLO = frozenset(("mathbb", "mathrm", "mathit", "mathbf", "mathcal", "operatorname", "text",
                                   "tag", "label", "dots", "cdots", "ldots", "vdots", "left", "right"))
_GREGA = r"\\(?:%s)(?![A-Za-z])" % "|".join(GREGAS)
_BASE = r"(?:(?<![A-Za-z\\])[A-Za-z]|%s)" % _GREGA           # uma letra solta ou uma letra grega
_SEM_LEITURA = (
    (r"\\(?:tag|label)\s*\{[^{}]*\}", " "),
    (r"\\(?:nonumber|notag|displaystyle|textstyle|left|right)(?![A-Za-z])", " "),
    (r"\\[Bb]igg?[lr]?(?![A-Za-z])", " "),
    (r"\\(?:,|;|:|!|quad(?![A-Za-z])|qquad(?![A-Za-z]))", " "),
    (r"~", " "),
)
_MARCA = "\ue000%d\ue001"
_RE_MARCA = re.compile("\ue000(\\d+)\ue001")


def _bytes(s):
    return s.encode("utf-8")


def _nome_da_base(base):
    return base[1:] if base.startswith("\\") else base


def _fechamento(texto, i, abre, fecha):
    """Índice do `fecha` que fecha o `abre` em `texto[i]`, ou -1."""
    nivel = 0
    for j in range(i, len(texto)):
        if texto[j] == abre:
            nivel += 1
        elif texto[j] == fecha:
            nivel -= 1
            if nivel == 0:
                return j
    return -1


def _depois_do_expoente(t):
    """`_` ou `(` logo depois de um expoente (`^x`, `^\\cmd`, `^{…}`), ou None."""
    for m in re.finditer(r"\^\s*", t):
        i = m.end()
        if i >= len(t):
            continue
        if t[i] == "{":
            fim = _fechamento(t, i, "{", "}")
            if fim < 0:
                continue
            fim += 1
        elif t[i] == "\\":
            fim = i + len(re.match(r"\\(?:[A-Za-z]+|.)", t[i:]).group(0))
        else:
            fim = i + 1
        resto = t[fim:].lstrip()
        if resto[:1] in ("_", "("):
            return resto[0]
    return None


# operador de relação: o parse lê `a = b = c` como `Equality(Equality(a, b), c)` e o SymPy o colapsa em
# `true`/`false` quando decide (`1 = 2`, `p(x)dx = p(x)dx`): a cadeia tem de ser vista no LaTeX, antes do parse
_RELACAO = re.compile(r"[=<>]|\\(?:leq?|geq?|neq?|lt|gt|approx|equiv|sim|simeq|ll|gg|propto)(?![A-Za-z])")


def _relacoes_no_nivel_zero(t):
    """Quantos operadores de relação há fora de qualquer chave (`_{…}`, `^{…}`, `\\frac{…}{…}`)."""
    nivel, texto = 0, []
    for c in t:
        if c == "{":
            nivel += 1
        elif c == "}":
            nivel = max(nivel - 1, 0)
        elif nivel == 0:
            texto.append(c)
    return len(_RELACAO.findall("".join(texto)))


def _preparar(latex):
    """Devolve (texto com marcas, [(tipo, nome canônico)], motivo). Tipo `simbolo` (composto) ou `funcao`."""
    for padrao in NAO_SUPORTADOS:
        m = re.search(padrao, latex)
        if m:
            return None, [], "nao_suportado:%s" % re.sub(r"\s+", "", m.group(0))
    t = latex.replace("\r", " ").replace("\n", " ")
    for padrao, troca in _SEM_LEITURA:
        t = re.sub(padrao, troca, t)
    t = re.sub(r"\s+", " ", re.sub(r"[\s,.;]+$", "", t)).strip()
    marcas = []

    def marca(tipo, nome):
        if (tipo, nome) not in marcas:
            marcas.append((tipo, nome))
        return _MARCA % marcas.index((tipo, nome))

    # esperança e operadores nomeados viram aplicação de função; é a ÚNICA origem de função aceita (marca
    # `funcao`): letra solta seguida de `(` é produto ou aplicação, ambíguo, e vira perda depois do parse
    while True:
        m = re.search(r"(?:\\mathbb\s*\{\s*E\s*\}\s*([\[(])|(?<![A-Za-z\\])E\s*(\[))", t)
        if not m:
            break
        g = 1 if m.group(1) else 2
        fim = _fechamento(t, m.start(g), m.group(g), "]" if m.group(g) == "[" else ")")
        if fim < 0:
            break
        t = t[:m.start()] + marca("funcao", "E") + "(" + t[m.end(g):fim] + ")" + t[fim + 1:]
    t = re.sub(r"\\operatorname\s*\{\s*([A-Za-z]+)\s*\}\s*(?=\()", lambda m: marca("funcao", m.group(1)), t)
    # compostos com marcação explícita viram um símbolo único
    t = re.sub(r"(%s)\s*\^\s*(?:\{\s*(?:\*|\\ast|\\star)\s*\}|\*|\\ast(?![A-Za-z])|\\star(?![A-Za-z]))" % _BASE,
               lambda m: marca("simbolo", _nome_da_base(m.group(1)) + "_star"), t)
    t = re.sub(r"(%s)\s*_\s*\{\s*(?:\\(?:text|mathrm|mathit)\s*\{\s*([A-Za-z0-9]{2,})\s*\}|([A-Za-z0-9]{2,}))\s*\}"
               % _BASE, lambda m: marca("simbolo", _nome_da_base(m.group(1)) + "_" + (m.group(2) or m.group(3))), t)
    t = re.sub(r"\\mathit\s*\{\s*([A-Za-z]+)\s*\}", lambda m: marca("simbolo", m.group(1)), t)
    t = re.sub(r"_\s*\{\s*([A-Za-z0-9])\s*\}", r"_\1", t)
    for m in _RE_MARCA.finditer(t):
        tipo, nome = marcas[int(m.group(1))]
        if tipo == "simbolo" and re.match(r"\s*\(", t[m.end():]):
            return None, [], "nao_suportado:%s(…)" % nome     # produto ou aplicação? ambíguo
    m = re.search(r"(?<![A-Za-z\\])([A-Za-z])\s*\[", t)
    if m:
        return None, [], "nao_suportado:%s[" % m.group(1)      # `X[…]`: esperança sem marcação? produto?
    seguinte = _depois_do_expoente(t)
    if seguinte:
        # `x^{2}_{i}`: o SymPy descarta o subscrito; `f^{-1}(x)`: inversa lida como produto
        return None, [], "nao_suportado:^{…}%s" % seguinte
    if _subscrito_e_expoente(latex):
        return None, [], "nao_suportado:_{…}^"
    m = re.search(RESIDUAIS, _RE_MARCA.sub(" ", t))
    if m:
        return None, [], "nao_suportado:%s" % m.group(0)
    if _relacoes_no_nivel_zero(t) > 1:
        return None, [], "nao_suportado:relacao_encadeada"
    return t, marcas, None


def normalizar_latex(latex):
    """O LaTeX como o parse o lê, com os compostos já canônicos (`\\mathit{T_max}`, `\\mathit{f_star}`,
    `E(X)`, `\\operatorname{Var}(X)`). Com perda antes do parse, devolve o LaTeX de origem."""
    t, marcas, motivo = _preparar(latex)
    if motivo:
        return latex
    def escrita(m):
        tipo, nome = marcas[int(m.group(1))]
        return "\\mathit{%s}" % nome if tipo == "simbolo" else nome if len(nome) == 1 else "\\operatorname{%s}" % nome
    return _RE_MARCA.sub(escrita, t)


def _tokens(t, marcas):
    """Tokens inteiros do LaTeX normalizado: letras (com um subscrito simples) e os nomes canônicos."""
    s = _RE_MARCA.sub(" ", t)
    s = re.sub(_GREGA, lambda m: " " + m.group(0)[1:], s)
    s = re.sub(r"\\(?:[A-Za-z]+|.)", " ", s)
    return set(re.findall(r"[A-Za-z]+(?:_[A-Za-z0-9])?", s)) | {nome for _, nome in marcas}


def _livres(texto, proibidas):
    """Prefixo só de letras que não ocorre no texto (as marcas do parse não colidem com nada dele)."""
    for p in ("QZ", "QY", "QX", "ZQ", "YQ", "XQ"):
        if p not in texto and p not in proibidas:
            return p
    raise ValueError("sem prefixo livre para os símbolos compostos")


def _letras(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(ord("a") + r) + s
    return s


def _canonico(nome):
    m = re.fullmatch(r"(.+)_\{([A-Za-z0-9])\}", nome)
    return "%s_%s" % m.groups() if m else nome


def _perda(motivo):
    return {"ok": False, "srepr": None, "simbolos": [], "motivo": motivo}


def parsear_latex(latex, funcoes=frozenset()):
    """LaTeX → `{"ok", "srepr", "simbolos", "motivo"}` pela definição estrita de "parseável" (ver o topo).
    `funcoes`: nomes canônicos (`f`, `F`, `gamma`, `n_F`) que o PO declarou funções no documento (decisão
    `declarar_funcoes`); só esses viram aplicação de função — `p(1-p)` sem `p` declarada segue perda, e o nome
    declarado que também aparece como símbolo na equação é `nao_suportado:uso_misto:<nome>`.
    Falta do `sympy`/`antlr4` sobe como ImportError (o portão diz "não medido", o CLI falha alto); qualquer
    outro erro inesperado é perda declarada `erro:<tipo>`, nunca um `ok`."""
    try:
        return _parsear(latex, frozenset(funcoes))
    except ImportError:
        raise
    except Exception as e:
        return _perda("erro:%s" % type(e).__name__)


def _parsear(latex, funcoes):
    from sympy import Expr, Function, Max, Min, Symbol, srepr
    from sympy.core.function import AppliedUndef
    from sympy.core.relational import Relational
    from sympy.parsing.latex import parse_latex

    t, marcas, motivo = _preparar(latex)
    if motivo:
        return _perda(motivo)
    prefixo = _livres(t, "".join(nome for _, nome in marcas))
    funcoes_livres = [c for c in "QZWKJUV" if c not in t]
    para_parse, simbolos_de, funcoes_de = [], {}, {}
    pos = 0
    for m in _RE_MARCA.finditer(t):
        tipo, nome = marcas[int(m.group(1))]
        para_parse.append(t[pos:m.start()])
        if tipo == "simbolo":
            ph = prefixo + _letras(int(m.group(1)))
            simbolos_de[ph] = nome
            para_parse.append("\\mathit{%s}" % ph)
        else:
            if not funcoes_livres:
                return _perda("nao_suportado:\\operatorname{%s}" % nome)
            ph = [k for k, v in funcoes_de.items() if v == nome]
            ph = ph[0] if ph else funcoes_livres.pop(0)
            funcoes_de[ph] = nome
            para_parse.append(" %s" % ph)
        pos = m.end()
    para_parse.append(t[pos:])
    # subscrito simples sempre entre chaves para o parser: sem elas, `P_d \times A` vira `P_{dtimes}·A`
    para_parse = [re.sub(r"_([A-Za-z0-9])", r"_{\1}", p) for p in para_parse]
    try:
        expr = parse_latex("".join(para_parse), strict=True)
    except ImportError:
        raise                                   # antlr4 ausente ou de outra série: não é perda, é ambiente
    except Exception:
        return _perda("strict")

    # função aplicada só a que veio de marcação explícita (`\mathbb{E}[…]`, `E[…]`, `\operatorname{…}(…)`)
    # ou que o PO declarou função no documento (`funcoes`); `p(1-p)`, `\alpha(1-\alpha)`, `g(x)` seriam lidos
    # como função: ambíguo, perda declarada
    for f in sorted(expr.atoms(AppliedUndef), key=lambda f: _bytes(type(f).__name__)):
        nome = type(f).__name__
        if nome not in funcoes_de and nome not in ("max", "min") and _canonico(nome) not in funcoes:
            return _perda("nao_suportado:%s(" % _canonico(nome))
    # o nome declarado que a marcação explícita também produziu (`\mathbb{E}[X] + E(x)` com `E` declarada):
    # fundiria o operador com a função do PO; perda
    marcados = sorted(funcoes & set(funcoes_de.values()), key=_bytes)
    if marcados:
        return _perda("nao_suportado:funcao_de_marcacao:%s" % marcados[0])
    # o nome declarado função que aparece também como símbolo (`f(x) = x f`): qual das leituras vale? perda
    misto = sorted(funcoes & {simbolos_de.get(s.name, _canonico(s.name)) for s in expr.atoms(Symbol)}, key=_bytes)
    if misto:
        return _perda("nao_suportado:uso_misto:%s" % misto[0])

    troca = {}
    for s in expr.atoms(Symbol):
        novo = simbolos_de.get(s.name, _canonico(s.name))
        if novo != s.name:
            troca[s] = Symbol(novo)
    expr = expr.xreplace(troca)

    def funcao_nova(f):
        nome = type(f).__name__
        if nome in ("max", "min"):
            return (Max if nome == "max" else Min)(*f.args)
        return Function(funcoes_de.get(nome, _canonico(nome)))(*f.args)
    expr = expr.replace(lambda e: isinstance(e, AppliedUndef), funcao_nova)

    # só `Relational` ou `Expr` é uma equação: `true`/`false` (relação decidida pelo SymPy) e as funções
    # booleanas (`And`, …) são valor de verdade; um `srepr` `true`/`false` nunca é ok
    if not isinstance(expr, (Relational, Expr)):
        return _perda("nao_suportado:booleano")
    if any(isinstance(no, Relational) and any(isinstance(a, Relational) for a in no.args)
           for no in (expr,) + tuple(expr.atoms(Relational))):
        return _perda("nao_suportado:relacao_encadeada")        # rede de segurança: o pré-parse já a recusa
    nomes = {s.name for s in expr.atoms(Symbol)} - {"+", "-", "+-"}       # `+-` é o lado de um `Limit`
    nomes |= {type(f).__name__ for f in expr.atoms(AppliedUndef)}
    tokens = _tokens(t, marcas)
    for nome in sorted(nomes, key=_bytes):
        if nome in COMANDOS_COMO_SIMBOLO:
            return _perda("simbolo_partido:%s" % nome)
    for nome in sorted(nomes, key=_bytes):
        if nome not in tokens:
            # o token que foi partido: contém o nome, mas não é o nome com um subscrito (`C` vem de `TC`, não de `C_i`)
            contem = sorted((k for k in tokens if nome in k and not k.startswith(nome + "_")), key=_bytes)
            return _perda("simbolo_partido:%s" % (contem[0] if contem else nome))
    return {"ok": True, "srepr": srepr(expr), "motivo": None,
            "simbolos": sorted((s.name for s in expr.free_symbols), key=_bytes)}


# nome canônico de símbolo como o parse o produz: letras, com um subscrito opcional (`f`, `gamma`, `f_1`,
# `I_x`, `n_F`, `T_max`, `f_star`); é a sintaxe dos nomes da decisão `declarar_funcoes`
RE_NOME_SIMBOLO = re.compile(r"^[A-Za-z]+(?:_[A-Za-z0-9]+)?$")
CAMPOS_DECLARAR_FUNCOES = ("documento", "funcoes", "tipo")
# nomes de função que a marcação explícita produz (`\mathbb{E}[…]`, `E[…]`, `\operatorname{Var}(…)`) e que o
# fiscal lê como momento: declará-los fundiria o operador com a função do PO (o parser recusa também, na
# equação, qualquer outro nome declarado que um `\operatorname{…}` produziu)
FUNCOES_DE_MARCACAO = ("E", "Var")


def validar_nome_de_funcao(nome):
    """ValueError se `nome` não pode ser declarado função: fora de `RE_NOME_SIMBOLO` ou nome de marcação."""
    if not isinstance(nome, str) or not RE_NOME_SIMBOLO.match(nome):
        raise ValueError("nome de função fora da sintaxe dos símbolos do parser (%s): %r"
                         % (RE_NOME_SIMBOLO.pattern, nome))
    if nome in FUNCOES_DE_MARCACAO:
        raise ValueError("%r é função de marcação explícita (esperança/variância), não se declara" % nome)


def validar_declaracao_funcoes(d, onde="declarar_funcoes"):
    """ValueError se a decisão `{"tipo": "declarar_funcoes", "documento", "funcoes"}` for malformada:
    documento texto não vazio; funcoes lista não vazia de nomes únicos na sintaxe de `RE_NOME_SIMBOLO`."""
    if not isinstance(d, dict) or sorted(d) != list(CAMPOS_DECLARAR_FUNCOES):
        raise ValueError("%s: chaves %s; esperadas %s" % (onde, sorted(d) if isinstance(d, dict) else d,
                                                          list(CAMPOS_DECLARAR_FUNCOES)))
    if not isinstance(d["documento"], str) or not d["documento"].strip():
        raise ValueError("%s: `documento` vazio ou não texto" % onde)
    funcoes = d["funcoes"]
    if not isinstance(funcoes, list) or not funcoes:
        raise ValueError("%s: `funcoes` tem de ser lista não vazia de nomes" % onde)
    for f in funcoes:
        try:
            validar_nome_de_funcao(f)
        except ValueError as e:
            raise ValueError("%s: %s" % (onde, e))
    if len(set(funcoes)) != len(funcoes):
        raise ValueError("%s: nome de função repetido em `funcoes`" % onde)


def funcoes_por_documento(decisoes):
    """`{documento: frozenset(funcoes)}` das decisões `declarar_funcoes` (as outras são ignoradas aqui);
    ValueError se alguma for malformada ou se um documento tiver mais de uma."""
    por_doc = {}
    for n, d in enumerate(decisoes, 1):
        if not isinstance(d, dict) or d.get("tipo") != "declarar_funcoes":
            continue
        validar_declaracao_funcoes(d, "decisão %d (declarar_funcoes)" % n)
        if d["documento"] in por_doc:
            raise ValueError("decisão declarar_funcoes repetida: %s" % d["documento"])
        por_doc[d["documento"]] = frozenset(d["funcoes"])
    return por_doc


def simular_funcoes(eqs, declaradas, propostas):
    """O que declarar `propostas` (além das `declaradas` de cada documento) mudaria, sem gravar nada: uma
    linha por (nome proposto, equação) — `passaria_a_parsear` quando a equação só parseia com elas e o `srepr`
    aplica aquele nome (`Function('<nome>')`), `deixaria_de_parsear` quando parseava e deixa de parsear por
    causa dele (`uso_misto`, `funcao_de_marcacao`). `eqs` no formato de `equacoes_do_documento`. Ordenado por
    nome, documento e ordem (bytes). É o que o PO lê antes de declarar: um nome que transforma uma constante
    em função (o `C` da eq. 13 de Convex_Responses) aparece aqui com o LaTeX e o `srepr`."""
    propostas = frozenset(propostas)
    linhas = []
    for eq in eqs:
        base = frozenset(declaradas.get(eq["documento"], frozenset()))
        antes, depois = parsear_latex(eq["latex"], base), parsear_latex(eq["latex"], base | propostas)
        nome_eq = "%s#%d" % (eq["documento"], eq["ordem"])
        if not antes["ok"] and depois["ok"]:
            efeito = "passaria_a_parsear"
            nomes = [n for n in propostas if "Function('%s')" % n in depois["srepr"]]
        elif antes["ok"] and not depois["ok"]:
            efeito = "deixaria_de_parsear"
            culpado = depois["motivo"].rsplit(":", 1)[-1]
            nomes = [culpado] if culpado in propostas else sorted(propostas)
        else:
            continue
        for n in nomes:
            linhas.append({"nome": n, "documento": eq["documento"], "ordem": eq["ordem"], "equacao": nome_eq,
                           "efeito": efeito, "latex": eq["latex"], "srepr": depois["srepr"],
                           "motivo": depois["motivo"]})
    return sorted(linhas, key=lambda l: (_bytes(l["nome"]), _bytes(l["documento"]), l["ordem"]))


def equacoes_do_documento(md, documento, nivel=2):
    """Um registro por bloco `$$…$$` não vazio: `documento`, `topico` (o do recorte no mesmo `nivel` de título),
    `ordem` (1, 2, … no documento) e `latex` (o conteúdo do bloco, sem os espaços das pontas)."""
    infinito = float("inf")
    trechos, _ = recortar_trechos.recortar_texto(md, nivel, 0, infinito, infinito, infinito)
    eqs = []
    for trecho in trechos:
        for m in re.finditer(r"\$\$(.*?)\$\$", trecho["texto"], re.S):
            latex = m.group(1).strip()
            if latex:
                eqs.append({"documento": documento, "topico": trecho["topico"], "ordem": len(eqs) + 1,
                            "latex": latex})
    return eqs


def forma(resultado):
    if not resultado["ok"]:
        return "perda"
    return "algebrica" if resultado["srepr"].startswith("Equality(") else "funcional"


def candidato(eq, onda, funcoes=frozenset()):
    r = parsear_latex(eq["latex"], funcoes)
    return {"nome": "%s#%d" % (eq["documento"], eq["ordem"]), "status": "staging", "corpus": CORPUS, "onda": onda,
            "ordem": eq["ordem"], "latex": eq["latex"], "srepr": r["srepr"], "simbolos": r["simbolos"],
            "motivo": r["motivo"], "variaveis": [{"simbolo": s, "nome": s} for s in r["simbolos"]],
            "forma": forma(r), "fonte": {"documento": eq["documento"], "topico": eq["topico"]},
            "funcoes_declaradas": sorted(funcoes, key=_bytes)}


def niveis_do_recorte(dir_esteira, onda):
    """Os `nivel` das execuções do manifesto do recorte da onda (`<dir_esteira>/trechos-<onda>.manifesto.json`),
    ou None se ele não existe."""
    caminho = recortar_trechos.caminho_manifesto(os.path.join(dir_esteira, "trechos-%s.jsonl" % onda))
    if not os.path.exists(caminho):
        return None
    with io.open(caminho, encoding="utf-8") as f:
        return [e.get("nivel") for e in json.load(f).get("execucoes", [])]


def ler_decisoes(caminho):
    """As linhas do `decisoes-<onda>.jsonl` (JSON por linha; linha vazia é pulada). ValueError se uma não é JSON."""
    linhas = []
    with io.open(caminho, encoding="utf-8") as f:
        for n, texto in enumerate(f, 1):
            if texto.strip():
                try:
                    linhas.append(json.loads(texto))
                except ValueError:
                    raise ValueError("%s, linha %d: não é JSON" % (caminho, n))
    return linhas


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", required=True, help="raiz do corpus (a pasta que contém `conferidos/`)")
    ap.add_argument("--onda", required=True, help="onda: lê <raiz>/conferidos/<onda>/")
    ap.add_argument("--saida", required=True, help="JSONL de candidatos, ex.: _esteira/incerto/equacoes-<onda>.jsonl")
    ap.add_argument("--nivel", type=int, default=2, help="nível do título do tópico (default 2: '## '); o mesmo "
                                                            "do recorte_trechos.py da onda")
    ap.add_argument("--decisoes", help="decisões do PO (default: decisoes-<onda>.jsonl na pasta da --saida, lido só "
                                       "se existir); as `declarar_funcoes` dizem que símbolos são funções em cada "
                                       "documento")
    ap.add_argument("--simular-funcoes", metavar="F,C,…",
                    help="não grava: para cada nome proposto, lista as equações de cada documento que passariam a "
                         "parsear com ele declarado função (ou deixariam de parsear), com LaTeX e srepr — o PO roda "
                         "antes de declarar")
    args = ap.parse_args(argv)
    propostas = None
    if args.simular_funcoes is not None:
        propostas = [n.strip() for n in args.simular_funcoes.split(",")]
        try:
            if not any(propostas):
                raise ValueError("lista vazia")
            for n in propostas:
                validar_nome_de_funcao(n)
            if len(set(propostas)) != len(propostas):
                raise ValueError("nome repetido")
        except ValueError as e:
            ap.error("--simular-funcoes: %s" % e)
    if not recortar_trechos.RE_ONDA.match(args.onda) or ".." in args.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")
    dir_onda = os.path.join(args.raiz, "conferidos", args.onda)
    if not os.path.isdir(dir_onda):
        sys.exit("não existe %s — rode `conferir_onda.py --aprovar` antes" % dir_onda)

    # o tópico da `fonte` tem de ser o de um trecho que existe: o recorte da onda na mesma esteira manda
    niveis = niveis_do_recorte(os.path.dirname(os.path.abspath(args.saida)), args.onda)
    if niveis is not None and any(n != args.nivel for n in niveis):
        sys.exit("--nivel %d diverge do recorte desta onda (nivel %s no manifesto de trechos-%s) — extraia com o "
                 "mesmo --nivel do recortar_trechos.py, ou o tópico citado não será o de trecho nenhum"
                 % (args.nivel, ", ".join(map(str, niveis)), args.onda))

    # funções declaradas pelo PO, por documento (decisão `declarar_funcoes`); sem o arquivo, nenhuma
    caminho_decisoes = args.decisoes or os.path.join(os.path.dirname(os.path.abspath(args.saida)),
                                                     "decisoes-%s.jsonl" % args.onda)
    if args.decisoes and not os.path.exists(args.decisoes):
        sys.exit("--decisoes %s não existe" % args.decisoes)
    try:
        funcoes = funcoes_por_documento(ler_decisoes(caminho_decisoes)) if os.path.exists(caminho_decisoes) else {}
    except ValueError as e:
        sys.exit("recusado, nada gravado — declarar_funcoes em %s: %s" % (caminho_decisoes, e))
    documentos = recortar_trechos.listar_documentos(dir_onda)
    fora = sorted(set(funcoes) - {doc for _, doc, _ in documentos}, key=_bytes)
    if fora:
        sys.exit("recusado, nada gravado — declarar_funcoes de documento fora de %s: %s" % (dir_onda, ", ".join(fora)))

    if propostas is not None:
        eqs = []
        for caminho, doc, _ in documentos:
            with io.open(caminho, encoding="utf-8", newline="") as f:
                eqs += equacoes_do_documento(f.read(), doc, args.nivel)
        sim = simular_funcoes(eqs, funcoes, propostas)
        print("simulação (nada gravado) — funções propostas: %s" % ", ".join(sorted(propostas, key=_bytes)))
        for n in sorted(propostas, key=_bytes):
            do_nome = [l for l in sim if l["nome"] == n]
            print("%s: %d equação(ões)" % (n, len(do_nome)))
            for l in do_nome:
                print("  %s %s — LaTeX: %s" % (l["equacao"], l["efeito"].replace("_", " "),
                                                l["latex"].replace("\n", " ")))
                print("      %s" % (l["srepr"] if l["srepr"] else l["motivo"]))
        return 0

    cands = []
    for caminho, doc, _ in documentos:
        with io.open(caminho, encoding="utf-8", newline="") as f:
            md = f.read()
        cands += [candidato(eq, args.onda, funcoes.get(doc, frozenset()))
                  for eq in equacoes_do_documento(md, doc, args.nivel)]
    texto = "".join(json.dumps(c, sort_keys=True, ensure_ascii=False) + "\n" for c in cands)

    estado = "novo"
    if os.path.exists(args.saida):
        with io.open(args.saida, encoding="utf-8", newline="") as f:
            if f.read() != texto:
                sys.exit("%s já existe com conteúdo diferente (o PO pode ter renomeado candidatos) — não se "
                         "sobrescreve; compare, apague-o ou use outra --saida" % args.saida)
        estado = "inalterado"
    else:
        os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
        with io.open(args.saida, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
    perdas = [c for c in cands if c["forma"] == "perda"]
    print("gravado: %s (%s)" % (args.saida, estado))
    print("equações: %d · parseáveis: %d · perdas declaradas: %d" % (len(cands), len(cands) - len(perdas), len(perdas)))
    for c in perdas:
        print("⚠️ %s — %s — LaTeX preservado: %s" % (c["nome"], c["motivo"], c["latex"].replace("\n", " ")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
