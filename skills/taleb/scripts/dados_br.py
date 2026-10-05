#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dados do mercado brasileiro, reproduzíveis: séries do SGS do Banco Central e cotações históricas da B3
(COTAHIST), com cache em disco. Só biblioteca padrão.

Hosts (únicos que este módulo toca, e só em `sgs`): `api.bcb.gov.br`. O COTAHIST nunca é baixado por
código: `cotahist_url` só diz onde está o ZIP anual (host `bvmf.bmfbovespa.com.br`) para baixar à mão em
`dados/`; ver `skills/taleb/references/dados-br.md`.

A rede entra por `abrir` (padrão `urllib.request.urlopen`), injetável: os testes passam um `abrir` falso e
nunca tocam a rede. A API do SGS limita séries diárias a janelas de 10 anos; `sgs` divide o pedido em
janelas de até 10 anos, concatena em ordem de data e remove datas repetidas.

Uso:
    python3 skills/taleb/scripts/dados_br.py --sgs 11 --inicio 2020-01-01 --fim 2025-12-31 [--cache dados]
    python3 skills/taleb/scripts/dados_br.py --cotahist dados/COTAHIST_A2025.ZIP [--ticker PETR4 ...]
Saída: linhas `data<TAB>valor` (SGS) ou `data<TAB>ticker<TAB>fechamento` (COTAHIST). Código 0 em sucesso,
2 em dados indisponíveis ou erro de uso.
"""
import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta

SERIES = {"selic_diaria": 11, "cdi_diaria": 12, "selic_meta": 432, "ipca_mensal": 433,
          "ptax_venda": 1, "ibovespa": 7}
URL_SGS = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           "?formato=json&dataInicial={ini}&dataFinal={fim}")
URL_COTAHIST = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
ANOS_POR_JANELA = 10
LARGURA_COTAHIST = 245
TIMEOUT = 30


class DadosIndisponiveis(Exception):
    """Dado não obtido; a mensagem nomeia o código da série e a URL (nunca credencial)."""


def cotahist_url(ano):
    return URL_COTAHIST.format(ano=ano)


# ---------------------------------------------------------------- SGS

def _br(d):
    return d.strftime("%d/%m/%Y")


def _mais_anos(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 de fevereiro num ano não bissexto
        return d.replace(year=d.year + n, day=28)


def _janelas(inicio, fim):
    """Janelas contíguas [a, b] de no máximo 10 anos cobrindo [inicio, fim]."""
    saida, a = [], inicio
    while a <= fim:
        b = min(_mais_anos(a, ANOS_POR_JANELA) - timedelta(days=1), fim)
        saida.append((a, b))
        a = b + timedelta(days=1)
    return saida


def _baixar_janela(codigo, a, b, abrir):
    url = URL_SGS.format(codigo=codigo, ini=_br(a), fim=_br(b))
    try:
        resp = abrir(url, timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        raise DadosIndisponiveis(f"SGS {codigo}: HTTP {e.code} em {url}") from e
    except (urllib.error.URLError, OSError) as e:
        raise DadosIndisponiveis(f"SGS {codigo}: falha de rede ({e}) em {url}") from e
    try:
        status = getattr(resp, "status", None)
        if status is None:
            status = resp.getcode()
        if status != 200:
            raise DadosIndisponiveis(f"SGS {codigo}: HTTP {status} em {url}")
        bruto = resp.read()
    finally:
        fechar = getattr(resp, "close", None)
        if fechar:
            fechar()
    try:
        corpo = json.loads(bruto.decode("utf-8"))
    except ValueError as e:
        raise DadosIndisponiveis(f"SGS {codigo}: corpo que não é JSON em {url}") from e
    if not isinstance(corpo, list):
        raise DadosIndisponiveis(f"SGS {codigo}: resposta que não é lista em {url}: {str(corpo)[:120]}")
    linhas = []
    for item in corpo:
        try:
            linhas.append((datetime.strptime(item["data"], "%d/%m/%Y").date(), float(item["valor"])))
        except (KeyError, TypeError, ValueError) as e:
            raise DadosIndisponiveis(f"SGS {codigo}: linha malformada {item!r} em {url}") from e
    return linhas


def _caminho_cache(cache, codigo, inicio, fim):
    return os.path.join(cache, f"sgs-{codigo}-{inicio.isoformat()}-{fim.isoformat()}.json")


def _ler_cache(caminho):
    try:
        with open(caminho, encoding="utf-8", newline="") as f:
            return [(date.fromisoformat(d), float(v)) for d, v in json.load(f)]
    except (OSError, ValueError, TypeError):
        return None  # ausente ou corrompido: baixa de novo


def sgs(codigo, inicio, fim, cache="dados", abrir=urllib.request.urlopen, hoje=None):
    """Série do SGS entre `inicio` e `fim` (inclusive) como [(data, valor)] em ordem de data.

    Cache em `<cache>/sgs-<codigo>-<inicio ISO>-<fim ISO>.json`; pedidos além de 10 anos são divididos em
    janelas e remontados. Período que chega a `hoje` (padrão: `date.today()`) ou além nunca vai ao cache —
    nem é gravado nem é lido: o dia corrente ainda não fechou e a série congelaria incompleta. HTTP diferente
    de 200 ou corpo que não é lista levanta `DadosIndisponiveis`."""
    if inicio > fim:
        raise ValueError(f"inicio {inicio} depois de fim {fim}")
    caminho = _caminho_cache(cache, codigo, inicio, fim)
    cacheavel = fim < (hoje or date.today())
    em_cache = _ler_cache(caminho) if cacheavel else None
    if em_cache is not None:
        return em_cache
    por_data = {}
    for a, b in _janelas(inicio, fim):
        for d, v in _baixar_janela(codigo, a, b, abrir):
            por_data[d] = v
    serie = sorted(por_data.items())
    if cacheavel:
        os.makedirs(cache, exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps([[d.isoformat(), v] for d, v in serie], sort_keys=True, ensure_ascii=False))
    return serie


# ---------------------------------------------------------------- COTAHIST

# (nome, início, fim) em posições 1-based inclusivas, como no layout da B3.
_TEXTOS = (("tipreg", 1, 2), ("codbdi", 11, 12), ("codneg", 13, 24), ("tpmerc", 25, 27),
           ("nomres", 28, 39), ("especi", 40, 49))
_VALORES = (("preabe", 57, 69), ("premax", 70, 82), ("premin", 83, 95), ("premed", 96, 108),
            ("preult", 109, 121), ("voltot", 171, 188))  # inteiros com 2 decimais implícitos


def _texto_cotahist(caminho):
    if caminho.lower().endswith(".zip"):
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            if not nomes:
                raise ValueError(f"{caminho}: ZIP vazio")
            return z.read(nomes[0]).decode("latin-1")
    with open(caminho, "rb") as f:
        return f.read().decode("latin-1")


def cotahist_ler(caminho, tickers=None):
    """Registros de negociação (`TIPREG` 01) de um COTAHIST `.txt` ou `.zip` (primeiro membro, latin-1).

    Cada registro é um dict com data, tipreg, codbdi, codneg, tpmerc, nomres, especi, preabe, premax,
    premin, premed, preult e voltot; preços e volume vêm com 2 decimais implícitos e saem divididos por
    100. `tickers` filtra por `CODNEG` exato; sem ele vêm todos. Linha de dados curta ou com campo
    numérico corrompido levanta ValueError com o número da linha."""
    saida = []
    for n, linha in enumerate(_texto_cotahist(caminho).split("\n"), 1):
        linha = linha.rstrip("\r")
        if linha[:2] != "01":
            continue
        if len(linha) < LARGURA_COTAHIST:
            raise ValueError(f"{caminho}: linha {n} com {len(linha)} caracteres (esperado {LARGURA_COTAHIST})")
        try:
            reg = {"data": datetime.strptime(linha[2:10], "%Y%m%d").date()}
            for nome, i, f in _TEXTOS:
                reg[nome] = linha[i - 1:f].strip()
            for nome, i, f in _VALORES:
                reg[nome] = int(linha[i - 1:f]) / 100
        except ValueError as e:
            raise ValueError(f"{caminho}: linha {n} com campo inválido ({e})") from e
        if tickers is None or reg["codneg"] in tickers:
            saida.append(reg)
    return saida


# ---------------------------------------------------------------- retornos

def retornos_log(serie):
    """Retornos logarítmicos [(data do segundo preço, ln(p2/p1))] entre preços positivos consecutivos.
    Preço não positivo é descartado sem exceção, e o próximo par parte do último preço válido."""
    saida, anterior = [], None
    for d, p in serie:
        if not p > 0 or math.isnan(p):
            continue
        if anterior is not None:
            saida.append((d, math.log(p / anterior)))
        anterior = p
    return saida


# ---------------------------------------------------------------- CLI

def main(argv=None, abrir=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description="SGS do BCB e COTAHIST da B3, com cache em disco.")
    ap.add_argument("--sgs", type=int, help="código da série do SGS")
    ap.add_argument("--inicio", type=date.fromisoformat, help="aaaa-mm-dd (com --sgs)")
    ap.add_argument("--fim", type=date.fromisoformat, help="aaaa-mm-dd (com --sgs)")
    ap.add_argument("--cache", default="dados", help="pasta do cache (padrão: dados)")
    ap.add_argument("--cotahist", help="caminho de um COTAHIST .txt ou .zip")
    ap.add_argument("--ticker", action="append", help="filtra por CODNEG; repetível")
    a = ap.parse_args(argv)
    if (a.sgs is None) == (a.cotahist is None):
        ap.error("informe exatamente um entre --sgs e --cotahist")
    try:
        if a.sgs is not None:
            if a.inicio is None or a.fim is None:
                ap.error("--sgs exige --inicio e --fim")
            for d, v in sgs(a.sgs, a.inicio, a.fim, cache=a.cache, abrir=abrir):
                print(f"{d.isoformat()}\t{v}")
        else:
            for r in cotahist_ler(a.cotahist, set(a.ticker) if a.ticker else None):
                print(f"{r['data'].isoformat()}\t{r['codneg']}\t{r['preult']}")
    except (DadosIndisponiveis, ValueError, OSError, zipfile.BadZipFile) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
