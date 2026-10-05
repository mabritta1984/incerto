#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aprovação da onda: o ÚNICO escritor que promove a `aprovado` no grafo, e só com o gate do fiscal.

Lê de `<raiz-esteira>` (padrão `_esteira/incerto`): `equacoes-<onda>.jsonl` (candidatos de
`extrair_equacoes.py`), `derivacoes-`, `validades-`, `fiscal-<onda>.jsonl` (vereditos do `fiscal.py`, sem
`ms`), `provas-<onda>.jsonl` (provas Wolfram) e `decisoes-<onda>.jsonl` (decisões do PO). O modelo do
grafo — nós, relações, chaves e o Cypher canônico de cada MERGE — é dono único em
`references/grafo-incerto.md`.

Gate (`decidir`, função pura), item a item — TODAS as linhas do fiscal do item têm de passar:
  `:Equacao`    P1 verde; toda P3 sobre ela verde (e toda condição de `validades-` com sua P3); se tem
                `momento_fechado`, a P4 do momento verde (e toda P4 de momento sobre ela, sempre).
  `DERIVA_DE`   a P2 da linha de derivação (mae, filha, simbolo, substituicao) E a P4 (mae, filha) verdes,
                e as duas pontas promovíveis. Grava `verificado_por: ["sympy@1.14.0", "wolfram"]`.
  `VALIDA_SOB`  a P3 (equacao, condicao) verde e a equação promovível.
  Passar = `verde`, ou `indeterminado` com decisão `{"tipo": "aceitar_indeterminado", "prova", <chaves
  estruturadas da linha>}` idêntica àquela linha (sem curinga, sem chave a menos ou a mais). `vermelho`
  nunca passa, com ou sem decisão. Item sem linha do fiscal não passa ("sem prova"). O que não passa é
  gravado com `status: 'staging'` e `pendencias` (o que falta), nunca `aprovado`.

Decisões do PO (`decisoes-<onda>.jsonl`), validadas inteiras antes de qualquer escrita; tipo desconhecido
ou decisão malformada recusa a execução (ValueError → saída com a mensagem, nada gravado):
  renomear_variavel     {equacao, simbolo, nome}
  conceito              {nome, tipo_conceito: fenomeno|principio|falacia|regime, definicao, sinonimos, fonte}
                        (`tipo` da linha é o tipo da decisão; o do conceito vai em `tipo_conceito`)
  heuristica            {nome, enunciado, condicao, fonte, sustenta: [nomes de conceito ou equação da onda]}
  aceitar_indeterminado {prova, <chaves estruturadas da linha do fiscal>}
  momento_fechado       {equacao, momento_fechado: {"media": "...", ...}} — aplicado ao candidato por
                        `--aplicar-momentos`, ANTES do fiscal (a P4 e a `impressao` Wolfram leem o momento
                        do candidato); na aprovação, decisão não aplicada recusa a execução.

Antes do gate, o fiscal é refeito (`fiscal.provas`) sobre os arquivos atuais e comparado com
`fiscal-<onda>.jsonl`: se diferirem, o fiscal está desatualizado e nada é feito.

Uso:
  python3 aprovar_onda.py --onda <onda> [--executar] [--corpus incerto] [--raiz-esteira _esteira/incerto]
                          [--database <db>]
  python3 aprovar_onda.py --onda <onda> --aplicar-momentos [--raiz-esteira ...] [--corpus ...]
