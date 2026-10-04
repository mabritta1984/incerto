#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingestão idempotente e retomável dos trechos verbatim (JSONL de `recortar_trechos.py`) no Neo4j.

Cada linha vira `(:Trecho {corpus, documento, topico, parte})` com `texto` verbatim, `onda`, `ordem` e
`embedding_gemini` (Vertex `gemini-embedding-2`, `nucleo.GEMINI_DIM` floats), mais `(:Documento {corpus, nome})`
e a aresta `(t)-[:PERTENCE_A]->(d)`. Parte ≥2 de tópico partido traz `cabecalho`: o vetor é de
`cabecalho + "\\n" + texto`, mas o nó guarda só o `texto` (verbatim) e, quando presentes, `junta` e `cabecalho`.

Idempotência: MERGE pela chave `{corpus, documento, topico, parte}`; reexecutar não duplica. Retomada: o
state (`{"gravadas": [chaves ordenadas]}`) é regravado após cada lote; chaves nele não são re-embedadas.
Toda linha deve trazer `corpus` igual a `--corpus` (default `incerto`): senão ValueError antes de qualquer
chamada de rede. Só este script (e `aprovar_onda.py`) escreve no grafo.

Uso:
  python3 ingerir_trechos.py --entrada _esteira/incerto/trechos-<onda>.jsonl \
      [--state _esteira/incerto/ingestao-<onda>.json] [--corpus incerto] [--database <db>]
  python3 ingerir_trechos.py --verificar [--corpus incerto] [--database <db>]
"""
import argparse
import io
import json
import os
import sys

import nucleo   # vizinho em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo

CORPUS = "incerto"
LOTE = 16
INDICE_VETORIAL = "trecho_embedding_incerto"
INDICE_TEXTO = "trecho_texto_incerto"
OBRIGATORIOS = ("documento", "topico", "parte", "ordem", "onda", "texto")

DDL = [
    "CREATE VECTOR INDEX %s IF NOT EXISTS FOR (t:Trecho) ON t.embedding_gemini "
    "OPTIONS { indexConfig: { `vector.dimensions`: %d, `vector.similarity_function`: 'cosine' } }"
    % (INDICE_VETORIAL, nucleo.GEMINI_DIM),
    "CREATE FULLTEXT INDEX %s IF NOT EXISTS FOR (t:Trecho) ON EACH [t.texto]" % INDICE_TEXTO,
]

CYPHER_GRAVAR = """
UNWIND $linhas AS l
MERGE (d:Documento {corpus: $corpus, nome: l.documento})
MERGE (t:Trecho {corpus: $corpus, documento: l.documento, topico: l.topico, parte: l.parte})
SET t.texto = l.texto, t.onda = l.onda, t.ordem = l.ordem, t.embedding_gemini = l.embedding,
    t.junta = l.junta, t.cabecalho = l.cabecalho
