#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingestão idempotente e retomável dos trechos verbatim (JSONL de `recortar_trechos.py`) no Neo4j.

Cada linha vira `(:Trecho {corpus, documento, topico, parte})` com `texto` verbatim, `onda`, `ordem` e
`embedding_gemini` (Vertex `gemini-embedding-2`, `nucleo.GEMINI_DIM` floats), mais `(:Documento {corpus, nome})`
e a aresta `(t)-[:PERTENCE_A]->(d)`. Parte ≥2 de tópico partido traz `cabecalho`: o vetor é de
`cabecalho + "\\n" + texto`, mas o nó guarda só o `texto` (verbatim) e, quando presentes, `junta` e `cabecalho`.

Idempotência: MERGE pela chave `{corpus, documento, topico, parte}`; reexecutar não duplica. Retomada: o
state (`{"corpus": ..., "gravadas": [chaves ordenadas]}`; de outro corpus é recusado) é regravado após cada lote; chaves nele não são re-embedadas.
Toda linha deve trazer `corpus` igual a `--corpus` (default `incerto`): senão ValueError antes de qualquer
chamada de rede. Só este script (e `aprovar_onda.py`) escreve no grafo.

Uso:
  python3 ingerir_trechos.py --entrada _esteira/incerto/trechos-<onda>.jsonl \
      [--state _esteira/incerto/ingestao-<onda>.json] [--corpus incerto] [--database <db>]
  python3 ingerir_trechos.py --verificar [--corpus incerto] [--database <db>]
`--verificar` confere contagem por onda, chaves duplicadas, dimensão dos embeddings e, por `SHOW INDEXES`, que
`trecho_embedding_incerto` (VECTOR, `nucleo.GEMINI_DIM` dimensões quando expostas) e `trecho_texto_incerto`
(FULLTEXT) existem com esses nomes sobre `:Trecho` — no Aura compartilhado, `IF NOT EXISTS` não cria nada se o
nome já é de outro índice; ausente, a falha nomeia o equivalente sobre `:Trecho` que exista com outro nome.
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
# o Aura é compartilhado: `CREATE … IF NOT EXISTS` não cria nada se o nome já existe (talvez de outro rótulo)
CYPHER_INDICES = ("SHOW INDEXES YIELD name, type, labelsOrTypes, properties, options "
                  "RETURN name, type, labelsOrTypes, properties, options ORDER BY name")
# nome → (tipo, propriedade de :Trecho) que o índice tem de ter
INDICES = {INDICE_VETORIAL: ("VECTOR", "embedding_gemini"), INDICE_TEXTO: ("FULLTEXT", "texto")}
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


def ler_state(caminho, corpus):
    """Chaves já gravadas. State de outro corpus (ou legado, sem `corpus`) é recusado: reaproveitá-lo
    pularia tudo em silêncio, ignorá-lo sobrescreveria o state alheio."""
    if not caminho or not os.path.exists(caminho):
        return set()
    with io.open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("corpus") != corpus:
        raise ValueError("state %s é do corpus %r, não de --corpus %r — use outro --state"
                         % (caminho, dados.get("corpus"), corpus))
    return set(dados.get("gravadas") or [])


def gravar_state(caminho, gravadas, corpus):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"corpus": corpus, "gravadas": sorted(gravadas)}, f, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def garantir_indices(cred, db):
    for ddl in DDL:
        nucleo.query_com_retentativa(cred, db, ddl, {})


def ingerir(cred, db, linhas, corpus, caminho_state, saida=print):
    """Grava `linhas` (já validadas) em lotes de LOTE. Devolve (gravadas_agora, recusadas): `recusadas` são
    trechos acima do limite do modelo — nunca truncados, ficam fora do state para nova tentativa."""
    gravadas = ler_state(caminho_state, corpus)
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
            gravar_state(caminho_state, gravadas, corpus)
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


