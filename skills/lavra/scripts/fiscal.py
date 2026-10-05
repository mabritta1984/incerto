#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fiscal de duas vias da onda: nada sai de staging sem ele, e prova vermelha nunca promove.

Provas (uma linha por prova; `prova`, `alvo`, `veredito` ∈ verde|vermelho|indeterminado, `detalhe`, `ms`):
  Chaves estruturadas por prova (além de `alvo`, mantido por compatibilidade): P1 `equacao`; P2 `mae`,
  `filha`, `simbolo` (o símbolo isolado — o `alvo` da linha de derivação), `substituicao` (como declarada);
  P3 `equacao`, `condicao`. São elas que distinguem duas derivações da mesma filha ou duas condições da
  mesma equação.
  P1 parse     — todo candidato de `equacoes-<onda>.jsonl`: `srepr` presente → verde; `srepr` nulo →
                 vermelho com o LaTeX e o motivo da perda no `detalhe`. `alvo` = nome da equação.
  P2 derivação — toda linha de `derivacoes-<onda>.jsonl` (`{"filha", "mae", "alvo", "substituicao",
                 "passo"}`): `equivalente(mae, filha, alvo, substituicao)`. `alvo` = nome da filha (a
                 mãe e o símbolo vão no `detalhe`).
  P3 validade  — toda linha de `validades-<onda>.jsonl` (`{"equacao", "condicao"}`):
                 `relacional_parseia(condicao, simbolos da equação)`. `alvo` = nome da equação.
  P4 duas vias — a segunda via, Wolfram, rodada pelo AGENTE pelo MCP (nunca por script), registrada por
                 `registrar_prova.py` em `provas-<onda>.jsonl` e conferida aqui (protocolo: dono único em
                 `references/fiscal.md`). Para toda linha P2 (chave `mae` + `filha`; `alvo` = filha) exige a
                 prova Wolfram `{"prova": "P2", "mae", "filha", …}`; para todo candidato com `momento_fechado`
                 não vazio (`alvo` = `equacao` = nome) exige `{"prova": "momento", "equacao", …}`. Sem prova →
                 vermelho "sem prova Wolfram". Mãe + filha repetida em mais de uma linha P2 → vermelho
                 "derivação ambígua para a prova Wolfram" em todas elas. `impressao` da prova ≠
                 `impressao_esperada` (sha256 do conteúdo provado, recalculado da onda atual) → vermelho "prova
                 Wolfram desatualizada". Derivação: veredito Wolfram ≠ veredito SymPy → vermelho "vias
                 divergem", com o `detalhe` da P2 e a `saida` Wolfram verbatim no `detalhe` (SymPy
                 indeterminado + Wolfram verde também diverge: indeterminado é pauta do PO na Task 11, não da
                 P4); vias iguais → o veredito comum ("vias concordam"). Momento: não há via SymPy; a P4 tem o
                 veredito da prova Wolfram. Candidato SEM `momento_fechado` cujo `srepr` aplica `E` ou `Var`
                 (`aplica_momento`: `\\mathbb{E}[X] = …`, `\\operatorname{Var}(X) = …`) → indeterminado
                 "aplica E/Var sem momento_fechado declarado" (afirma um momento que ninguém prova). Chaves
                 estruturadas da P4: `mae`, `filha` (derivação) ou `equacao` (momento).
`provas_sympy` roda só P1–P3; `provas` roda a tabela `PROVAS` inteira (P1–P4), que é o que a CLI grava.

`provas_wolfram(caminho)`: lê `provas-<onda>.jsonl` (ausente = nenhuma prova) e indexa por
`chave_wolfram` — `("P2", mae, filha)` ou `("momento", equacao)`; toda linha traz `impressao` = sha256
hex de `json.dumps(conteudo, sort_keys=True, ensure_ascii=False)`, com conteudo P2 `{"mae_srepr",
"filha_srepr", "simbolo", "substituicao"}` e momento `{"equacao_srepr", "momento_fechado"}`
(`impressao_esperada`, dono único; `registrar_prova.py` a chama); linha malformada (chaves fora do
formato, `via` ≠ wolfram, `prova` ou `veredito` desconhecidos) ou chave repetida → `ValueError` (a CLI
sai com a mensagem): prova ambígua não é prova.