MERGE (t)-[:PERTENCE_A]->(d)
"""

CYPHER_POR_ONDA = "MATCH (t:Trecho {corpus: $corpus}) RETURN t.onda, count(t) ORDER BY t.onda"
CYPHER_DUPLICADAS = ("MATCH (t:Trecho {corpus: $corpus}) "
                     "WITH t.documento AS d, t.topico AS tp, t.parte AS p, count(*) AS n WHERE n > 1 "
                     "RETURN d, tp, p, n ORDER BY d, tp, p")
CYPHER_DIMENSAO = ("MATCH (t:Trecho {corpus: $corpus}) "
                   "WHERE t.embedding_gemini IS NULL OR size(t.embedding_gemini) <> $dim "
                   "RETURN t.documento, t.topico, t.parte, size(t.embedding_gemini) "
                   "ORDER BY t.documento, t.topico, t.parte")


def chave_trecho(linha):
    """Chave do trecho no state: [documento, topico, parte] canônicos (NFC) em JSON — sem ambiguidade."""
    return json.dumps([nucleo.chave(linha["documento"]), nucleo.chave(linha["topico"], caminho=False),
                       linha["parte"]], ensure_ascii=False)


def ler_trechos(caminho, corpus):
    """Lê e valida o JSONL inteiro antes de qualquer rede: ValueError se faltar `corpus`, se divergir de
    `corpus`, ou se faltar campo obrigatório."""
    linhas = []
    with io.open(caminho, encoding="utf-8", newline="") as f:
        for n, bruta in enumerate(f, 1):
            if not bruta.strip():
                continue
            try:
                l = json.loads(bruta)
            except ValueError as e:
                raise ValueError("%s:%d: JSON inválido (%s)" % (caminho, n, e))
            if not l.get("corpus"):
                raise ValueError("%s:%d: linha sem `corpus` — nada é gravado sem partição" % (caminho, n))
            if l["corpus"] != corpus:
                raise ValueError("%s:%d: corpus %r difere de --corpus %r" % (caminho, n, l["corpus"], corpus))
            faltam = [c for c in OBRIGATORIOS if l.get(c) is None]
            if faltam:
                raise ValueError("%s:%d: campos ausentes: %s" % (caminho, n, ", ".join(faltam)))
            linhas.append(l)
    return linhas


def texto_para_embedding(linha):
    """Parte ≥2 embeda cabeçalho + texto (P-AK); o que se grava continua sendo só `texto`."""
    return linha["cabecalho"] + "\n" + linha["texto"] if linha.get("cabecalho") else linha["texto"]


def ler_state(caminho):
    if not caminho or not os.path.exists(caminho):
        return set()
    with io.open(caminho, encoding="utf-8") as f:
        return set(json.load(f).get("gravadas") or [])


def gravar_state(caminho, gravadas):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"gravadas": sorted(gravadas)}, f, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def garantir_indices(cred, db):
    for ddl in DDL:
        nucleo.query_com_retentativa(cred, db, ddl, {})


def ingerir(cred, db, linhas, corpus, caminho_state, saida=print):
    """Grava `linhas` (já validadas) em lotes de LOTE. Devolve (gravadas_agora, recusadas): `recusadas` são
    trechos acima do limite do modelo — nunca truncados, ficam fora do state para nova tentativa."""
    gravadas = ler_state(caminho_state)
    pendentes = [l for l in linhas if chave_trecho(l) not in gravadas]
    saida("%d trecho(s): %d já no state, %d a gravar" % (len(linhas), len(linhas) - len(pendentes), len(pendentes)))
    if not pendentes:
        return 0, []
    garantir_indices(cred, db)
    agora, recusadas = 0, []
    for i in range(0, len(pendentes), LOTE):
        lote = pendentes[i:i + LOTE]
        vetores, _tokens = nucleo.embed_gemini(cred, [texto_para_embedding(l) for l in lote])
        linhas_db, chaves = [], []
        for l, v in zip(lote, vetores):
            if v is None:
                recusadas.append(l)
                saida("RECUSADO (acima de %d tokens, nunca truncado): %s / %s / parte %s"
                      % (nucleo.GEMINI_LIMITE_TOKENS, l["documento"], l["topico"], l["parte"]))
                continue
            linhas_db.append({"documento": nucleo.chave(l["documento"]),
                              "topico": nucleo.chave(l["topico"], caminho=False), "parte": l["parte"],
                              "ordem": l["ordem"], "onda": l["onda"], "texto": l["texto"],
                              "junta": l.get("junta"), "cabecalho": l.get("cabecalho"), "embedding": v})
            chaves.append(chave_trecho(l))
        if linhas_db:
            nucleo.query_com_retentativa(cred, db, CYPHER_GRAVAR, {"corpus": corpus, "linhas": linhas_db})
            gravadas.update(chaves)
            gravar_state(caminho_state, gravadas)
            agora += len(linhas_db)
        saida("lote %d: %d gravado(s)" % (i // LOTE + 1, len(linhas_db)))
    return agora, recusadas


def avaliar_verificacao(por_onda, duplicadas, dimensao_errada):
    """Pura: (linhas de relato, ok) a partir das três consultas de `--verificar`."""
    out = ["contagem por onda:"]
    out += ["  %s: %d" % (onda, n) for onda, n in por_onda] or ["  (nenhum trecho)"]
    ok = bool(por_onda)
    if not por_onda:
        out.append("✘ nenhum trecho no corpus")
    if duplicadas:
        ok = False
        out.append("✘ %d chave(s) duplicada(s):" % len(duplicadas))
        out += ["    %s / %s / parte %s: %d nós" % tuple(r) for r in duplicadas]
    else:
        out.append("✔ nenhuma chave duplicada")
    if dimensao_errada:
        ok = False
        out.append("✘ %d trecho(s) com embedding de dimensão ≠ %d:" % (len(dimensao_errada), nucleo.GEMINI_DIM))
        out += ["    %s / %s / parte %s: tamanho %s" % tuple(r) for r in dimensao_errada]
    else:
        out.append("✔ todos os embeddings têm %d dimensões" % nucleo.GEMINI_DIM)
    return out, ok


def verificar(cred, db, corpus, saida=print):
    p = {"corpus": corpus}
    linhas, ok = avaliar_verificacao(
        nucleo.query_api(cred, db, CYPHER_POR_ONDA, p),
        nucleo.query_api(cred, db, CYPHER_DUPLICADAS, p),
        nucleo.query_api(cred, db, CYPHER_DIMENSAO, dict(p, dim=nucleo.GEMINI_DIM)))
    for l in linhas:
        saida(l)
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entrada", help="JSONL de recortar_trechos.py")
    ap.add_argument("--state", help="default: _esteira/incerto/ingestao-<onda>.json")
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--database")
    ap.add_argument("--verificar", action="store_true", help="só confere o banco; exit 1 se algo falhar")
    a = ap.parse_args(argv)
    if not a.verificar and not a.entrada:
        ap.error("--entrada é obrigatório (exceto com --verificar)")
    linhas = ler_trechos(a.entrada, a.corpus) if a.entrada else []      # ValueError antes de qualquer rede
    cred, db, _consultar = nucleo.abrir_banco(a.database)
    if a.verificar:
        return 0 if verificar(cred, db, a.corpus) else 1
    ondas = sorted({l["onda"] for l in linhas})
    if not a.state and len(ondas) != 1:
        ap.error("--state é obrigatório quando a entrada não tem exatamente uma onda (%s)" % ", ".join(ondas))
    state = a.state or os.path.join("_esteira", "incerto", "ingestao-%s.json" % ondas[0])
    _n, recusadas = ingerir(cred, db, linhas, a.corpus, state)
    return 1 if recusadas else 0


if __name__ == "__main__":
    sys.exit(main())