def _dimensao(opcoes):
    """`vector.dimensions` das `options` de `SHOW INDEXES`, ou None se o servidor não a expõe."""
    config = (opcoes or {}).get("indexConfig") if isinstance(opcoes, dict) else None
    return config.get("vector.dimensions") if isinstance(config, dict) else None


def avaliar_indices(linhas_indices):
    """Pura: (linhas de relato, ok) a partir das linhas de `CYPHER_INDICES` (name, type, labelsOrTypes,
    properties, options). Cada índice de `INDICES` tem de existir com esse nome, sobre `:Trecho`, com o tipo e
    a propriedade dele (e o vetorial com `nucleo.GEMINI_DIM` dimensões, quando o servidor as expõe). Ausente →
    falha que nomeia o índice equivalente sobre `:Trecho` que exista com outro nome."""
    por_nome = {r[0]: r for r in linhas_indices}
    out, ok = [], True
    for nome, (tipo, prop) in sorted(INDICES.items()):
        equivalentes = sorted(r[0] for r in linhas_indices if r[0] != nome and r[1] == tipo
                              and "Trecho" in (r[2] or []) and prop in (r[3] or []))
        r = por_nome.get(nome)
        if r is None:
            ok = False
            out.append("✘ índice %s ausente%s" % (nome, " — há equivalente sobre :Trecho(%s) com outro nome: %s"
                                                  % (prop, ", ".join(equivalentes)) if equivalentes else ""))
            continue
        if r[1] != tipo or list(r[2] or []) != ["Trecho"] or list(r[3] or []) != [prop]:
            ok = False
            out.append("✘ índice %s existe com outra definição (%s em %s(%s); esperado %s em Trecho(%s)) — nome "
                       "tomado por outro índice no banco compartilhado%s"
                       % (nome, r[1], ",".join(r[2] or []), ",".join(r[3] or []), tipo, prop,
                          "; equivalente com outro nome: %s" % ", ".join(equivalentes) if equivalentes else ""))
            continue
        dim = _dimensao(r[4]) if len(r) > 4 else None
        if tipo == "VECTOR" and dim is not None and dim != nucleo.GEMINI_DIM:
            ok = False
            out.append("✘ índice %s com %s dimensões; esperado %d" % (nome, dim, nucleo.GEMINI_DIM))
            continue
        out.append("✔ índice %s: %s em Trecho(%s)%s" % (nome, tipo, prop, ", %s dimensões" % dim if dim else ""))
    return out, ok


def verificar(cred, db, corpus, saida=print):
    p = {"corpus": corpus}
    linhas, ok = avaliar_verificacao(
        nucleo.query_api(cred, db, CYPHER_POR_ONDA, p),
        nucleo.query_api(cred, db, CYPHER_DUPLICADAS, p),
        nucleo.query_api(cred, db, CYPHER_DIMENSAO, dict(p, dim=nucleo.GEMINI_DIM)))
    linhas_ind, ok_ind = avaliar_indices(nucleo.query_api(cred, db, CYPHER_INDICES))
    for l in linhas + linhas_ind:
        saida(l)
    return ok and ok_ind


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
    if a.verificar:
        cred, db, _consultar = nucleo.abrir_banco(a.database)
        return 0 if verificar(cred, db, a.corpus) else 1
    ondas = sorted({l["onda"] for l in linhas})
    if not a.state and len(ondas) != 1:
        ap.error("--state é obrigatório quando a entrada não tem exatamente uma onda (%s)" % ", ".join(ondas))
    state = a.state or os.path.join("_esteira", "incerto", "ingestao-%s.json" % ondas[0])
    ler_state(state, a.corpus)                                          # ValueError antes de qualquer rede
    cred, db, _consultar = nucleo.abrir_banco(a.database)
    _n, recusadas = ingerir(cred, db, linhas, a.corpus, state)
    return 1 if recusadas else 0


if __name__ == "__main__":
    sys.exit(main())
