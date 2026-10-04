#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fiscal algébrico da onda: nada sai de staging sem ele, e prova vermelha nunca promove.

Provas (uma linha por prova; `prova`, `alvo`, `veredito` ∈ verde|vermelho|indeterminado, `detalhe`, `ms`):
  P1 parse     — todo candidato de `equacoes-<onda>.jsonl`: `srepr` presente → verde; `srepr` nulo →
                 vermelho com o LaTeX e o motivo da perda no `detalhe`. `alvo` = nome da equação.
  P2 derivação — toda linha de `derivacoes-<onda>.jsonl` (`{"filha", "mae", "alvo", "substituicao",
                 "passo"}`): `equivalente(mae, filha, alvo, substituicao)`. `alvo` = nome da filha (a
                 mãe e o símbolo vão no `detalhe`).
  P3 validade  — toda linha de `validades-<onda>.jsonl` (`{"equacao", "condicao"}`):
                 `relacional_parseia(condicao, simbolos da equação)`. `alvo` = nome da equação.
A Task 10 acrescenta a via Wolfram (P4) à tabela `PROVAS`; `--provas-wolfram` já é aceito e, por ora,
não é usado.

`equivalente`: os `srepr` viram expressão por `sympy.sympify`; a `substituicao` ({símbolo: expressão em
sintaxe SymPy}) é aplicada aos dois lados; a filha tem de ser `Equality` com lado esquerdo exatamente
`Symbol(alvo)` e a mãe uma `Equality` que contenha `alvo`; `solve(mae, alvo)`; alguma solução com
`simplify(sol - filha.rhs) == 0` → verde; soluções, mas nenhuma igual → vermelho (as soluções no
`detalhe`); nenhuma solução ou SymPy sem resposta → indeterminado. Não há timeout portável: só `solve`
e `simplify`, nada mais caro.

`relacional_parseia`: a estrutura booleana é lida pelo `ast` do Python — `and`/`or`/`not` (e `&`, `|`,
`~` com os operandos entre parênteses) combinam condições; cada comparação simples (`a > b`, `<`, `>=`,
`<=`, `==`, `!=`; comparação encadeada não) é lida por `parse_expr(..., evaluate=False)` com todo nome
que não é chamada como `Symbol` (`pi`, `e`, `E` continuam símbolos, como na extração). Toda comparação
tem de ter símbolo livre (constante `1 > 0`, `True` não são condição) e todo símbolo livre tem de estar
entre os símbolos da equação; função não definida no SymPy (`g(x)`) não é aceita.

Uso:
  python3 fiscal.py --onda <onda> [--raiz-esteira _esteira/incerto] [--relatorio <md>]
                    [--provas-wolfram _esteira/incerto/provas-<onda>.jsonl]

Grava o relatório Markdown (`--relatorio`, padrão `<raiz-esteira>/fiscal-<onda>.md`; tabela `prova |
alvo | veredito | detalhe | ms`) e `<raiz-esteira>/fiscal-<onda>.jsonl` (uma linha por prova, chaves
ordenadas, SEM `ms`: o tempo só existe no Markdown, para que o JSONL — a entrada do portão da Task 11 —
seja determinístico). `derivacoes-`/`validades-` ausentes = nenhuma declaração.
`sympy` só é importado dentro de função (decisão A6).
"""
import argparse
import ast
import io
import json
import os
import sys
import time

import recortar_trechos   # vizinho em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo

VERDE, VERMELHO, INDETERMINADO = "verde", "vermelho", "indeterminado"


def _ordenado(exprs):
    from sympy import default_sort_key
    return sorted(exprs, key=default_sort_key)


def _expressao(texto):
    """Expressão em sintaxe SymPy com todo nome não chamado como símbolo (`pi` e `e` inclusive)."""
    from sympy import Symbol
    from sympy.parsing.sympy_parser import parse_expr
    arvore = ast.parse(texto, mode="eval")
    chamados = {id(n.func) for n in ast.walk(arvore) if isinstance(n, ast.Call)}
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name) and id(n) not in chamados}
    return parse_expr(texto, {nome: Symbol(nome) for nome in nomes}, evaluate=False)


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
        return valida(ast.parse(condicao.strip(), mode="eval").body)
    except Exception:
        return False


# --- provas: cada uma recebe o contexto e devolve linhas sem `ms`; a Task 10 acrescenta P4 ---------------

def _p1_parse(ctx):
    for eq in ctx["equacoes"]:
        if eq.get("srepr"):
            yield {"alvo": eq["nome"], "veredito": VERDE, "detalhe": "srepr presente"}
        else:
            yield {"alvo": eq["nome"], "veredito": VERMELHO,
                   "detalhe": "sem srepr (%s) — LaTeX: %s" % (eq.get("motivo") or "motivo ausente", eq.get("latex"))}


def _p2_derivacao(ctx):
    por_nome = ctx["por_nome"]
    for d in ctx["derivacoes"]:
        filha, mae, alvo = d.get("filha"), d.get("mae"), d.get("alvo")
        desconhecidas = [n for n in (mae, filha) if n not in por_nome]
        if desconhecidas:
            yield {"alvo": filha, "veredito": VERMELHO,
                   "detalhe": "equação desconhecida: %s" % ", ".join(str(n) for n in desconhecidas)}
            continue
        sem = [n for n in (mae, filha) if not por_nome[n].get("srepr")]
        if sem:
            yield {"alvo": filha, "veredito": VERMELHO, "detalhe": "sem srepr: %s" % ", ".join(sem)}
            continue
        r = equivalente(por_nome[mae]["srepr"], por_nome[filha]["srepr"], alvo, d.get("substituicao") or {})
        yield {"alvo": filha, "veredito": r["veredito"],
               "detalhe": "de %s por %s: %s" % (mae, alvo, r["detalhe"])}


def _p3_validade(ctx):
    por_nome = ctx["por_nome"]
    for v in ctx["validades"]:
        nome, condicao = v.get("equacao"), v.get("condicao")
        if nome not in por_nome:
            yield {"alvo": nome, "veredito": VERMELHO, "detalhe": "equação desconhecida: %s" % nome}
            continue
        ok = isinstance(condicao, str) and relacional_parseia(condicao, por_nome[nome].get("simbolos") or [])
        yield {"alvo": nome, "veredito": VERDE if ok else VERMELHO,
               "detalhe": ("condição %s" if ok else "condição não é relacional sobre os símbolos da equação: %s")
               % condicao}


PROVAS = (("P1", _p1_parse), ("P2", _p2_derivacao), ("P3", _p3_validade))


def provas_sympy(equacoes, derivacoes, validades):
    ctx = {"equacoes": equacoes, "derivacoes": derivacoes, "validades": validades,
           "por_nome": {e["nome"]: e for e in equacoes}}
    linhas = []
    for prova, executar in PROVAS:
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


def _ler_jsonl(caminho, obrigatorio=False):
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
    ap.add_argument("--provas-wolfram", help="provas Wolfram registradas — aceito, mas ainda NÃO usado (a via P4 vem na Task 10)")
    args = ap.parse_args(argv)
    if not recortar_trechos.RE_ONDA.match(args.onda) or ".." in args.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")

    def arquivo(prefixo, ext="jsonl"):
        return os.path.join(args.raiz_esteira, "%s-%s.%s" % (prefixo, args.onda, ext))

    linhas = provas_sympy(_ler_jsonl(arquivo("equacoes"), obrigatorio=True),
                          _ler_jsonl(arquivo("derivacoes")), _ler_jsonl(arquivo("validades")))
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