`equivalente`: os `srepr` viram expressão por `sympy.sympify`; a `substituicao` ({símbolo: expressão em
sintaxe SymPy}) é aplicada aos dois lados; a filha tem de ser `Equality` com lado esquerdo exatamente
`Symbol(alvo)` e a mãe uma `Equality` que contenha `alvo`; `solve(mae, alvo)`; alguma solução com
`simplify(sol - filha.rhs) == 0` → verde se for a única solução, e indeterminado ("filha escolhe um
ramo (k de n)", k = soluções iguais à filha, n = soluções) se houver mais de uma;
soluções, mas nenhuma igual → vermelho (as soluções no
`detalhe`); nenhuma solução ou SymPy sem resposta → indeterminado. Não há timeout portável: só `solve`
e `simplify`, nada mais caro.

`relacional_parseia`: a estrutura booleana é lida pelo `ast` do Python — `and`/`or`/`not` (e `&`, `|`,
`~` com os operandos entre parênteses) combinam condições; cada comparação simples (`a > b`, `<`, `>=`,
`<=`, `==`, `!=`; comparação encadeada não) é lida por `parse_expr(..., evaluate=False)` com todo nome
que não é chamada como `Symbol` (`pi`, `e`, `E` continuam símbolos, como na extração; o token `lambda`,
palavra reservada do Python, é renomeado antes do parse e volta como `Symbol('lambda')`). Toda comparação
tem de ter símbolo livre (constante `1 > 0`, `True` não são condição) e todo símbolo livre tem de estar
entre os símbolos da equação; função não definida no SymPy (`g(x)`) não é aceita.

Uso:
  python3 fiscal.py --onda <onda> [--raiz-esteira _esteira/incerto] [--relatorio <md>]
                    [--provas-wolfram <jsonl>]      (padrão: <raiz-esteira>/provas-<onda>.jsonl)

Grava o relatório Markdown (`--relatorio`, padrão `<raiz-esteira>/fiscal-<onda>.md`; tabela `prova |
alvo | veredito | detalhe | ms`) e `<raiz-esteira>/fiscal-<onda>.jsonl` (uma linha por prova, chaves
ordenadas, SEM `ms`: o tempo só existe no Markdown, para que o JSONL — a entrada do portão da Task 11 —
seja determinístico). `derivacoes-`/`validades-` ausentes = nenhuma declaração.
`sympy` só é importado dentro de função (decisão A6).
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import sys
import time
import tokenize

import recortar_trechos   # vizinho em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo

VERDE, VERMELHO, INDETERMINADO = "verde", "vermelho", "indeterminado"
VEREDITOS = (VERDE, VERMELHO, INDETERMINADO)
VIA_WOLFRAM = "wolfram"
# `prova` de uma linha de `provas-<onda>.jsonl` → chaves que a identificam (e com que a P4 a junta à onda)
CHAVES_WOLFRAM = {"P2": ("mae", "filha"), "momento": ("equacao",)}
# campos de toda linha de prova Wolfram, além das chaves; `impressao` amarra o veredito ao conteúdo provado
CAMPOS_WOLFRAM = ("prova", "via", "codigo", "saida", "veredito", "impressao")


def _ordenado(exprs):
    from sympy import default_sort_key
    return sorted(exprs, key=default_sort_key)


# `\lambda` vira `Symbol('lambda')` na extração, mas `lambda` é palavra reservada do Python: o token NAME
# `lambda` é trocado por este nome antes do `ast`/`parse_expr` e lido de volta como `Symbol('lambda')`
LAMBDA = "QZlambdaQZ"


def _sem_lambda(texto):
    tokens = list(tokenize.generate_tokens(io.StringIO(texto).readline))
    if not any(t.type == tokenize.NAME and t.string == "lambda" for t in tokens):
        return texto
    if LAMBDA in texto:
        raise ValueError("o texto já contém %s" % LAMBDA)
    return tokenize.untokenize((t.type, LAMBDA if t.type == tokenize.NAME and t.string == "lambda" else t.string)
                               for t in tokens).strip()


def _expressao(texto):
    """Expressão em sintaxe SymPy com todo nome não chamado como símbolo (`pi`, `e` e `lambda` inclusive)."""
    from sympy import Symbol
    from sympy.parsing.sympy_parser import parse_expr
    texto = _sem_lambda(texto)
    arvore = ast.parse(texto, mode="eval")
    chamados = {id(n.func) for n in ast.walk(arvore) if isinstance(n, ast.Call)}
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name) and id(n) not in chamados}
    return parse_expr(texto, {nome: Symbol("lambda" if nome == LAMBDA else nome) for nome in nomes}, evaluate=False)


