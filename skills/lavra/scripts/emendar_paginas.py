#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emenda de páginas reconvertidas ("reparo", decisão do PO de 05/10/2026) no `.md` de uma onda.

O `mineiro` reconverte só documentos inteiros. Quando uma faixa de páginas se perde (ex.: HTTP 429 em
Dynamic_Hedging.pdf, pp. 321–340, onda 2026-10-TALEB-1), o PO converte só aquelas páginas como sub-PDF
numa onda própria (`extraidos/<onda-reparo>/<documento-reparo>`, numerado de 1 a N) e este script troca a
nota `> ⚠️ [fallback] páginas A-B não convertida(s) …` do `.md` alvo pelo `.md` do reparo, entre
marcadores:

    <!-- reparo: páginas A-B, onda <onda-reparo>, relatório sha256 <sha256 do .report.json do reparo> -->
    <conteúdo do .md do reparo>
    <!-- fim do reparo: páginas A-B -->

(`página A` quando A = B.) Os assets do reparo são copiados para `<documento>.assets/` com o prefixo
`reparo-pA-B-` e as referências do texto emendado são reescritas. O registro da emenda vai para o
sidecar `<documento>.reparos.json` (lista, um registro por faixa), que o portão `conferir_onda.py` lê.
O `.report.json` do `mineiro` NUNCA é alterado (procedência).

O registro também guarda `source`, `sha256_original` (do sub-PDF, quando legível no mesmo disco), tokens,
tempos e custo do relatório do reparo; o portão rederiva do relatório o que dá para rederivar e confere.

Pré-condição: a emenda vem ANTES do portão e do recorte/extração. Recusa se o documento já está em
`conferidos/<onda>/` ou se já há `trechos-<onda>.jsonl` / `equacoes-<onda>.jsonl` em `--esteira` (default
`_esteira/incerto`) ou em `<raiz>/_esteira/incerto` — a emenda mudaria tópicos e a ordem das equações já citadas.

Recusa (saída 1, nada gravado) também quando: o nome do documento do reparo não termina em `_pA-B.<ext>`
(`_pA.<ext>` quando A = B) com a faixa de `--paginas` e a extensão do alvo; o mesmo relatório (sha256) ou o
mesmo documento de reparo já foi usado em outra faixa; o `.md` alvo não tem exatamente uma nota `[fallback]`
para a faixa; o `.md` alvo já não é o de depois do último reparo (alterado fora do reparo); já há reparo para a
faixa (idempotência: recusa, não reaplica); a faixa tem mais páginas do que as `paginas_falhas` ainda não
reparadas do alvo; o relatório do reparo tem `paginas_falhas` > 0, ou um número de páginas diferente de
B-A+1 (quando o relatório o informa); o reparo não passa na conferência do `conferir_onda.py` (mesmas
regras de perda silenciosa, KaTeX, LaTeX inválido); o texto do reparo cita asset que não existe; ou um
asset prefixado já existe no alvo (colisão).

Escrita e RECUPERAÇÃO: copia os assets, grava sidecar e `.md` em `*.reparo-tmp`, troca o sidecar e, por
último, o `.md` (`os.replace`). Se o processo cair no meio, o `.md` alvo ou está intacto (com a nota) ou está
emendado por inteiro. Intacto: apague os `<documento>.assets/reparo-pA-B-*`, os `*.reparo-tmp` e — se a troca
do sidecar já ocorreu (o portão acusa "md alterado fora do reparo") — o último registro do sidecar (o arquivo
inteiro, se era o único), e rode de novo. Emendado: nada a fazer.

Uso:
    python3 skills/lavra/scripts/emendar_paginas.py --raiz <corpus> --onda <onda> --documento <nome.pdf> \
        --onda-reparo <onda> --documento-reparo <nome_pA-B.pdf> --paginas A-B [--esteira _esteira/incerto]
Saída: 0 emendado; 1 recusado; 2 em erro de uso. Só biblioteca padrão.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys

import conferir_onda as co   # vizinho: mesmas regras do portão (decisão do PO: reutilizar, não duplicar)

RE_FAIXA = re.compile(r"^([0-9]+)(?:-([0-9]+))?$")
CAMPOS_PAGINAS = ("paginas", "paginas_total", "total_paginas")   # o `mineiro` atual não informa nenhum


