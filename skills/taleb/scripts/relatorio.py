#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Relatório por ativo: diagnósticos de cauda (caudas.py) e de convexidade/ergodicidade (convexidade.py) sobre
retornos brasileiros, em Markdown determinístico. Só biblioteca padrão.

Cada número sai com a equação que o produziu e a marcação de fonte: `[corpus]` se `status_equacoes[nome] ==
"aprovado"`, `[staging]` se `"staging"`, `[externo]` se o nome falta, o status é outro ou `status_equacoes` é
None. Os nomes `EQ_*` abaixo são um mapa fixo métrica -> equação e DEVEM coincidir com os nomes dos nós
`:Equacao` aprovados pelo PO; a conferência é a reconciliação da Task 19.

Entrada: `retornos` são retornos LOGARÍTMICOS diários (saída de `dados_br.retornos_log`). Caudas e assimetria
usam-nos como vêm; a seção de ergodicidade os converte em retornos simples (exp(r) − 1), que é o que
`crescimento_temporal`/`crescimento_ensemble` esperam. `taxa_livre_diaria` é taxa simples diária (0,0005 =
0,05% ao dia) e entra SÓ na seção Ergodicidade: excesso = crescimento temporal − taxa_livre_diaria (a
diferença entre ln(1+taxa) e a taxa é desprezível em taxas diárias e é ignorada de propósito).

Veredito (determinístico): Extremistão se κ(n0=1, n=30) > 0,3 ou α̂ de Hill (cauda esquerda, k = max(10,
n//20)) < 2; senão Mediocristão. Classe de fragilidade = `classificar(assimetria_empirica(retornos))` (tolerância
padrão 1e-9, logo o "robusto" só aparece com assimetria nula). O veredito diagnostica exposição e NUNCA recomenda
ativo: usa só frágil/robusto/antifrágil/Extremistão/Mediocristão e termina com a linha fixa FECHAMENTO.

Menos de 60 retornos: ValueError com a contagem (métricas de cauda não significam nada em amostra assim).

Uso:
    python3 skills/taleb/scripts/relatorio.py --ticker PETR4 --cotahist dados/COTAHIST_A2024.ZIP --sgs-cache dados
Lê o COTAHIST local e a Selic diária (SGS 11) do cache `--sgs-cache` (o nome do cache depende do período; sem
cache, baixa pelo SGS). Código 0 em sucesso, 2 em dado indisponível, amostra pequena ou erro de uso.
"""
import argparse
import math
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
_NOME_CLASSE = {"fragil": "frágil", "robusto": "robusto", "antifragil": "antifrágil"}


def etiqueta(nome, status_equacoes):
    """`[corpus]`, `[staging]` ou `[externo]` para a equação `nome`."""
    status = (status_equacoes or {}).get(nome)
    return {"aprovado": "[corpus]", "staging": "[staging]"}.get(status, "[externo]")


def _f(x):
    return f"{x:.6f}"


def relatorio_ativo(ticker, retornos, taxa_livre_diaria, status_equacoes=None,
                    fonte_taxa_livre="informada pelo chamador"):
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
    classe = _NOME_CLASSE[convexidade.classificar(h)]
    simples = [math.exp(x) - 1.0 for x in xs]
    temporal = convexidade.crescimento_temporal(simples)
    ensemble = convexidade.crescimento_ensemble(simples)
    extremistao = kap > LIMIAR_KAPPA or alfa < LIMIAR_ALFA
    dominio = "Extremistão" if extremistao else "Mediocristão"

    L = [f"# Relatório de {ticker}", "",
         f"Amostra: {n} retornos logarítmicos diários, de {retornos[0][0].isoformat()} a "
         f"{retornos[-1][0].isoformat()}.",
         "Fonte de cada número: nome da equação e marcação corpus, staging ou externo (externo = a equação "
         "não consta como aprovada ou em staging no grafo).", "",
         "## Caudas", "",
         f"- κ(n0=1, n=30) = {_f(kap)} — equação `{EQ_KAPPA}` {tag(EQ_KAPPA)}",
         f"- α̂ de Hill, cauda esquerda, k={k} = {_f(alfa)} — equação `{EQ_HILL}` {tag(EQ_HILL)}",
         f"- razão máximo/soma R_n(p=2) = {_f(r2)} — equação `{EQ_MAX_SOMA}` {tag(EQ_MAX_SOMA)}",
         f"- razão máximo/soma R_n(p=4) = {_f(r4)} — equação `{EQ_MAX_SOMA}` {tag(EQ_MAX_SOMA)}", "",
         "## Convexidade", "",
         f"- assimetria empírica H (choque de ±2σ, por quantis) = {_f(h)} — equação `{EQ_ASSIMETRIA}` "
         f"{tag(EQ_ASSIMETRIA)}",
         f"- classe: **{classe}** (sinal de H: H > 0 antifrágil, H < 0 frágil)", "",
         "## Ergodicidade", "",
         f"- crescimento temporal (média de ln(1+r)) = {_f(temporal)} — equação `{EQ_CRESC_TEMPORAL}` "
         f"{tag(EQ_CRESC_TEMPORAL)}",
         f"- crescimento de ensemble (média aritmética de r) = {_f(ensemble)} — equação "
         f"`{EQ_CRESC_ENSEMBLE}` {tag(EQ_CRESC_ENSEMBLE)}",
         f"- taxa livre de risco diária = {_f(taxa_livre_diaria)} — fonte: {fonte_taxa_livre}",
         f"- excesso de crescimento temporal sobre a taxa livre = {_f(temporal - taxa_livre_diaria)} — "
         f"equação `{EQ_CRESC_TEMPORAL}` {tag(EQ_CRESC_TEMPORAL)}", "",
         "## Veredito", "",
         f"- domínio: **{dominio}** (Extremistão se κ > {LIMIAR_KAPPA} ou α̂ < {LIMIAR_ALFA:g})",
         f"- κ = {_f(kap)} — equação `{EQ_KAPPA}` {tag(EQ_KAPPA)}",
         f"- α̂ = {_f(alfa)} — equação `{EQ_HILL}` {tag(EQ_HILL)}",
         f"- fragilidade: **{classe}** — H = {_f(h)} — equação `{EQ_ASSIMETRIA}` {tag(EQ_ASSIMETRIA)}",
         "", FECHAMENTO]
    return "\n".join(L) + "\n"


def main(argv=None, abrir=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description="Relatório de caudas, convexidade e ergodicidade de um ativo.")
    ap.add_argument("--ticker", required=True, help="CODNEG no COTAHIST")
    ap.add_argument("--cotahist", required=True, help="COTAHIST .txt ou .zip local")
    ap.add_argument("--sgs-cache", default="dados", help="pasta do cache do SGS (padrão: dados)")
    ap.add_argument("--inicio", type=date.fromisoformat, help="início do período da Selic (padrão: 1º retorno)")
    ap.add_argument("--fim", type=date.fromisoformat, help="fim do período da Selic (padrão: último retorno)")
    a = ap.parse_args(argv)
    try:
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
        texto = relatorio_ativo(a.ticker, retornos, taxa, None,
                                fonte_taxa_livre=f"SGS série 11, média de {len(selic)} observações "
                                                 f"({ini.isoformat()} a {fim.isoformat()})")
    except (dados_br.DadosIndisponiveis, ValueError, OSError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