Sem `--executar`, só imprime o plano (nada é gravado e o banco não é aberto). Todo MERGE vai em lote por
`nucleo.query_com_retentativa`, com Cypher parametrizado (`UNWIND $linhas`).
"""
import argparse
import io
import json
import os
import re
import sys
import tokenize

import fiscal             # vizinhos em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo
import nucleo
import recortar_trechos

CORPUS = "incerto"
APROVADO, STAGING = "aprovado", "staging"
VERDE, VERMELHO, INDETERMINADO = fiscal.VERDE, fiscal.VERMELHO, fiscal.INDETERMINADO
VERIFICADO_POR = ["sympy@1.14.0", "wolfram"]
TIPOS_CONCEITO = ("fenomeno", "principio", "falacia", "regime")

# chaves estruturadas de cada prova (as de `fiscal.py`); a P4 tem duas formas: derivação ou momento
CHAVES_PROVA = {"P1": (("equacao",),), "P2": (("mae", "filha", "simbolo", "substituicao"),),
                "P3": (("equacao", "condicao"),), "P4": (("mae", "filha"), ("equacao",))}

# campos de cada tipo de decisão, além de `tipo` (aceitar_indeterminado é validado à parte)
CAMPOS_DECISAO = {
    "renomear_variavel": ("equacao", "simbolo", "nome"),
    "conceito": ("nome", "tipo_conceito", "definicao", "sinonimos", "fonte"),
    "heuristica": ("nome", "enunciado", "condicao", "fonte", "sustenta"),
    "momento_fechado": ("equacao", "momento_fechado"),
}
TIPOS_DECISAO = tuple(sorted(set(CAMPOS_DECISAO) | {"aceitar_indeterminado"}))

RE_LADO_ESQUERDO = re.compile(r"^Equality\(Symbol\('([^']+)'\),")


# --- utilidades -------------------------------------------------------------------------------------------

def canonico(valor):
    return json.dumps(valor, sort_keys=True, ensure_ascii=False)


def _texto(valor):
    return isinstance(valor, str) and bool(valor.strip())


def validar_fonte(fonte, onde):
    if not isinstance(fonte, dict) or set(fonte) != {"documento", "topico"} \
            or not all(_texto(fonte[k]) for k in fonte):
        raise ValueError("%s: `fonte` tem de ser {documento, topico} com textos não vazios (veio %r)" % (onde, fonte))
    return canonico(fonte)


def identidade(linha):
    """(prova, (chave, valor canônico)…) de uma linha do fiscal ou de um aceite: é o que o aceite casa."""
    prova = linha.get("prova")
    if prova not in CHAVES_PROVA:
        raise ValueError("prova desconhecida: %r" % (prova,))
    formas = CHAVES_PROVA[prova]
    chaves = formas[0] if len(formas) == 1 else (formas[0] if "mae" in linha else formas[1])
    return (prova,) + tuple((k, canonico(linha.get(k))) for k in chaves)


def _validar_linha_fiscal(linha, n):
    try:
        ident = identidade(linha)
    except ValueError as e:
        raise ValueError("fiscal, linha %d: %s" % (n, e))
    if linha.get("veredito") not in fiscal.VEREDITOS:
        raise ValueError("fiscal, linha %d: veredito %r" % (n, linha.get("veredito")))
    if any(linha.get(k) is None for k, _ in ident[1:]):
        raise ValueError("fiscal, linha %d: faltam chaves estruturadas de %s" % (n, ident[0]))


def _simbolos_da_condicao(condicao):
    try:
        return {t.string for t in tokenize.generate_tokens(io.StringIO(condicao).readline) if t.type == tokenize.NAME}
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()


# --- decisões -----------------------------------------------------------------------------------------------

def _validar_aceite(d, n):
    resto = set(d) - {"tipo", "prova"}
    formas = CHAVES_PROVA.get(d.get("prova"))
    if not formas or not any(resto == set(f) for f in formas):
        raise ValueError("decisão %d (aceitar_indeterminado): use `prova` P1..P4 e exatamente as chaves "
                         "estruturadas da linha do fiscal (%s) — veio %s"
                         % (n, "; ".join("%s: %s" % (p, " | ".join(", ".join(f) for f in fs))
                                         for p, fs in sorted(CHAVES_PROVA.items())), sorted(d)))
    for k in resto:
        if d[k] is None or (isinstance(d[k], str) and not d[k].strip()) or d[k] == "*":
            raise ValueError("decisão %d (aceitar_indeterminado): `%s` vazio ou curinga — o aceite nomeia uma "
                             "linha exata" % (n, k))
    if "substituicao" in resto and not isinstance(d["substituicao"], dict):
        raise ValueError("decisão %d (aceitar_indeterminado): `substituicao` tem de ser objeto" % n)


def validar_decisoes(decisoes):
    """Levanta ValueError na primeira decisão de tipo desconhecido ou malformada; devolve-as por tipo."""
    por_tipo = {t: [] for t in TIPOS_DECISAO}
    for n, d in enumerate(decisoes, 1):
        if not isinstance(d, dict) or d.get("tipo") not in TIPOS_DECISAO:
            raise ValueError("decisão %d: tipo desconhecido %r (use %s) — nada é gravado"
                             % (n, d.get("tipo") if isinstance(d, dict) else d, ", ".join(TIPOS_DECISAO)))
        tipo = d["tipo"]
        if tipo == "aceitar_indeterminado":
            _validar_aceite(d, n)
            por_tipo[tipo].append(d)
            continue
        if set(d) != set(CAMPOS_DECISAO[tipo]) | {"tipo"}:
            raise ValueError("decisão %d (%s): chaves %s; esperadas %s"
                             % (n, tipo, sorted(d), sorted(set(CAMPOS_DECISAO[tipo]) | {"tipo"})))
        onde = "decisão %d (%s)" % (n, tipo)
        textos = {"renomear_variavel": ("equacao", "simbolo", "nome"), "conceito": ("nome", "definicao"),
                  "heuristica": ("nome", "enunciado", "condicao"), "momento_fechado": ("equacao",)}[tipo]
        for k in textos:
            if not _texto(d[k]):
                raise ValueError("%s: `%s` vazio ou não texto" % (onde, k))
        if "fonte" in d:
            validar_fonte(d["fonte"], onde)
        if tipo == "conceito":
            if d["tipo_conceito"] not in TIPOS_CONCEITO:
                raise ValueError("%s: tipo_conceito %r (use %s)" % (onde, d["tipo_conceito"], "|".join(TIPOS_CONCEITO)))
            if not isinstance(d["sinonimos"], list) or not all(_texto(s) for s in d["sinonimos"]):
                raise ValueError("%s: `sinonimos` tem de ser lista de textos" % onde)
        if tipo == "heuristica" and (not isinstance(d["sustenta"], list) or not all(_texto(s) for s in d["sustenta"])):
            raise ValueError("%s: `sustenta` tem de ser lista de nomes" % onde)
        if tipo == "momento_fechado":
            m = d["momento_fechado"]
            if not isinstance(m, dict) or not m or not all(_texto(k) and _texto(v) for k, v in m.items()):
                raise ValueError("%s: `momento_fechado` tem de ser objeto não vazio {momento: expressão}" % onde)
        por_tipo[tipo].append(d)
    for tipo, chave in (("renomear_variavel", ("equacao", "simbolo")), ("conceito", ("nome",)),
                        ("heuristica", ("nome",)), ("momento_fechado", ("equacao",))):
        vistos = set()
        for d in por_tipo[tipo]:
            k = tuple(d[c] for c in chave)
            if k in vistos:
                raise ValueError("decisão %s repetida: %s" % (tipo, "/".join(k)))
            vistos.add(k)
    return por_tipo


def aplicar_momentos(equacoes, decisoes):
    """Os candidatos com o `momento_fechado` de cada decisão `momento_fechado` (cópias; ValueError se a
    equação não existir ou a decisão for malformada)."""
    momentos = {d["equacao"]: d["momento_fechado"] for d in validar_decisoes(decisoes)["momento_fechado"]}
    nomes = {e["nome"] for e in equacoes}
    faltam = sorted(set(momentos) - nomes)
    if faltam:
        raise ValueError("momento_fechado de equação desconhecida: %s" % ", ".join(faltam))
    return [dict(e, momento_fechado=momentos[e["nome"]]) if e["nome"] in momentos else dict(e) for e in equacoes]


# --- o gate -------------------------------------------------------------------------------------------------

def _validar_equacoes(equacoes):
    vistos = set()
    for e in equacoes:
        if not _texto(e.get("nome")):
            raise ValueError("candidato sem `nome`: %r" % (e,))
        if e["nome"] in vistos:
            raise ValueError("candidato repetido: %s" % e["nome"])
        vistos.add(e["nome"])
        validar_fonte(e.get("fonte"), "candidato %s" % e["nome"])
        for v in e.get("variaveis") or []:
            if not _texto(v.get("simbolo")) or not _texto(v.get("nome")):
                raise ValueError("candidato %s: variável sem `simbolo`/`nome`: %r" % (e["nome"], v))


def _avaliar(linhas, aceites):
    """(pendências, provas aceitas como indeterminado) de um conjunto de linhas do fiscal."""
    pendencias, aceitas = [], []
    for l in linhas:
        if l["veredito"] == VERDE:
            continue
        if l["veredito"] == INDETERMINADO and identidade(l) in aceites:
            aceitas.append(l["prova"])
            continue
        sufixo = " sem aceite do PO" if l["veredito"] == INDETERMINADO else ""
        pendencias.append("%s %s%s: %s" % (l["prova"], l["veredito"], sufixo, l.get("detalhe")))
    return pendencias, sorted(set(aceitas))


def _indice(fiscal_linhas, prova, *chaves):
    idx = {}
    for l in fiscal_linhas:
        if l["prova"] == prova and all(k in l for k in chaves):
            idx.setdefault(tuple(canonico(l[k]) for k in chaves), []).append(l)
    return idx


def decidir(equacoes, derivacoes, validades, fiscal_linhas, decisoes):
    """O plano da aprovação: cada nó e aresta com `status` (aprovado só se passou no gate), `pendencias`,
    `fonte` (JSON canônico {documento, topico}) e as propriedades do modelo. ValueError se as entradas ou
    as decisões forem inconsistentes — nesse caso nada pode ser gravado."""
    por_tipo = validar_decisoes(decisoes)
    _validar_equacoes(equacoes)
    for n, l in enumerate(fiscal_linhas, 1):
        _validar_linha_fiscal(l, n)
    por_nome = {e["nome"]: e for e in equacoes}
    aceites = {identidade(d) for d in por_tipo["aceitar_indeterminado"]}
    c = canonico

    for d in por_tipo["momento_fechado"]:
        if d["equacao"] not in por_nome:
            raise ValueError("momento_fechado de equação desconhecida: %s" % d["equacao"])
        if por_nome[d["equacao"]].get("momento_fechado") != d["momento_fechado"]:
            raise ValueError("momento_fechado decidido para %s não está no candidato — rode "
                             "`aprovar_onda.py --aplicar-momentos` e o fiscal de novo" % d["equacao"])

    nomes_var = {(e["nome"], v["simbolo"]): v["nome"] for e in equacoes for v in e.get("variaveis") or []}
    for d in por_tipo["renomear_variavel"]:
        if (d["equacao"], d["simbolo"]) not in nomes_var:
            raise ValueError("renomear_variavel: %s não tem a variável de símbolo %s" % (d["equacao"], d["simbolo"]))
        nomes_var[(d["equacao"], d["simbolo"])] = d["nome"]

    p1 = _indice(fiscal_linhas, "P1", "equacao")
    p2 = _indice(fiscal_linhas, "P2", "mae", "filha", "simbolo", "substituicao")
    p3 = _indice(fiscal_linhas, "P3", "equacao", "condicao")
    p3_eq = _indice(fiscal_linhas, "P3", "equacao")
    p4d = _indice(fiscal_linhas, "P4", "mae", "filha")
    p4m = _indice([l for l in fiscal_linhas if "mae" not in l], "P4", "equacao")

    vistas = set()
    for v in validades:
        if v.get("equacao") not in por_nome:
            raise ValueError("validade de equação desconhecida: %r" % v.get("equacao"))
        if not _texto(v.get("condicao")):
            raise ValueError("validade de %s sem `condicao`" % v["equacao"])
        if (v["equacao"], v["condicao"]) in vistas:
            raise ValueError("validade repetida: %s / %s" % (v["equacao"], v["condicao"]))
        vistas.add((v["equacao"], v["condicao"]))
    vistas = set()
    for d in derivacoes:
        desconhecidas = [n for n in (d.get("mae"), d.get("filha")) if n not in por_nome]
        if desconhecidas:
            raise ValueError("derivação com equação desconhecida: %s" % ", ".join(map(str, desconhecidas)))
        if (d["mae"], d["filha"]) in vistas:
            raise ValueError("derivação ambígua de %s a %s — deixe uma só na rodada" % (d["mae"], d["filha"]))
        vistas.add((d["mae"], d["filha"]))

    # equações
    plano_eq, status_eq = [], {}
    for e in equacoes:
        nome = e["nome"]
        k = (c(nome),)
        pend = [] if p1.get(k) else ["sem prova P1"]
        conds = [v["condicao"] for v in validades if v["equacao"] == nome]
        pend += ["sem prova P3 para a condição %s" % cd for cd in conds if not p3.get((c(nome), c(cd)))]
        if e.get("momento_fechado") and not p4m.get(k):
            pend.append("sem prova P4 do momento fechado")
        mais, aceitas = _avaliar(p1.get(k, []) + p3_eq.get(k, []) + p4m.get(k, []), aceites)
        pend += mais
        status_eq[nome] = STAGING if pend else APROVADO
        plano_eq.append({"nome": nome, "latex": e.get("latex"), "sympy_srepr": e.get("srepr"), "forma": e.get("forma"),
                         "momento_fechado": c(e["momento_fechado"]) if e.get("momento_fechado") else None,
                         "hipoteses": None, "faixa_validade": conds, "onda": e.get("onda"), "ordem": e.get("ordem"),
                         "fonte": c(e["fonte"]), "status": status_eq[nome], "pendencias": pend, "aceites_po": aceitas})

    # variáveis: USA, DEFINIDA_POR
    usa, definida, variaveis = [], [], {}
    for e in equacoes:
        grupos = {}
        for v in e.get("variaveis") or []:
            grupos.setdefault(nomes_var[(e["nome"], v["simbolo"])], []).append(v["simbolo"])
        m = RE_LADO_ESQUERDO.match(e.get("srepr") or "")
        esquerdo = m.group(1) if m else None
        for nome_v, simbolos in sorted(grupos.items()):
            simbolos = sorted(set(simbolos))
            papel = "definida" if esquerdo in simbolos else "entrada"
            linha = {"equacao": e["nome"], "variavel": nome_v, "simbolos": simbolos, "papel": papel,
                     "fonte": c(e["fonte"]), "status": status_eq[e["nome"]]}
            usa.append(linha)
            if papel == "definida":
                definida.append({"variavel": nome_v, "equacao": e["nome"], "fonte": linha["fonte"],
                                 "status": linha["status"]})
            atual = variaveis.get(nome_v)
            candidata = {"nome": nome_v, "simbolo": simbolos[0], "fonte": linha["fonte"], "status": linha["status"]}
            if atual is None or (atual["status"] == STAGING and linha["status"] == APROVADO):
                variaveis[nome_v] = candidata
            elif candidata["simbolo"] < atual["simbolo"]:
                atual["simbolo"] = candidata["simbolo"]

    # DERIVA_DE
    plano_der = []
    for d in derivacoes:
        mae, filha = d["mae"], d["filha"]
        k2 = (c(mae), c(filha), c(d.get("alvo")), c(d.get("substituicao") or {}))
        k4 = (c(mae), c(filha))
        pend = ([] if p2.get(k2) else ["sem prova P2"]) + ([] if p4d.get(k4) else ["sem prova P4"])
        mais, aceitas = _avaliar(p2.get(k2, []) + p4d.get(k4, []), aceites)
        pend += mais
        pend += ["%s %s fica em staging" % (papel, n) for papel, n in (("mãe", mae), ("filha", filha))
                 if status_eq[n] != APROVADO]
        status = STAGING if pend else APROVADO
        plano_der.append({"mae": mae, "filha": filha, "passo": d.get("passo"), "simbolo": d.get("alvo"),
                          "substituicao": c(d.get("substituicao") or {}),
                          "verificado_por": list(VERIFICADO_POR) if status == APROVADO else [],
                          "fonte": c(por_nome[filha]["fonte"]), "status": status, "pendencias": pend,
                          "aceites_po": aceitas})

    # VALIDA_SOB: da equação às variáveis cujos símbolos a condição cita
    plano_val, avisos = [], []
    for v in validades:
        nome, cond = v["equacao"], v["condicao"]
        k = (c(nome), c(cond))
        pend = [] if p3.get(k) else ["sem prova P3"]
        mais, aceitas = _avaliar(p3.get(k, []), aceites)
        pend += mais + ([] if status_eq[nome] == APROVADO else ["equação %s fica em staging" % nome])
        citados = _simbolos_da_condicao(cond)
        alvos = sorted({nomes_var[(nome, s)] for s in citados if (nome, s) in nomes_var})
        if not alvos:
            avisos.append("VALIDA_SOB %s / %s não gravada: a condição não cita variável da equação" % (nome, cond))
        for alvo in alvos:
            plano_val.append({"equacao": nome, "variavel": alvo, "condicao": cond, "fonte": c(por_nome[nome]["fonte"]),
                              "status": STAGING if pend else APROVADO, "pendencias": pend, "aceites_po": aceitas})

    # conceitos, heurísticas, SUSTENTA
    conceitos = [{"nome": d["nome"], "tipo": d["tipo_conceito"], "definicao": d["definicao"],
                  "sinonimos": list(d["sinonimos"]), "fonte": c(d["fonte"]), "status": APROVADO}
                 for d in por_tipo["conceito"]]
    nomes_conceito = {d["nome"] for d in conceitos}
    heuristicas, sustenta = [], []
    for d in por_tipo["heuristica"]:
        heuristicas.append({"nome": d["nome"], "enunciado": d["enunciado"], "condicao": d["condicao"],
                            "fonte": c(d["fonte"]), "status": APROVADO})
        for alvo in d["sustenta"]:
            if alvo in nomes_conceito and alvo in por_nome:
                raise ValueError("heurística %s: %s é conceito e equação — nome ambíguo" % (d["nome"], alvo))
            if alvo in nomes_conceito:
                rotulo, status = "Conceito", APROVADO
            elif alvo in por_nome:
                rotulo, status = "Equacao", status_eq[alvo]
            else:
                raise ValueError("heurística %s sustenta %r, que não é conceito decidido nem equação da onda"
                                 % (d["nome"], alvo))
            sustenta.append({"heuristica": d["nome"], "alvo": alvo, "rotulo": rotulo, "fonte": c(d["fonte"]),
                             "status": status})

    nomes_doc = {json.loads(l["fonte"])["documento"] for l in plano_eq + conceitos + heuristicas}
    documentos = [{"nome": n, "fonte": c({"documento": n, "topico": None}), "status": APROVADO}
                  for n in sorted(nomes_doc)]

    for d in por_tipo["aceitar_indeterminado"]:
        casadas = [l for l in fiscal_linhas if identidade(l) == identidade(d)]
        if not casadas:
            avisos.append("aceite sem linha do fiscal correspondente: %s" % c({k: v for k, v in d.items() if k != "tipo"}))
        elif any(l["veredito"] == VERMELHO for l in casadas):
            avisos.append("aceite de linha vermelha ignorado (vermelho nunca promove): %s" % casadas[0].get("alvo"))

    return {"documentos": documentos, "equacoes": plano_eq, "variaveis": [variaveis[k] for k in sorted(variaveis)],
            "usa": usa, "definida_por": definida, "deriva_de": plano_der, "valida_sob": plano_val,
            "conceitos": conceitos, "heuristicas": heuristicas, "sustenta": sustenta, "avisos": avisos}


# --- entradas -----------------------------------------------------------------------------------------------

def arquivo(raiz, prefixo, onda):
    return os.path.join(raiz, "%s-%s.jsonl" % (prefixo, onda))


def carregar_onda(raiz, onda, corpus):
    """Os arquivos da onda; ValueError se faltar candidato ou fiscal, ou se o corpus ou a onda de um
    candidato divergirem (a limpeza e o rebaixamento no banco confiam na `onda` gravada no nó)."""
    for prefixo in ("equacoes", "fiscal"):
        if not os.path.exists(arquivo(raiz, prefixo, onda)):
            raise ValueError("não existe %s — rode %s antes" % (arquivo(raiz, prefixo, onda),
                             "extrair_equacoes.py" if prefixo == "equacoes" else "fiscal.py"))
    dados = {p: fiscal.ler_jsonl(arquivo(raiz, p, onda))
             for p in ("equacoes", "derivacoes", "validades", "fiscal", "decisoes")}
    for e in dados["equacoes"]:
        if e.get("corpus") != corpus:
            raise ValueError("candidato %s é do corpus %r, não de --corpus %r" % (e.get("nome"), e.get("corpus"), corpus))
        if e.get("onda") != onda:
            raise ValueError("candidato %s é da onda %r, não de --onda %r" % (e.get("nome"), e.get("onda"), onda))
    dados["wolfram"] = fiscal.provas_wolfram(arquivo(raiz, "provas", onda))
    return dados


def conferir_fiscal_atual(dados):
    """ValueError se o fiscal refeito agora sobre os arquivos da onda não for o `fiscal-<onda>.jsonl` lido."""
    atual = [{k: v for k, v in l.items() if k != "ms"}
             for l in fiscal.provas(dados["equacoes"], dados["derivacoes"], dados["validades"], dados["wolfram"])]
    if [canonico(l) for l in atual] != [canonico(l) for l in dados["fiscal"]]:
        raise ValueError("fiscal desatualizado: os candidatos, derivações, validades ou provas mudaram depois do "
                         "fiscal-<onda>.jsonl — rode `fiscal.py --onda <onda>` de novo")


# --- escrita ------------------------------------------------------------------------------------------------

# reaprovar a onda substitui as arestas que saem das equações e heurísticas dela (renomear, retirar um
# alvo de `sustenta` ou mudar uma condição não deixa aresta velha para trás)
CYPHER_LIMPAR_ARESTAS = (
    "MATCH (e:Equacao {corpus: $corpus, onda: $onda})-[r:USA|VALIDA_SOB|DERIVA_DE]->() DELETE r",
    "MATCH ()-[r:DEFINIDA_POR]->(e:Equacao {corpus: $corpus, onda: $onda}) DELETE r",
    "MATCH (h:Heuristica {corpus: $corpus, onda: $onda})-[r:SUSTENTA]->() DELETE r",
)

# `:Equacao` é chaveada por {corpus, nome}: se o nome já existe em outra onda, o MERGE tomaria o nó dela
CYPHER_COLISOES = ("MATCH (e:Equacao {corpus: $corpus}) WHERE e.nome IN $nomes AND e.onda <> $onda "
                   "RETURN e.nome, e.onda ORDER BY e.nome")

# nós da onda (com `onda` gravada) que já estão no banco: o que não está no plano atual é rebaixado
CYPHER_NOS_DA_ONDA = ("MATCH (n {corpus: $corpus, onda: $onda}) WHERE n:Equacao OR n:Conceito OR n:Heuristica "
                      "RETURN [r IN labels(n) WHERE r IN ['Equacao', 'Conceito', 'Heuristica']][0], n.nome "
                      "ORDER BY n.nome")

PENDENCIA_FORA = "fora da rodada atual"
CYPHER_REBAIXAR = """
UNWIND $linhas AS l
MATCH (n {corpus: $corpus, onda: $onda, nome: l.nome})
WHERE l.rotulo IN labels(n)
SET n.status = 'staging', n.pendencias = [$pendencia]
"""

CYPHER_DOCUMENTOS = """
UNWIND $linhas AS l
MERGE (d:Documento {corpus: $corpus, nome: l.nome})
SET d.status = l.status, d.fonte = l.fonte
"""

CYPHER_EQUACOES = """
UNWIND $linhas AS l
MERGE (e:Equacao {corpus: $corpus, nome: l.nome})
SET e.latex = l.latex, e.sympy_srepr = l.sympy_srepr, e.forma = l.forma, e.momento_fechado = l.momento_fechado,
    e.hipoteses = l.hipoteses, e.faixa_validade = l.faixa_validade, e.onda = l.onda, e.ordem = l.ordem,
    e.status = l.status, e.fonte = l.fonte, e.pendencias = l.pendencias, e.aceites_po = l.aceites_po