class Recusa(Exception):
    """A emenda não é aplicada; nada foi gravado."""


def faixa(texto):
    """`A-B` ou `A` → (A, B), com 1 <= A <= B."""
    m = RE_FAIXA.match(texto or "")
    if not m:
        raise ValueError("faixa inválida: %r (use A-B ou A)" % texto)
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    if a < 1 or b < a:
        raise ValueError("faixa inválida: %r (1 <= A <= B)" % texto)
    return a, b


rotulo, codigo, prefixo = co.rotulo_faixa, co.codigo_faixa, co.prefixo_reparo


def validar_documento(nome):
    if not co.RE_NOME.match(nome or "") or ".." in nome or not co.RE_EXTENSAO_DE_ORIGEM.match(nome):
        raise ValueError("nome de documento inválido: %r (esperado <nome>.<ext>, sem '/' nem '..')" % nome)
    return nome


def _ler_texto(caminho):
    with io.open(caminho, encoding="utf-8", newline="") as f:
        return f.read()


def _ler_json(caminho):
    try:
        with io.open(caminho, encoding="utf-8") as f:
            obj = json.load(f)
    except ValueError as e:
        raise Recusa("%s ilegível: %s" % (os.path.basename(caminho), e))
    if not isinstance(obj, dict) or not isinstance(obj.get("summary"), dict):
        raise Recusa("%s ilegível: sem summary" % os.path.basename(caminho))
    return obj


def _assets(pasta, documento):
    """Caminhos relativos (separador `/`) dos arquivos de `<documento>.assets/`, ordenados por bytes."""
    raiz = os.path.join(pasta, documento + ".assets")
    rels = []
    if os.path.isdir(raiz):
        for base, subpastas, arquivos in os.walk(raiz):
            subpastas.sort(key=co._bytes)
            for a in arquivos:
                rels.append(os.path.relpath(os.path.join(base, a), raiz).replace(os.sep, "/"))
    return sorted(rels, key=co._bytes)


def _numero_de_paginas(rel):
    s = rel["summary"]
    for lugar in (s.get("parse") or {}, s):
        for k in CAMPOS_PAGINAS:
            if isinstance(lugar.get(k), int):
                return lugar[k]
    return None


def _saida_de_extracao(esteiras, onda):
    """Os arquivos de recorte ou extração da onda que já existem nas pastas da esteira."""
    achados = []
    for pasta in esteiras:
        for prefixo_ in ("trechos", "equacoes"):
            c = os.path.join(pasta, "%s-%s.jsonl" % (prefixo_, onda))
            if os.path.exists(c):
                achados.append(c.replace(os.sep, "/"))
    return achados


