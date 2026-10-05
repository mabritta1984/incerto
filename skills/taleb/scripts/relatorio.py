#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Relatório por ativo: diagnósticos de cauda (caudas.py) e de convexidade/ergodicidade (convexidade.py) sobre
retornos brasileiros, em Markdown determinístico. Só biblioteca padrão.

Cada número sai com a equação que o produziu e a marcação de fonte: `[corpus]` se `status_equacoes[nome] ==
"aprovado"`, `[staging]` se `"staging"`, `[externo]` se o nome falta, o status é outro ou `status_equacoes` é
None. Os `EQ_*` abaixo são um mapa fixo métrica -> RÓTULO de equação: o `:Equacao.rotulo` que o PO dá pela
decisão `rotular_equacao` (`skills/lavra/references/grafo-incerto.md`) e com que o MCP `ler_equacao` acha a
equação. `status_equacoes` é indexado por esses rótulos.

Entrada: `retornos` são retornos LOGARÍTMICOS diários (saída de `dados_br.retornos_log`). Caudas e assimetria
usam-nos como vêm; a seção de ergodicidade os converte em retornos simples (exp(r) − 1), que é o que
`crescimento_temporal`/`crescimento_ensemble` esperam. `taxa_livre_diaria` é taxa simples diária (0,0005 =
0,05% ao dia) e entra SÓ na seção Ergodicidade: excesso = crescimento temporal − taxa_livre_diaria (a
diferença entre ln(1+taxa) e a taxa é desprezível em taxas diárias e é ignorada de propósito).