def equivalente(mae_srepr, filha_srepr, alvo, substituicao):
    """A filha (`alvo = …`) sai da mãe resolvida para `alvo`, sob a `substituicao` declarada?"""
    from sympy import Equality, Symbol, simplify, solve, sstr, sympify

    def resultado(veredito, detalhe):
        return {"veredito": veredito, "detalhe": detalhe}

    if not isinstance(alvo, str) or not alvo:
        return resultado(INDETERMINADO, "alvo não declarado")
    try:
        mae, filha = sympify(mae_srepr), sympify(filha_srepr)
    except Exception as e:
        return resultado(INDETERMINADO, "srepr ilegível: %s" % type(e).__name__)
    x = Symbol(alvo)
    if not isinstance(filha, Equality) or filha.lhs != x:
        return resultado(INDETERMINADO, "a filha não é `%s = …`" % alvo)
    if not isinstance(mae, Equality):
        return resultado(INDETERMINADO, "a mãe não é uma igualdade")
    if alvo in (substituicao or {}):
        return resultado(INDETERMINADO, "a substituição não pode trocar o próprio alvo `%s`" % alvo)
    try:
        troca = {Symbol(k): _expressao(v) for k, v in sorted((substituicao or {}).items())}
    except Exception as e:
        return resultado(INDETERMINADO, "substituição ilegível: %s" % type(e).__name__)
    mae = mae.subs(troca, simultaneous=True)
    rhs = filha.rhs.subs(troca, simultaneous=True)
    if not isinstance(mae, Equality):
        return resultado(INDETERMINADO, "a mãe deixou de ser igualdade após a substituição: %s" % sstr(mae))
    if x not in mae.free_symbols:
        return resultado(INDETERMINADO, "`%s` não aparece na mãe" % alvo)
    try:
        solucoes = _ordenado(solve(mae.lhs - mae.rhs, x))
    except Exception as e:
        return resultado(INDETERMINADO, "solve sem resposta: %s" % type(e).__name__)
    if not solucoes:
        return resultado(INDETERMINADO, "solve não achou solução para `%s`" % alvo)
    lista = "; ".join("%s = %s" % (alvo, sstr(s)) for s in solucoes)
    try:
        iguais = [s for s in solucoes if simplify(s - rhs) == 0]
    except Exception as e:
        return resultado(INDETERMINADO, "simplify sem resposta: %s" % type(e).__name__)
    if iguais and len(solucoes) > 1:
        # `y = x^2` → `x = sqrt(y)`: a filha escolheu um ramo; a escolha precisa de hipótese, não é derivação pura
        return resultado(INDETERMINADO, "filha escolhe um ramo (%d de %d): %s" % (len(iguais), len(solucoes), lista))
    if iguais:
        return resultado(VERDE, "%s = %s" % (alvo, sstr(iguais[0])))
    return resultado(VERMELHO, "a mãe dá %s; a filha diz %s = %s" % (lista, alvo, sstr(rhs)))