def emendar(raiz, onda, documento, onda_reparo, documento_reparo, a, b, esteiras=()):
    """Aplica a emenda; devolve o registro gravado no sidecar. Toda conferência vem antes de qualquer escrita.
    `esteiras`: pastas onde procurar saída de recorte/extração da onda (além de `<raiz>/_esteira/incerto`)."""
    co.validar_nome(onda)
    co.validar_nome(onda_reparo)
    validar_documento(documento)
    validar_documento(documento_reparo)
    pasta = os.path.join(raiz, "extraidos", onda)
    pasta_r = os.path.join(raiz, "extraidos", onda_reparo)
    c_md, c_rel = os.path.join(pasta, documento + co.SUF_MD), os.path.join(pasta, documento + co.SUF_REL)
    c_md_r = os.path.join(pasta_r, documento_reparo + co.SUF_MD)
    c_rel_r = os.path.join(pasta_r, documento_reparo + co.SUF_REL)
    for c in (c_md, c_rel, c_md_r, c_rel_r):
        if not os.path.isfile(c):
            raise Recusa("arquivo não encontrado: %s" % os.path.relpath(c, raiz).replace(os.sep, "/"))
    n, faixa_txt, pre = b - a + 1, codigo(a, b), prefixo(a, b)

    # pré-condição: a emenda vem antes do portão e do recorte/extração (senão as citações já gravadas mudariam)
    saida = _saida_de_extracao(list(esteiras) + [os.path.join(raiz, "_esteira", "incerto")], onda)
    if saida:
        raise Recusa("a onda já tem saída de recorte/extração (%s): a emenda vem antes do portão e da extração"
                     % ", ".join(saida))
    if os.path.exists(os.path.join(raiz, "conferidos", onda, documento + co.SUF_MD)):
        raise Recusa("%s já está em conferidos/%s/: a emenda vem antes do portão (conferidos/ não se reescreve)"
                     % (documento, onda))

    # o reparo cobre a faixa pelo nome: <qualquer coisa>_pA-B.<ext do alvo> (ou _pA quando A = B)
    sufixo = "_p%s%s" % (faixa_txt, os.path.splitext(documento)[1])
    if not documento_reparo.endswith(sufixo) or len(documento_reparo) == len(sufixo):
        raise Recusa("o documento do reparo tem de terminar em %s (a faixa de --paginas); recebido %s"
                     % (sufixo, documento_reparo))

    # sidecar: idempotência, reparo não reusado e .md intacto desde o último reparo
    c_side = os.path.join(pasta, documento + co.SUF_REPAROS)
    try:
        reparos = co.ler_reparos(pasta, documento) or []
    except ValueError as e:
        raise Recusa(str(e))
    if any(r["paginas"] == faixa_txt for r in reparos):
        raise Recusa("já existe reparo para %s em %s (não se reaplica)" % (rotulo(a, b), os.path.basename(c_side)))
    sha_rel_r = co._sha256(c_rel_r)
    for r in reparos:
        if r["sha256_report_reparo"] == sha_rel_r or r["documento_reparo"] == documento_reparo:
            raise Recusa("este reparo (%s, relatório sha256 %s) já foi usado nas páginas %s"
                         % (documento_reparo, sha_rel_r, r["paginas"]))
    sha_antes = co._sha256(c_md)
    if reparos and reparos[-1]["sha256_md_depois"] != sha_antes:
        raise Recusa("md alterado fora do reparo: o .md alvo não é o de depois do último reparo")

    # a nota no alvo
    md = _ler_texto(c_md)
    linhas = md.splitlines(keepends=True)
    nota = co.re_nota_da_faixa(a, b)
    achadas = [i for i, linha in enumerate(linhas) if nota.match(linha)]
    if len(achadas) != 1:
        raise Recusa("o .md alvo tem %d notas [fallback] para %s; a emenda exige exatamente uma"
                     % (len(achadas), rotulo(a, b)))
    rel = _ler_json(c_rel)
    s = rel.get("summary") or {}
    falhas = ((s.get("parse") or {}).get("paginas_falhas") or 0) - sum(co.paginas_da_faixa(r) for r in reparos)
    if n > falhas:
        raise Recusa("a faixa %s tem %d página(s), mas o alvo só tem %d em summary.parse.paginas_falhas ainda "
                     "não reparadas" % (faixa_txt, n, falhas))

    # o reparo: as mesmas regras do portão, depois as próprias da emenda
    doc_r = co.conferir_documento(pasta_r, documento_reparo)
    if doc_r["veredito"] != "apto":
        raise Recusa("o reparo não passa na conferência: %s" % "; ".join(doc_r["motivos"]))
    rel_r = doc_r["_relatorio"]
    falhas_r = (rel_r["summary"].get("parse") or {}).get("paginas_falhas") or 0
    if falhas_r > 0:
        raise Recusa("o relatório do reparo tem summary.parse.paginas_falhas = %d" % falhas_r)
    total = _numero_de_paginas(rel_r)
    if total is not None and total != n:
        raise Recusa("o reparo tem %d página(s); a faixa %s tem %d" % (total, faixa_txt, n))

    # assets e referências
    origem_assets = os.path.join(pasta_r, documento_reparo + ".assets")
    destino_assets = os.path.join(pasta, documento + ".assets")
    mapa = {r_: pre + r_ for r_ in _assets(pasta_r, documento_reparo)}
    pares = sorted(mapa.items(), key=lambda t: co._bytes(t[0]))
    colisoes = [d for d in mapa.values() if os.path.lexists(os.path.join(destino_assets, *d.split("/")))]
    if colisoes:
        raise Recusa("colisão de asset em %s.assets/: %s" % (documento, ", ".join(colisoes)))
    try:
        derivado = co.derivar_registro(rel_r, documento_reparo, documento, a, b, mapa)
        conteudo = co.reescritor(documento_reparo, documento, mapa)(_ler_texto(c_md_r)).strip("\r\n")
    except ValueError as e:
        raise Recusa(str(e))

    i = achadas[0]
    fim_de_linha = linhas[i][len(linhas[i].rstrip("\r\n")):]
    abre, fecha = co.marcadores_do_reparo(a, b, onda_reparo, sha_rel_r)
    novo = "".join(linhas[:i]) + "%s\n\n%s\n\n%s" % (abre, conteudo, fecha) + fim_de_linha + "".join(linhas[i + 1:])
    resolve = re.compile(r"^parse: %s:" % re.escape(rotulo(a, b)))
    registro = dict(derivado)
    registro.update({
        "paginas": faixa_txt, "pagina_inicial": a, "pagina_final": b,
        "onda_reparo": onda_reparo, "documento_reparo": documento_reparo,
        "sha256_report_reparo": sha_rel_r, "sha256_md_reparo": co._sha256(c_md_r),
        "sha256_original": co._sha256_original(raiz, derivado["source"]),
        "sha256_md_antes": sha_antes, "sha256_md_depois": hashlib.sha256(novo.encode("utf-8")).hexdigest(),
        "erros_resolvidos": [str(e) for e in s.get("erros") or [] if resolve.match(str(e))],
        "assets": [{"origem": o, "destino": d, "sha256": co._sha256(os.path.join(origem_assets, *o.split("/")))}
                   for o, d in pares],
    })

    # escrita. Ordem: assets; sidecar e .md em temporários; troca do sidecar; troca do .md por último. Uma
    # queda deixa o .md alvo intacto (tudo menos a última troca) ou a emenda inteira; ver RECUPERAÇÃO no topo.
    for o, d in pares:
        alvo = os.path.join(destino_assets, *d.split("/"))
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        shutil.copyfile(os.path.join(origem_assets, *o.split("/")), alvo)
    tmp_md, tmp_side = c_md + ".reparo-tmp", c_side + ".reparo-tmp"
    with io.open(tmp_md, "w", encoding="utf-8", newline="") as f:
        f.write(novo)
    with io.open(tmp_side, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(reparos + [registro], sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp_side, c_side)
    os.replace(tmp_md, c_md)
    return registro


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", required=True, help="raiz do corpus local (com extraidos/)")
    ap.add_argument("--onda", required=True, help="onda alvo (pasta em extraidos/)")
    ap.add_argument("--documento", required=True, help="documento alvo, ex.: Dynamic_Hedging.pdf")
    ap.add_argument("--onda-reparo", required=True, help="onda do reparo, ex.: 2026-10-TALEB-1-reparo-DH")
    ap.add_argument("--documento-reparo", required=True, help="sub-PDF reconvertido, ex.: Dynamic_Hedging_p321-340.pdf")
    ap.add_argument("--paginas", required=True, help="faixa do original que o reparo cobre: A-B (ou A)")
    ap.add_argument("--esteira", default=os.path.join("_esteira", "incerto"),
                    help="pasta da esteira local (default: _esteira/incerto)")
    args = ap.parse_args(argv)
    try:
        a, b = faixa(args.paginas)
        co.validar_nome(args.onda)
        co.validar_nome(args.onda_reparo)
        validar_documento(args.documento)
        validar_documento(args.documento_reparo)
    except ValueError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 2
    try:
        r = emendar(os.path.abspath(args.raiz), args.onda, args.documento, args.onda_reparo,
                    args.documento_reparo, a, b, [os.path.abspath(args.esteira)])
    except Recusa as e:
        print("RECUSADO: %s" % e, file=sys.stderr)
        return 1
    print("Emendado: %s, %s ← %s/%s (%d item(ns), %d asset(s)); registro em %s%s." % (
        args.documento, rotulo(a, b), args.onda_reparo, args.documento_reparo, len(r["items"]),
        len(r["assets"]), args.documento, co.SUF_REPAROS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