"""

CYPHER_VARIAVEIS = """
UNWIND $linhas AS l
MERGE (v:Variavel {corpus: $corpus, nome: l.nome})
ON CREATE SET v.simbolo = l.simbolo, v.fonte = l.fonte, v.status = l.status
"""

CYPHER_USA = """
UNWIND $linhas AS l
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MERGE (e)-[r:USA {corpus: $corpus}]->(v)
SET r.papel = l.papel, r.simbolos = l.simbolos, r.status = l.status, r.fonte = l.fonte
"""

CYPHER_DEFINIDA_POR = """
UNWIND $linhas AS l
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MERGE (v)-[r:DEFINIDA_POR {corpus: $corpus}]->(e)
SET r.status = l.status, r.fonte = l.fonte
"""

CYPHER_DERIVA_DE = """
UNWIND $linhas AS l
MATCH (f:Equacao {corpus: $corpus, nome: l.filha})
MATCH (m:Equacao {corpus: $corpus, nome: l.mae})
MERGE (f)-[r:DERIVA_DE {corpus: $corpus}]->(m)
SET r.passo = l.passo, r.simbolo = l.simbolo, r.substituicao = l.substituicao, r.verificado_por = l.verificado_por,
    r.status = l.status, r.fonte = l.fonte, r.pendencias = l.pendencias, r.aceites_po = l.aceites_po