def relacional_parseia(condicao, simbolos):
    """`condicao` é uma comparação (ou combinação booleana de comparações) só sobre `simbolos`?"""
    from sympy import Expr
    from sympy.core.function import AppliedUndef
    from sympy.core.relational import Relational

    permitidos = set(simbolos)

    def comparacao(no):
        if len(no.ops) != 1:
            return False                                       # `a < b < c`: encadeada, não
        try:
            rel = _expressao(ast.unparse(no))
        except Exception:
            return False
        if not isinstance(rel, Relational) or not all(isinstance(lado, Expr) for lado in rel.args):
            return False
        livres = {s.name for s in rel.free_symbols}
        return bool(livres) and livres <= permitidos and not rel.atoms(AppliedUndef)

    def valida(no):
        if isinstance(no, ast.BoolOp):
            return all(valida(v) for v in no.values)
        if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.Not, ast.Invert)):
            return valida(no.operand)
        if isinstance(no, ast.BinOp) and isinstance(no.op, (ast.BitAnd, ast.BitOr)):
            return valida(no.left) and valida(no.right)
        if isinstance(no, ast.Compare):
            return comparacao(no)
        return False

    try:
        return valida(ast.parse(_sem_lambda(condicao.strip()), mode="eval").body)
    except Exception:
        return False


# --- provas Wolfram registradas -----------------------------------------------------------------------

def chave_wolfram(linha):
    """`("P2", mae, filha)` ou `("momento", equacao)`: a identidade de uma prova Wolfram registrada."""
    prova = linha.get("prova")
    if prova not in CHAVES_WOLFRAM:
        raise ValueError("prova Wolfram desconhecida: %r (use %s)" % (prova, " ou ".join(sorted(CHAVES_WOLFRAM))))
    return (prova,) + tuple(linha.get(k) for k in CHAVES_WOLFRAM[prova])


def validar_prova_wolfram(linha):
    """Levanta `ValueError` se `linha` não estiver exatamente no formato de `registrar_prova.py`."""
    if not isinstance(linha, dict):
        raise ValueError("linha não é objeto JSON")
    chave_wolfram(linha)
    esperadas = set(CAMPOS_WOLFRAM) | set(CHAVES_WOLFRAM[linha["prova"]])
    if set(linha) != esperadas:
        raise ValueError("chaves %s; esperadas %s" % (sorted(linha), sorted(esperadas)))
    if linha["via"] != VIA_WOLFRAM:
        raise ValueError("via %r; esperada %r" % (linha["via"], VIA_WOLFRAM))
    if linha["veredito"] not in VEREDITOS:
        raise ValueError("veredito %r; use %s" % (linha["veredito"], "|".join(VEREDITOS)))
    for k in esperadas - {"prova", "via", "veredito"}:
        if not isinstance(linha[k], str) or not linha[k].strip():
            raise ValueError("`%s` vazio ou não texto" % k)
    if len(linha["impressao"]) != 64 or set(linha["impressao"]) - set("0123456789abcdef"):
        raise ValueError("`impressao` não é sha256 hex: %r" % linha["impressao"])


def impressao(conteudo):
    """sha256 hex de `json.dumps(conteudo, sort_keys=True, ensure_ascii=False)`."""
    return hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def impressao_esperada(chave, equacoes, derivacoes):
    """A `impressao` que a prova de `chave` tem de trazer para a onda como está agora.

    P2: `{"mae_srepr", "filha_srepr", "simbolo", "substituicao"}` da ÚNICA linha de `derivacoes` com essa
    mãe e essa filha; momento: `{"equacao_srepr", "momento_fechado"}` do candidato. `ValueError` se a
    derivação não existir ou for ambígua, se a equação for desconhecida ou se o momento não estiver declarado.
    """
    por_nome = {e["nome"]: e for e in equacoes}
    if chave[0] == "P2":
        _, mae, filha = chave
        ds = [d for d in derivacoes if (d.get("mae"), d.get("filha")) == (mae, filha)]
        if not ds:
            raise ValueError("derivação de %s a %s não declarada em derivacoes-" % (mae, filha))
        if len(ds) > 1:
            raise ValueError("derivação ambígua de %s a %s (%d linhas)" % (mae, filha, len(ds)))
        desconhecidas = [n for n in (mae, filha) if n not in por_nome]
        if desconhecidas:
            raise ValueError("equação desconhecida: %s" % ", ".join(str(n) for n in desconhecidas))
        return impressao({"mae_srepr": por_nome[mae].get("srepr"), "filha_srepr": por_nome[filha].get("srepr"),
                          "simbolo": ds[0].get("alvo"), "substituicao": ds[0].get("substituicao") or {}})
    if chave[0] == "momento":
        nome = chave[1]
        if nome not in por_nome:
            raise ValueError("equação desconhecida: %s" % nome)
        if not por_nome[nome].get("momento_fechado"):
            raise ValueError("%s não declara momento_fechado" % nome)
        return impressao({"equacao_srepr": por_nome[nome].get("srepr"),
                          "momento_fechado": por_nome[nome]["momento_fechado"]})
    raise ValueError("prova Wolfram desconhecida: %r" % (chave[0],))


