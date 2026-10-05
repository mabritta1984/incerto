#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registro da segunda via do fiscal: a prova Wolfram que o AGENTE rodou pelo MCP vira uma linha de
`provas-<onda>.jsonl`, que a P4 do `fiscal.py` confere contra a via SymPy.

Nenhum script chama o Wolfram: o agente monta o código pelo protocolo de `references/fiscal.md` (dono
único), roda-o pelo MCP, salva o código em `<arquivo.wl>` e a saída, tal como veio, em `<arquivo.txt>`,
e chama este script. Código e saída são lidos **verbatim** (sem tradução de quebra de linha nem corte)
e gravados como estão.

Linhas (uma por prova, `json.dumps(sort_keys=True, ensure_ascii=False)`, `newline="\\n"`, sem timestamp):
  derivação       {"prova": "P2", "via": "wolfram", "mae", "filha", "codigo", "saida", "veredito"}
  momento fechado {"prova": "momento", "via": "wolfram", "equacao", "codigo", "saida", "veredito"}
`veredito` ∈ verde|vermelho|indeterminado, decidido pelo agente segundo `references/fiscal.md`.

A chave de uma prova é `prova` + `mae` + `filha` (P2) ou `prova` + `equacao` (momento) — as mesmas com
que a P4 a junta à onda. Chave já registrada é recusada; com `--substituir`, o arquivo é reescrito sem a
linha antiga e a nova vai para o fim (as demais mantêm a ordem). Gravação atômica.

Uso:
  python3 registrar_prova.py --onda <onda> --prova P2 --mae <nome> --filha <nome> \\
          --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado [--substituir]
  python3 registrar_prova.py --onda <onda> --prova momento --equacao <nome> \\
          --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado [--substituir]
Arquivo: `<raiz-esteira>/provas-<onda>.jsonl` (padrão `_esteira/incerto`), ou `--provas-wolfram <jsonl>`.
Só biblioteca padrão; formato e chaves vêm do `fiscal.py` (vizinho, importado sem `sympy`).
"""
import argparse
import io
import json
import os
import sys

import fiscal             # vizinhos em skills/lavra/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo
import recortar_trechos


def _ler_verbatim(caminho, rotulo):
    try:
        with io.open(caminho, encoding="utf-8", newline="") as f:
            texto = f.read()
    except OSError as e:
        sys.exit("não consegui ler --%s %s: %s" % (rotulo, caminho, e.strerror or e))
    if not texto.strip():
        sys.exit("--%s %s está vazio: prova sem %s não é prova" % (rotulo, caminho, rotulo))
    return texto


def _linha_json(linha):
    return json.dumps(linha, sort_keys=True, ensure_ascii=False) + "\n"


def registrar(caminho, linha, substituir=False):
    """Anexa `linha` a `caminho`; chave repetida levanta `ValueError`, salvo com `substituir`."""
    fiscal.validar_prova_wolfram(linha)
    chave = fiscal.chave_wolfram(linha)
    fiscal.provas_wolfram(caminho)                       # o arquivo existente tem de estar íntegro
    existentes = []
    if os.path.exists(caminho):
        with io.open(caminho, encoding="utf-8", newline="") as f:
            # só "\n" separa linhas: `splitlines` também cortaria em U+2028, que o JSON sem ensure_ascii não escapa
            existentes = [l + "\n" for l in f.read().split("\n") if l.strip()]
    mantidas = [l for l in existentes if fiscal.chave_wolfram(json.loads(l)) != chave]
    if len(mantidas) != len(existentes) and not substituir:
        raise ValueError("prova já registrada: %s (use --substituir)" % "/".join(chave))
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    temporario = caminho + ".tmp"
    with io.open(temporario, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(mantidas) + _linha_json(linha))
    os.replace(temporario, caminho)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onda", required=True)
    ap.add_argument("--prova", required=True, choices=sorted(fiscal.CHAVES_WOLFRAM),
                    help="P2 (derivação: --mae e --filha) ou momento (momento fechado: --equacao)")
    ap.add_argument("--mae")
    ap.add_argument("--filha")
    ap.add_argument("--equacao")
    ap.add_argument("--via", default=fiscal.VIA_WOLFRAM, choices=(fiscal.VIA_WOLFRAM,))
    ap.add_argument("--codigo", required=True, help="arquivo com o código Wolfram rodado, verbatim")
    ap.add_argument("--saida", required=True, help="arquivo com a saída do MCP, verbatim")
    ap.add_argument("--veredito", required=True, choices=fiscal.VEREDITOS)
    ap.add_argument("--substituir", action="store_true", help="troca a prova já registrada com a mesma chave")
    ap.add_argument("--raiz-esteira", default="_esteira/incerto")
    ap.add_argument("--provas-wolfram", help="arquivo de provas (padrão: <raiz-esteira>/provas-<onda>.jsonl)")
    args = ap.parse_args(argv)
    if not recortar_trechos.RE_ONDA.match(args.onda) or ".." in args.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")
    proprias = fiscal.CHAVES_WOLFRAM[args.prova]
    faltando = [k for k in proprias if not getattr(args, k)]
    alheias = [k for k in ("mae", "filha", "equacao") if k not in proprias and getattr(args, k) is not None]
    if faltando or alheias:
        ap.error("--prova %s exige %s e só elas (faltando: %s; a mais: %s)"
                 % (args.prova, " e ".join("--" + k for k in proprias), ", ".join(faltando) or "nada",
                    ", ".join(alheias) or "nada"))
    linha = {"prova": args.prova, "via": args.via, "veredito": args.veredito,
             "codigo": _ler_verbatim(args.codigo, "codigo"), "saida": _ler_verbatim(args.saida, "saida")}
    linha.update({k: getattr(args, k) for k in proprias})
    caminho = args.provas_wolfram or os.path.join(args.raiz_esteira, "provas-%s.jsonl" % args.onda)
    try:
        registrar(caminho, linha, args.substituir)
    except ValueError as e:
        sys.exit("não registrado — %s" % e)
    print("registrado: %s %s %s em %s" % (args.prova, "/".join(linha[k] for k in proprias), args.veredito, caminho))
    return 0


if __name__ == "__main__":
    sys.exit(main())