Veredito (determinístico): Extremistão se κ(n0=1, n=30) > 0,3 ou α̂ de Hill (cauda esquerda, k = max(10,
n//20)) < 2; senão Mediocristão. Classe de fragilidade = intervalo bootstrap de 95% de
`assimetria_empirica` (500 reamostras, semente fixa): antifrágil se todo acima de 0, frágil se todo abaixo, robusto
se contém 0. Todo número impresso termina com marcação de fonte; linhas derivadas levam a mais fraca das entradas. O veredito diagnostica exposição e NUNCA recomenda
ativo: usa só frágil/robusto/antifrágil/Extremistão/Mediocristão e termina com a linha fixa FECHAMENTO.

Menos de 60 retornos: ValueError com a contagem (métricas de cauda não significam nada em amostra assim).

Uso:
    python3 skills/taleb/scripts/relatorio.py --ticker PETR4 --cotahist dados/COTAHIST_A2024.ZIP --sgs-cache dados \
        [--status-equacoes status.json]
`--status-equacoes`: JSON objeto rótulo -> status (`{"kappa": "aprovado", "hill": "staging"}`), montado pela
estação `taleb` (aprovado: `ler_equacao(<rótulo>)` achou a equação; staging: só dos arquivos locais da
esteira). Sem ele, tudo é `[externo]`.
Lê o COTAHIST local e a Selic diária (SGS 11) do cache `--sgs-cache` (o nome do cache depende do período; sem
cache, baixa pelo SGS). Código 0 em sucesso, 2 em dado indisponível, amostra pequena ou erro de uso.
"""
import argparse
import json
import math
import random
import sys
import urllib.request
from datetime import date

import dados_br    # vizinhos em skills/taleb/scripts/: a pasta do script já é o sys.path[0] ao rodá-lo
import caudas
import convexidade

EQ_KAPPA = "kappa"
EQ_HILL = "hill"
EQ_MAX_SOMA = "razao_max_soma"
EQ_ASSIMETRIA = "assimetria_convexidade"
EQ_CRESC_TEMPORAL = "crescimento_temporal"
EQ_CRESC_ENSEMBLE = "crescimento_ensemble"

MINIMO_RETORNOS = 60
LIMIAR_KAPPA = 0.3
LIMIAR_ALFA = 2.0
FECHAMENTO = "Isto não é recomendação de ativo."
REAMOSTRAS_H = 500
SEMENTE_H = 15
AVISO_PRECOS = ("Preços do COTAHIST não são ajustados por proventos ou desdobramentos; um desdobramento "
                "aparece como retorno espúrio.")
_ORDEM_TAG = ("[externo]", "[staging]", "[corpus]")  # do mais fraco ao mais forte


def _mais_fraca(*tags):
    return min(tags, key=_ORDEM_TAG.index)


def intervalo_h(xs, reamostras=REAMOSTRAS_H, semente=SEMENTE_H):
    """Intervalo de 95% (percentis 2,5 e 97,5) de H = assimetria_empirica por bootstrap: `reamostras`
    reamostragens de `xs` com reposição, `random.Random(semente)`."""
    r = random.Random(semente)
    n = len(xs)
    hs = sorted(convexidade.assimetria_empirica([xs[r.randrange(n)] for _ in range(n)])
                for _ in range(reamostras))
    return hs[int(0.025 * reamostras)], hs[int(0.975 * reamostras) - 1]


def classe_fragilidade(baixo, alto):
    """antifrágil se o intervalo está todo acima de 0; frágil se todo abaixo; senão robusto."""
    if baixo > 0:
        return "antifrágil"
    if alto < 0:
        return "frágil"
    return "robusto"


def etiqueta(nome, status_equacoes):
    """`[corpus]`, `[staging]` ou `[externo]` para a equação `nome`."""
    status = (status_equacoes or {}).get(nome)
    return {"aprovado": "[corpus]", "staging": "[staging]"}.get(status, "[externo]")


def _f(x):
    return f"{x:.6f}"


def relatorio_ativo(ticker, retornos, taxa_livre_diaria, status_equacoes=None,
                    fonte_taxa_livre="informada pelo chamador",
                    fonte_retornos="dados B3/COTAHIST"):
    """Relatório Markdown do ativo `ticker`; ver o cabeçalho do módulo para entrada, veredito e marcação."""
    n = len(retornos)
    if n < MINIMO_RETORNOS:
        raise ValueError(f"{ticker}: {n} retornos; mínimo {MINIMO_RETORNOS} (métricas de cauda não são "
                         f"significativas em amostra menor)")
    xs = [float(r) for _, r in retornos]
    if not all(math.isfinite(x) for x in xs):
        raise ValueError(f"{ticker}: retorno não finito na amostra")
    tag = lambda nome: etiqueta(nome, status_equacoes)
    k = max(10, n // 20)

    kap = caudas.kappa(xs, 1, 30)
    alfa = caudas.hill(xs, k, "esquerda")
    r2 = caudas.razao_max_soma(xs, 2)[-1]
    r4 = caudas.razao_max_soma(xs, 4)[-1]
    h = convexidade.assimetria_empirica(xs)
    h_baixo, h_alto = intervalo_h(xs)
    classe = classe_fragilidade(h_baixo, h_alto)
    ic = f"IC95% bootstrap [{_f(h_baixo)}; {_f(h_alto)}]"
    tag_dom = _mais_fraca(tag(EQ_KAPPA), tag(EQ_HILL))
    simples = [math.exp(x) - 1.0 for x in xs]
    temporal = convexidade.crescimento_temporal(simples)
    ensemble = convexidade.crescimento_ensemble(simples)
    extremistao = kap > LIMIAR_KAPPA or alfa < LIMIAR_ALFA
    dominio = "Extremistão" if extremistao else "Mediocristão"

    L = [f"# Relatório de {ticker}", "",
         f"- Amostra: {n} retornos logarítmicos diários, de {retornos[0][0].isoformat()} a "
         f"{retornos[-1][0].isoformat()} — fonte: {fonte_retornos} [externo]",
         "", AVISO_PRECOS,
         "Fonte de cada número: nome da equação e marcação corpus, staging ou externo (externo = a equação "
         "não consta como aprovada ou em staging no grafo).", "",
         "## Caudas", "",
         f"- κ(n0=1, n=30) = {_f(kap)} — equação `{EQ_KAPPA}` {tag(EQ_KAPPA)}",
         f"- α̂ de Hill, cauda esquerda, k={k} = {_f(alfa)} — equação `{EQ_HILL}` {tag(EQ_HILL)}",
         f"- razão máximo/soma R_n(p=2) = {_f(r2)} — equação `{EQ_MAX_SOMA}` {tag(EQ_MAX_SOMA)}",
         f"- razão máximo/soma R_n(p=4) = {_f(r4)} — equação `{EQ_MAX_SOMA}` {tag(EQ_MAX_SOMA)}", "",
         "## Convexidade", "",
         f"- assimetria empírica H (choque de ±2σ, por quantis) = {_f(h)}, {ic} — equação "
         f"`{EQ_ASSIMETRIA}` {tag(EQ_ASSIMETRIA)}",
         f"- classe: **{classe}** — antifrágil se o intervalo de H fica todo acima de 0, frágil se todo "
         f"abaixo, robusto se contém 0 (ruído amostral não decide a classe) — equação `{EQ_ASSIMETRIA}` "
         f"{tag(EQ_ASSIMETRIA)}", "",
         "## Ergodicidade", "",
         f"- crescimento temporal (média de ln(1+r)) = {_f(temporal)} — equação `{EQ_CRESC_TEMPORAL}` "
         f"{tag(EQ_CRESC_TEMPORAL)}",
         f"- crescimento de ensemble (média aritmética de r) = {_f(ensemble)} — equação "
         f"`{EQ_CRESC_ENSEMBLE}` {tag(EQ_CRESC_ENSEMBLE)}",
         f"- taxa livre de risco diária = {_f(taxa_livre_diaria)} — fonte: {fonte_taxa_livre} [externo]",
         f"- excesso de crescimento temporal sobre a taxa livre = {_f(temporal - taxa_livre_diaria)} — "
         f"equação `{EQ_CRESC_TEMPORAL}` {tag(EQ_CRESC_TEMPORAL)}", "",
         "## Veredito", "",
         f"- domínio: **{dominio}** — derivado de κ e α̂ (equações `{EQ_KAPPA}` e `{EQ_HILL}`) {tag_dom}",
         f"- limiares: Extremistão se κ > {LIMIAR_KAPPA} ou α̂ < {LIMIAR_ALFA:g} — limiar do incerto [externo]",
         f"- κ = {_f(kap)} — equação `{EQ_KAPPA}` {tag(EQ_KAPPA)}",
         f"- α̂ = {_f(alfa)} — equação `{EQ_HILL}` {tag(EQ_HILL)}",
         f"- fragilidade: **{classe}** — H = {_f(h)}, {ic} — equação `{EQ_ASSIMETRIA}` "
         f"{tag(EQ_ASSIMETRIA)}",
         "", FECHAMENTO]
    return "\n".join(L) + "\n"


def ler_status_equacoes(caminho):
    """O mapa rótulo -> status de `--status-equacoes`; ValueError se não for um objeto JSON de textos."""
    try:
        with open(caminho, encoding="utf-8") as f:
            mapa = json.load(f)
    except OSError as e:
        raise ValueError(f"--status-equacoes {caminho}: {e.strerror or e}")
    except ValueError as e:
        raise ValueError(f"--status-equacoes {caminho}: JSON inválido ({e})")
    if not isinstance(mapa, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in mapa.items()):
        raise ValueError(f"--status-equacoes {caminho}: use um objeto JSON rótulo -> status (textos)")
    return mapa


def main(argv=None, abrir=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description="Relatório de caudas, convexidade e ergodicidade de um ativo.")
    ap.add_argument("--ticker", required=True, help="CODNEG no COTAHIST")
    ap.add_argument("--cotahist", required=True, help="COTAHIST .txt ou .zip local")
    ap.add_argument("--sgs-cache", default="dados", help="pasta do cache do SGS (padrão: dados)")
    ap.add_argument("--inicio", type=date.fromisoformat, help="início do período da Selic (padrão: 1º retorno)")
    ap.add_argument("--fim", type=date.fromisoformat, help="fim do período da Selic (padrão: último retorno)")
    ap.add_argument("--status-equacoes", help="JSON rótulo -> status (aprovado|staging) das equações EQ_*; "
                                              "sem ele, tudo é [externo]")
    a = ap.parse_args(argv)
    try:
        status_equacoes = ler_status_equacoes(a.status_equacoes) if a.status_equacoes else None
        regs = dados_br.cotahist_ler(a.cotahist, {a.ticker})
        if not regs:
            raise ValueError(f"ticker {a.ticker} ausente em {a.cotahist}")
        retornos = dados_br.retornos_log(sorted((r["data"], r["preult"]) for r in regs))
        if len(retornos) < MINIMO_RETORNOS:
            raise ValueError(f"{a.ticker}: {len(retornos)} retornos; mínimo {MINIMO_RETORNOS}")
        ini, fim = a.inicio or retornos[0][0], a.fim or retornos[-1][0]
        selic = dados_br.sgs(dados_br.SERIES["selic_diaria"], ini, fim, cache=a.sgs_cache, abrir=abrir)
        if not selic:
            raise ValueError(f"SGS 11 sem observações entre {ini} e {fim}")
        taxa = math.fsum(v for _, v in selic) / len(selic) / 100.0  # SGS 11 vem em % ao dia
        texto = relatorio_ativo(a.ticker, retornos, taxa, status_equacoes,
                                fonte_taxa_livre=f"SGS série 11, média de {len(selic)} observações "
                                                 f"({ini.isoformat()} a {fim.isoformat()})")
    except (dados_br.DadosIndisponiveis, ValueError, OSError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