RE_APLICA_MOMENTO = re.compile(r"Function\('(?:E|Var)'\)")


def aplica_momento(srepr):
    """O `srepr` aplica `E` ou `Var` (marcação explícita de esperança ou variância na extração)?"""
    return bool(srepr) and bool(RE_APLICA_MOMENTO.search(srepr))


def provas_wolfram(caminho):
    """`provas-<onda>.jsonl` indexado por `chave_wolfram`; arquivo ausente = nenhuma prova."""
    if not os.path.exists(caminho):
        return {}
    indice = {}
    with io.open(caminho, encoding="utf-8") as f:
        for n, texto in enumerate(f, 1):
            if not texto.strip():
                continue
            try:
                linha = json.loads(texto)
                validar_prova_wolfram(linha)
            except ValueError as e:
                raise ValueError("%s, linha %d: %s" % (caminho, n, e))
            chave = chave_wolfram(linha)
            if chave in indice:
                raise ValueError("%s, linha %d: prova repetida %s" % (caminho, n, "/".join(chave)))
            indice[chave] = linha
    return indice


# --- provas: cada uma recebe o contexto e devolve linhas sem `ms` ---------------------------------------

def _p1_parse(ctx):
    for eq in ctx["equacoes"]:
        if eq.get("srepr"):
            yield {"alvo": eq["nome"], "equacao": eq["nome"], "veredito": VERDE, "detalhe": "srepr presente"}
        else:
            yield {"alvo": eq["nome"], "equacao": eq["nome"], "veredito": VERMELHO,
                   "detalhe": "sem srepr (%s) — LaTeX: %s" % (eq.get("motivo") or "motivo ausente", eq.get("latex"))}


def _p2_derivacao(ctx):
    por_nome = ctx["por_nome"]
    for d in ctx["derivacoes"]:
        filha, mae, alvo = d.get("filha"), d.get("mae"), d.get("alvo")
        chaves = {"alvo": filha, "mae": mae, "filha": filha, "simbolo": alvo, "substituicao": d.get("substituicao") or {}}
        desconhecidas = [n for n in (mae, filha) if n not in por_nome]
        if desconhecidas:
            yield dict(chaves, veredito=VERMELHO,
                       detalhe="equação desconhecida: %s" % ", ".join(str(n) for n in desconhecidas))
            continue
        sem = [n for n in (mae, filha) if not por_nome[n].get("srepr")]
        if sem:
            yield dict(chaves, veredito=VERMELHO, detalhe="sem srepr: %s" % ", ".join(sem))
            continue
        r = equivalente(por_nome[mae]["srepr"], por_nome[filha]["srepr"], alvo, d.get("substituicao") or {})
        yield dict(chaves, veredito=r["veredito"], detalhe="de %s por %s: %s" % (mae, alvo, r["detalhe"]))


def _p3_validade(ctx):
    por_nome = ctx["por_nome"]
    for v in ctx["validades"]:
        nome, condicao = v.get("equacao"), v.get("condicao")
        chaves = {"alvo": nome, "equacao": nome, "condicao": condicao}
        if nome not in por_nome:
            yield dict(chaves, veredito=VERMELHO, detalhe="equação desconhecida: %s" % nome)
            continue
        ok = isinstance(condicao, str) and relacional_parseia(condicao, por_nome[nome].get("simbolos") or [])
        yield dict(chaves, veredito=VERDE if ok else VERMELHO,
                   detalhe=("condição %s" if ok else "condição não é relacional sobre os símbolos da equação: %s")
                   % condicao)


