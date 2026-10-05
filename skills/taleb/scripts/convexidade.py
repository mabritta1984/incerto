#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convexidade e ergodicidade (Taleb): assimetria de resposta (frágil/robusto/antifrágil), critério de Kelly,
barbell, crescimento temporal x de ensemble e assimetria empírica sobre amostras de retornos. Só biblioteca
padrão. Pensado para retornos de mercado brasileiros (`dados_br.retornos_log`).

Parâmetros fora do domínio levantam ValueError cuja mensagem nomeia o parâmetro; nunca se devolve fração
negativa em silêncio. Entrada de amostra vazia ou com valor não finito (nan, inf) também levanta ValueError.
"""
import math
import statistics


def _validar(xs):
    """Devolve `xs` como lista de floats; ValueError se vazia ou com valor não finito."""
    xs = [float(x) for x in xs]
    if not xs:
        raise ValueError("amostra vazia")
    for i, x in enumerate(xs):
        if not math.isfinite(x):
            raise ValueError(f"valor não finito na posição {i}: {x!r}")
    return xs


def _numero(nome, v):
    """Devolve `v` como float finito; ValueError nomeando `nome` caso contrário."""
    if isinstance(v, bool):
        raise ValueError(f"{nome} deve ser número, recebido {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} deve ser número, recebido {v!r}") from None
    if not math.isfinite(x):
        raise ValueError(f"{nome} deve ser finito, recebido {v!r}")
    return x


def assimetria(f, x, delta):
    """Assimetria de resposta H = [f(x+δ) + f(x−δ)]/2 − f(x), com δ > 0. H > 0: ganha com a volatilidade
    (convexa, antifrágil); H < 0: perde (côncava, frágil); H = 0: linear (robusta).
    Equação: assimetria de convexidade (desigualdade de Jensen) — Antifragile, tópico fragility and convexity."""
    delta = _numero("delta", delta)
    if delta <= 0:
        raise ValueError(f"delta deve ser > 0, recebido {delta!r}")
    x = _numero("x", x)
    return (f(x + delta) + f(x - delta)) / 2.0 - f(x)


def classificar(h, tol=1e-9):
    """Classifica a assimetria `h`: h > tol → "antifragil"; h < −tol → "fragil"; senão "robusto"."""
    if h > tol:
        return "antifragil"
    if h < -tol:
        return "fragil"
    return "robusto"


def kelly(p, b):
    """Fração de Kelly f* = p − (1−p)/b, para aposta com probabilidade de ganho `p` (0 ≤ p ≤ 1) e retorno
    líquido `b` > 0 por unidade apostada (perda de 1 unidade no insucesso). Devolve o valor da fórmula: com
    vantagem negativa (ex.: kelly(0.3, 1.0) = −0.4) o resultado é negativo (não apostar / tomar o outro lado).
    Quem dimensiona posição só comprada deve cortar em 0: max(0.0, kelly(p, b)).
    Equação: critério de Kelly — Skin_in_the_Game, tópico Kelly criterion / sizing."""
    p = _numero("p", p)
    b = _numero("b", b)
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"p deve estar em [0, 1], recebido {p!r}")
    if b <= 0:
        raise ValueError(f"b deve ser > 0, recebido {b!r}")
    return p - (1.0 - p) / b


def barbell(fracao_segura, perda_maxima_convexa=1.0):
    """Barbell: `fracao_segura` (0 ≤ · ≤ 1) em ativo sem risco e o resto em ativo convexo cuja perda máxima é
    `perda_maxima_convexa` (0 ≤ · ≤ 1, fração do valor aplicado nele). Devolve
    {"perda_maxima_carteira": (1−fracao_segura)·perda_maxima_convexa, "fracao_segura", "fracao_convexa"}.
    Equação: estratégia barbell — Antifragile, tópico barbell strategy."""
    fs = _numero("fracao_segura", fracao_segura)
    pm = _numero("perda_maxima_convexa", perda_maxima_convexa)
    if not 0.0 <= fs <= 1.0:
        raise ValueError(f"fracao_segura deve estar em [0, 1], recebido {fs!r}")
    if not 0.0 <= pm <= 1.0:
        raise ValueError(f"perda_maxima_convexa deve estar em [0, 1], recebido {pm!r}")
    fc = 1.0 - fs
    return {"perda_maxima_carteira": fc * pm, "fracao_segura": fs, "fracao_convexa": fc}


def crescimento_temporal(retornos):
    """Taxa de crescimento temporal (de um só caminho) = média de ln(1+r). Qualquer r ≤ −1 é ruína (riqueza
    zerada) e dá −inf: devolve `-math.inf`. Compare com `crescimento_ensemble`: a média aritmética pode ser
    positiva enquanto este é negativo (não ergodicidade).
    Equação: crescimento temporal x ensemble (ergodicidade) — Skin_in_the_Game, tópico ergodicity."""
    rs = _validar(retornos)
    if any(r <= -1.0 for r in rs):
        return -math.inf
    return math.fsum(math.log1p(r) for r in rs) / len(rs)


def crescimento_ensemble(retornos):
    """Taxa de crescimento de ensemble = média aritmética dos retornos.
    Equação: crescimento temporal x ensemble (ergodicidade) — Skin_in_the_Game, tópico ergodicity."""
    rs = _validar(retornos)
    return math.fsum(rs) / len(rs)


def _quantil(ordenada, p):
    """Quantil empírico de uma lista ordenada, com interpolação linear (posição p·(n−1))."""
    pos = p * (len(ordenada) - 1)
    i = int(math.floor(pos))
    if i >= len(ordenada) - 1:
        return ordenada[-1]
    return ordenada[i] + (pos - i) * (ordenada[i + 1] - ordenada[i])


def assimetria_empirica(retornos, sigmas=2.0):
    """Resposta média da amostra a choques de ±`sigmas`·σ, pelos quantis: H = [q(+) + q(−)]/2 − mediana,
    com q(±) os quantis empíricos (interpolação linear) nas probabilidades Φ(±sigmas) de uma normal. Amostra
    simétrica dá H ≈ 0; cauda direita mais longa (convexa) dá H > 0; cauda esquerda mais longa, H < 0.
    Equação: assimetria de convexidade, versão empírica — Antifragile, tópico fragility and convexity."""
    sigmas = _numero("sigmas", sigmas)
    if sigmas <= 0:
        raise ValueError(f"sigmas deve ser > 0, recebido {sigmas!r}")
    xs = sorted(_validar(retornos))
    nd = statistics.NormalDist()
    q_mais = _quantil(xs, nd.cdf(sigmas))
    q_menos = _quantil(xs, nd.cdf(-sigmas))
    return (q_mais + q_menos) / 2.0 - statistics.median(xs)