"""

CYPHER_VALIDA_SOB = """
UNWIND $linhas AS l
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MERGE (e)-[r:VALIDA_SOB {corpus: $corpus, condicao: l.condicao}]->(v)
SET r.status = l.status, r.fonte = l.fonte, r.pendencias = l.pendencias, r.aceites_po = l.aceites_po
"""

# status da variável: aprovada se alguma equação aprovada a USA por aresta aprovada (em qualquer onda);
# variável que nenhuma equação usa mais (renomeada) sai do grafo
CYPHER_STATUS_VARIAVEIS = """
MATCH (v:Variavel {corpus: $corpus})
SET v.status = CASE WHEN EXISTS { MATCH (:Equacao {corpus: $corpus, status: 'aprovado'})
                                  -[:USA {corpus: $corpus, status: 'aprovado'}]->(v) }
                    THEN 'aprovado' ELSE 'staging' END
"""

CYPHER_VARIAVEIS_ORFAS = """
MATCH (v:Variavel {corpus: $corpus})
WHERE NOT EXISTS { MATCH (:Equacao)-[:USA]->(v) }
DETACH DELETE v
"""

CYPHER_CONCEITOS = """
UNWIND $linhas AS l
MERGE (c:Conceito {corpus: $corpus, nome: l.nome})
SET c.tipo = l.tipo, c.definicao = l.definicao, c.sinonimos = l.sinonimos, c.onda = $onda, c.status = l.status,
    c.fonte = l.fonte