def _desatualizada(w, chave, ctx):
    """Motivo pelo qual a prova `w` não vale para a onda como está agora, ou None."""
    try:
        esperada = impressao_esperada(chave, ctx["equacoes"], ctx["derivacoes"])
    except ValueError as e:
        return "prova Wolfram desatualizada (%s)" % e
    if w["impressao"] != esperada:
        return "prova Wolfram desatualizada: o conteúdo provado mudou desde o registro (impressao %s… ≠ %s…)" % (
            w["impressao"][:12], esperada[:12])
    return None


def _p4_duas_vias(ctx):
    wolfram = ctx["wolfram"]
    p2s = [l for l in ctx["linhas"] if l["prova"] == "P2"]
    ocorrencias = {}
    for l in p2s:
        ocorrencias[(l["mae"], l["filha"])] = ocorrencias.get((l["mae"], l["filha"]), 0) + 1
    for p2 in p2s:
        mae, filha = p2["mae"], p2["filha"]
        chaves = {"alvo": filha, "mae": mae, "filha": filha}
        if ocorrencias[(mae, filha)] > 1:
            # a prova é chaveada por mãe + filha: com duas derivações iguais nisso, uma prova validaria as duas
            yield dict(chaves, veredito=VERMELHO, detalhe="derivação ambígua para a prova Wolfram: %d derivações "
                       "de %s a %s na onda" % (ocorrencias[(mae, filha)], mae, filha))
            continue
        w = wolfram.get(("P2", mae, filha))
        motivo = w and _desatualizada(w, ("P2", mae, filha), ctx)
        if w is None:
            yield dict(chaves, veredito=VERMELHO, detalhe="sem prova Wolfram para a derivação de %s a %s" % (mae, filha))
        elif motivo:
            yield dict(chaves, veredito=VERMELHO, detalhe=motivo)
        elif w["veredito"] != p2["veredito"]:
            yield dict(chaves, veredito=VERMELHO, detalhe="vias divergem — SymPy %s: %s — Wolfram %s: %s"
                       % (p2["veredito"], p2["detalhe"], w["veredito"], w["saida"]))
        else:
            yield dict(chaves, veredito=p2["veredito"], detalhe="vias concordam (%s) — SymPy: %s — Wolfram: %s"
                       % (p2["veredito"], p2["detalhe"], w["saida"]))
    for eq in ctx["equacoes"]:
        momento = eq.get("momento_fechado")
        nome = eq["nome"]
        chaves = {"alvo": nome, "equacao": nome}
        if not momento:
            if aplica_momento(eq.get("srepr")):
                # `\mathbb{E}[X] = …` afirma um momento fechado: sem declaração não há o que a via Wolfram prove
                yield dict(chaves, veredito=INDETERMINADO, detalhe="aplica E/Var sem momento_fechado declarado — "
                           "decida o momento_fechado (que a via Wolfram prova) ou aceite a linha")
            continue
        declarado = json.dumps(momento, sort_keys=True, ensure_ascii=False)
        w = wolfram.get(("momento", nome))
        motivo = w and _desatualizada(w, ("momento", nome), ctx)
        if w is None:
            yield dict(chaves, veredito=VERMELHO, detalhe="sem prova Wolfram para o momento fechado %s" % declarado)
        elif motivo:
            yield dict(chaves, veredito=VERMELHO, detalhe=motivo)
        else:
            yield dict(chaves, veredito=w["veredito"], detalhe="momento fechado %s — Wolfram %s: %s"
                       % (declarado, w["veredito"], w["saida"]))


PROVAS_SYMPY = (("P1", _p1_parse), ("P2", _p2_derivacao), ("P3", _p3_validade))
PROVAS = PROVAS_SYMPY + (("P4", _p4_duas_vias),)


def _executar(tabela, equacoes, derivacoes, validades, wolfram):
    linhas = []
    ctx = {"equacoes": equacoes, "derivacoes": derivacoes, "validades": validades, "wolfram": wolfram,
           "por_nome": {e["nome"]: e for e in equacoes}, "linhas": linhas}
    for prova, executar in tabela:
        gerador = executar(ctx)
        while True:
            inicio = time.perf_counter()
            try:
                linha = next(gerador)
            except StopIteration:
                break
            linha["ms"] = int(round((time.perf_counter() - inicio) * 1000))
            linha["prova"] = prova
            linhas.append(linha)
    return linhas


