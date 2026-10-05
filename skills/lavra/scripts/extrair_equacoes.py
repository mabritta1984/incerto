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
     símbolo com subscrito seguido de `^` (`C_n^k` → Pow(C_n, k): `_{…}^`), chaves de conjunto `\\{…\\}` (e
     `\\left\\{…\\right\\}`, lidas como `x`), `^{(…)}` (lido como potência) e `\\Delta` seguido de letra
     (`\\Delta x` lido como `Delta·x`);
  3. `sympy.parsing.latex.parse_latex(..., strict=True)`; erro é perda `strict`;
  4. conferência: todo símbolo e toda função do resultado têm de ser um token inteiro do LaTeX
     normalizado (`TC` lido como `T·C` é `simbolo_partido:TC`); símbolo com nome de comando LaTeX
     (`mathrm`, `dots`, …), relação encadeada (`a = b = c`) e função aplicada que não veio de marcação
     explícita (`p(1-p)`, `\\alpha(1-\\alpha)`, `g(x)`: `nao_suportado:p(`) também são perda.
Perda é ⚠️ com o LaTeX preservado como veio; nunca some.

Uso:
  python3 extrair_equacoes.py --raiz <corpus> --onda <onda> --saida _esteira/incerto/equacoes-<onda>.jsonl \
      [--nivel 2]
`--nivel` é o nível do título que define o tópico (default 2), o MESMO do `recortar_trechos.py` da onda: se
o manifesto do recorte (`trechos-<onda>.manifesto.json`, na pasta da `--saida`) existe e registra outro
`nivel`, a extração recusa (o tópico citado não seria o de trecho nenhum).

Saída: um candidato por linha (`status: "staging"`, `nome` = `<documento>#<ordem>` até o PO renomear,
`latex`, `srepr`, `simbolos`, `variaveis`, `forma` — `algebrica` com `=`, `funcional` sem `=`, `perda` —,
`motivo`, `fonte: {documento, topico}`), documentos em ordem de bytes, sem timestamp. A saída nunca é
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
# símbolo com subscrito seguido de `^` (`C_n^k`, binomial; `x_{i}^{2}`): o SymPy lê Pow(C_n, k) — perda
_SUBSCRITO_E_EXPOENTE = r"_\s*(?:\{[^{}]*\}|\\[A-Za-z]+|[A-Za-z0-9])\s*\^"
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
    if re.search(_SUBSCRITO_E_EXPOENTE, latex):
        return None, [], "nao_suportado:_{…}^"
    m = re.search(RESIDUAIS, _RE_MARCA.sub(" ", t))
    if m:
        return None, [], "nao_suportado:%s" % m.group(0)
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


def parsear_latex(latex):
    """LaTeX → `{"ok", "srepr", "simbolos", "motivo"}` pela definição estrita de "parseável" (ver o topo).
    Falta do `sympy`/`antlr4` sobe como ImportError (o portão diz "não medido", o CLI falha alto); qualquer
    outro erro inesperado é perda declarada `erro:<tipo>`, nunca um `ok`."""
    try:
        return _parsear(latex)
    except ImportError:
        raise
    except Exception as e:
        return _perda("erro:%s" % type(e).__name__)


def _parsear(latex):
    from sympy import Function, Max, Min, Symbol, srepr
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

    # função aplicada só a que veio de marcação explícita (`\mathbb{E}[…]`, `E[…]`, `\operatorname{…}(…)`);
    # `p(1-p)`, `\alpha(1-\alpha)`, `g(x)` seriam lidos como função: ambíguo, perda declarada
    for f in sorted(expr.atoms(AppliedUndef), key=lambda f: _bytes(type(f).__name__)):
        nome = type(f).__name__
        if nome not in funcoes_de and nome not in ("max", "min"):
            return _perda("nao_suportado:%s(" % _canonico(nome))

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

    for no in (expr,) + tuple(expr.atoms(Relational)):
        if isinstance(no, Relational) and any(isinstance(a, Relational) for a in no.args):
            return _perda("nao_suportado:relacao_encadeada")
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


def candidato(eq, onda):
    r = parsear_latex(eq["latex"])
    return {"nome": "%s#%d" % (eq["documento"], eq["ordem"]), "status": "staging", "corpus": CORPUS, "onda": onda,
            "ordem": eq["ordem"], "latex": eq["latex"], "srepr": r["srepr"], "simbolos": r["simbolos"],
            "motivo": r["motivo"], "variaveis": [{"simbolo": s, "nome": s} for s in r["simbolos"]],
            "forma": forma(r), "fonte": {"documento": eq["documento"], "topico": eq["topico"]}}


def niveis_do_recorte(dir_esteira, onda):
    """Os `nivel` das execuções do manifesto do recorte da onda (`<dir_esteira>/trechos-<onda>.manifesto.json`),
    ou None se ele não existe."""
    caminho = recortar_trechos.caminho_manifesto(os.path.join(dir_esteira, "trechos-%s.jsonl" % onda))
    if not os.path.exists(caminho):
        return None
    with io.open(caminho, encoding="utf-8") as f:
        return [e.get("nivel") for e in json.load(f).get("execucoes", [])]


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
    args = ap.parse_args(argv)
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

    cands = []
    for caminho, doc, _ in recortar_trechos.listar_documentos(dir_onda):
        with io.open(caminho, encoding="utf-8", newline="") as f:
            md = f.read()
        cands += [candidato(eq, args.onda) for eq in equacoes_do_documento(md, doc, args.nivel)]
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