"""

CYPHER_HEURISTICAS = """
UNWIND $linhas AS l
MERGE (h:Heuristica {corpus: $corpus, nome: l.nome})
SET h.enunciado = l.enunciado, h.condicao = l.condicao, h.onda = $onda, h.status = l.status, h.fonte = l.fonte
"""

CYPHER_SUSTENTA_CONCEITO = """
UNWIND $linhas AS l
MATCH (h:Heuristica {corpus: $corpus, nome: l.heuristica})
MATCH (x:Conceito {corpus: $corpus, nome: l.alvo})
MERGE (h)-[r:SUSTENTA {corpus: $corpus}]->(x)
SET r.status = l.status, r.fonte = l.fonte
"""

CYPHER_SUSTENTA_EQUACAO = CYPHER_SUSTENTA_CONCEITO.replace("(x:Conceito", "(x:Equacao")


def a_rebaixar(existentes, plano):
    """[(rotulo, nome)] dos nós da onda já no banco (`existentes`) que o plano atual não grava: equação que
    saiu de `equacoes-`, conceito ou heurística cuja decisão saiu de `decisoes-`. Rebaixados, nunca apagados."""
    no_plano = {("Equacao", l["nome"]) for l in plano["equacoes"]} | \
               {("Conceito", l["nome"]) for l in plano["conceitos"]} | \
               {("Heuristica", l["nome"]) for l in plano["heuristicas"]}
    return sorted({(r, n) for r, n in existentes} - no_plano)


def gravar(cred, db, plano, corpus, onda, saida=print):
    """Grava o plano em lotes, na ordem nós → arestas. Antes de qualquer escrita, recusa (ValueError) se um
    nome de equação do plano já existe no banco em outra onda. Reaprovar a onda substitui as arestas dela e
    rebaixa a `staging` o nó da onda que saiu da rodada (nada fica `aprovado` de uma rodada anterior)."""
    def lote(cypher, linhas, extra=None):
        if linhas:
            nucleo.query_com_retentativa(cred, db, cypher, dict({"corpus": corpus, "linhas": linhas}, **(extra or {})))

    colisoes = nucleo.query_com_retentativa(cred, db, CYPHER_COLISOES, {
        "corpus": corpus, "onda": onda, "nomes": [l["nome"] for l in plano["equacoes"]]})
    if colisoes:
        raise ValueError("equação já existe no grafo em outra onda — renomeie na rodada: %s"
                         % "; ".join("%s (onda %s)" % (n, o) for n, o in colisoes))
    existentes = nucleo.query_com_retentativa(cred, db, CYPHER_NOS_DA_ONDA, {"corpus": corpus, "onda": onda})
    rebaixar = a_rebaixar([tuple(r) for r in existentes], plano)
    lote(CYPHER_REBAIXAR, [{"rotulo": r, "nome": n} for r, n in rebaixar], {"onda": onda, "pendencia": PENDENCIA_FORA})
    for r, n in rebaixar:
        saida("rebaixado a staging (%s): %s %s" % (PENDENCIA_FORA, r, n))
    for cypher in CYPHER_LIMPAR_ARESTAS:
        nucleo.query_com_retentativa(cred, db, cypher, {"corpus": corpus, "onda": onda})
    lote(CYPHER_DOCUMENTOS, plano["documentos"])
    lote(CYPHER_EQUACOES, plano["equacoes"])
    lote(CYPHER_VARIAVEIS, plano["variaveis"])
    lote(CYPHER_CONCEITOS, plano["conceitos"], {"onda": onda})
    lote(CYPHER_HEURISTICAS, plano["heuristicas"], {"onda": onda})
    lote(CYPHER_USA, plano["usa"])
    lote(CYPHER_DEFINIDA_POR, plano["definida_por"])
    lote(CYPHER_DERIVA_DE, plano["deriva_de"])
    lote(CYPHER_VALIDA_SOB, plano["valida_sob"])
    lote(CYPHER_SUSTENTA_CONCEITO, [s for s in plano["sustenta"] if s["rotulo"] == "Conceito"])
    lote(CYPHER_SUSTENTA_EQUACAO, [s for s in plano["sustenta"] if s["rotulo"] == "Equacao"])
    nucleo.query_com_retentativa(cred, db, CYPHER_VARIAVEIS_ORFAS, {"corpus": corpus})
    nucleo.query_com_retentativa(cred, db, CYPHER_STATUS_VARIAVEIS, {"corpus": corpus})
    saida("gravado no database %s, corpus %s" % (db, corpus))


# --- relato -------------------------------------------------------------------------------------------------

def linhas_do_plano(plano):
    out = []
    for tipo, rotulo in (("equacoes", "Equacao"), ("deriva_de", "DERIVA_DE"), ("valida_sob", "VALIDA_SOB")):
        linhas = plano[tipo]
        aprov = sum(1 for l in linhas if l["status"] == APROVADO)
        out.append("%s: %d aprovado(s), %d em staging" % (rotulo, aprov, len(linhas) - aprov))
        for l in linhas:
            nome = l.get("nome") or ("%s → %s" % (l["filha"], l["mae"]) if tipo == "deriva_de"
                                     else "%s / %s → %s" % (l["equacao"], l["condicao"], l["variavel"]))
            aceite = " (indeterminado aceito pelo PO: %s)" % ", ".join(l["aceites_po"]) if l["aceites_po"] else ""
            out.append("  %-8s %s%s" % (l["status"], nome, aceite))
            out += ["           - %s" % p for p in l["pendencias"]]
    for tipo in ("variaveis", "usa", "definida_por", "conceitos", "heuristicas", "sustenta", "documentos"):
        aprov = sum(1 for l in plano[tipo] if l["status"] == APROVADO)
        out.append("%s: %d (%d aprovado(s))" % (tipo, len(plano[tipo]), aprov))
    out += ["AVISO: %s" % a for a in plano["avisos"]]
    return out


def _gravar_jsonl(caminho, linhas):
    temporario = caminho + ".tmp"
    try:
        with io.open(temporario, "w", encoding="utf-8", newline="\n") as f:
            for l in linhas:
                f.write(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n")
        os.replace(temporario, caminho)
    except BaseException:
        if os.path.exists(temporario):
            os.remove(temporario)
        raise


def main(argv=None, banco=None):
    """`banco` = (cred, db) já aberto (testes); sem ele, `--executar` abre por `nucleo.abrir_banco`."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onda", required=True)
    ap.add_argument("--raiz-esteira", default="_esteira/incerto")
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--database")
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--executar", action="store_true", help="grava no grafo (sem ele, só imprime o plano)")
    modo.add_argument("--aplicar-momentos", action="store_true",
                      help="grava os momento_fechado decididos em equacoes-<onda>.jsonl (antes do fiscal)")
    a = ap.parse_args(argv)
    if not recortar_trechos.RE_ONDA.match(a.onda) or ".." in a.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")

    if a.aplicar_momentos:
        caminho = arquivo(a.raiz_esteira, "equacoes", a.onda)
        try:
            equacoes = fiscal.ler_jsonl(caminho, obrigatorio=True)
            novas = aplicar_momentos(equacoes, fiscal.ler_jsonl(arquivo(a.raiz_esteira, "decisoes", a.onda)))
        except ValueError as e:
            sys.exit("recusado — %s" % e)
        _gravar_jsonl(caminho, novas)
        mudaram = sum(1 for x, y in zip(equacoes, novas) if x != y)
        print("%s: %d candidato(s) com momento_fechado novo — rode fiscal.py (e a prova Wolfram do momento) "
              "antes de aprovar" % (caminho, mudaram))
        return 0

    try:
        dados = carregar_onda(a.raiz_esteira, a.onda, a.corpus)
        plano = decidir(dados["equacoes"], dados["derivacoes"], dados["validades"], dados["fiscal"], dados["decisoes"])
        conferir_fiscal_atual(dados)
    except ValueError as e:
        sys.exit("recusado, nada gravado — %s" % e)
    print("onda %s, corpus %s" % (a.onda, a.corpus))
    for linha in linhas_do_plano(plano):
        print(linha)
    if not a.executar:
        print("nada gravado (sem --executar)")
        return 0
    cred, db = banco if banco else nucleo.abrir_banco(a.database)[:2]
    try:
        gravar(cred, db, plano, a.corpus, a.onda)
    except ValueError as e:
        sys.exit("recusado — %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