def provas_sympy(equacoes, derivacoes, validades):
    """Só a via SymPy (P1–P3)."""
    return _executar(PROVAS_SYMPY, equacoes, derivacoes, validades, {})


def provas(equacoes, derivacoes, validades, wolfram):
    """As duas vias (P1–P4); `wolfram` é o índice de `provas_wolfram`."""
    return _executar(PROVAS, equacoes, derivacoes, validades, wolfram)


# --- saídas -----------------------------------------------------------------------------------------

def _celula(valor):
    return str(valor).replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def relatorio(onda, linhas):
    contagem = {v: sum(1 for l in linhas if l["veredito"] == v) for v in (VERDE, VERMELHO, INDETERMINADO)}
    partes = ["# Fiscal — onda %s\n\n" % onda,
              "Provas: %d · verde: %d · vermelho: %d · indeterminado: %d\n\n"
              % (len(linhas), contagem[VERDE], contagem[VERMELHO], contagem[INDETERMINADO]),
              "Vermelho nunca promove. `ms` só existe aqui; `fiscal-%s.jsonl` (sem `ms`) é a entrada do portão.\n\n"
              % onda,
              "| prova | alvo | veredito | detalhe | ms |\n", "|---|---|---|---|---|\n"]
    for l in linhas:
        partes.append("| %s |\n" % " | ".join(_celula(l[k]) for k in ("prova", "alvo", "veredito", "detalhe", "ms")))
    return "".join(partes)


def jsonl(linhas):
    return "".join(json.dumps({k: v for k, v in l.items() if k != "ms"}, sort_keys=True, ensure_ascii=False) + "\n"
                   for l in linhas)


def ler_jsonl(caminho, obrigatorio=False):
    if not os.path.exists(caminho):
        if obrigatorio:
            sys.exit("não existe %s — rode `extrair_equacoes.py` antes" % caminho)
        return []
    with io.open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _gravar(caminho, texto):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onda", required=True, help="onda: lê <raiz-esteira>/{equacoes,derivacoes,validades}-<onda>.jsonl")
    ap.add_argument("--raiz-esteira", default="_esteira/incerto", help="pasta dos JSONL da onda (padrão: _esteira/incerto)")
    ap.add_argument("--relatorio", help="relatório Markdown (padrão: <raiz-esteira>/fiscal-<onda>.md)")
    ap.add_argument("--provas-wolfram", help="provas Wolfram registradas por registrar_prova.py "
                                             "(padrão: <raiz-esteira>/provas-<onda>.jsonl)")
    args = ap.parse_args(argv)
    if not recortar_trechos.RE_ONDA.match(args.onda) or ".." in args.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")

    def arquivo(prefixo, ext="jsonl"):
        return os.path.join(args.raiz_esteira, "%s-%s.%s" % (prefixo, args.onda, ext))

    equacoes = ler_jsonl(arquivo("equacoes"), obrigatorio=True)
    try:
        wolfram = provas_wolfram(args.provas_wolfram or arquivo("provas"))
    except ValueError as e:
        sys.exit("provas Wolfram inválidas — %s" % e)
    linhas = provas(equacoes, ler_jsonl(arquivo("derivacoes")), ler_jsonl(arquivo("validades")), wolfram)
    caminho_md = args.relatorio or arquivo("fiscal", "md")
    _gravar(caminho_md, relatorio(args.onda, linhas))
    _gravar(arquivo("fiscal"), jsonl(linhas))
    print("gravado: %s e %s" % (caminho_md, arquivo("fiscal")))
    for v in (VERDE, VERMELHO, INDETERMINADO):
        print("%s: %d" % (v, sum(1 for l in linhas if l["veredito"] == v)))
    for l in linhas:
        if l["veredito"] != VERDE:
            print("%s %s %s — %s" % (l["prova"], l["veredito"], l["alvo"], l["detalhe"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
