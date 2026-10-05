#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico de caudas gordas (Taleb): razão máximo/soma, estimador de Hill, métrica kappa e
sobrevivência log-log, mais geradores determinísticos (Pareto, normal, Cauchy) para os testes. Só
biblioteca padrão. Pensado para retornos de mercado brasileiros (`dados_br.retornos_log`).

Valores teóricos de kappa: Gaussiano κ=0, Cauchy κ=1 (valores teóricos; conferência Wolfram registrada
pelo controlador).

Toda amostragem usa `random.Random(semente)` explícita: mesma semente, mesmo resultado, bit a bit.
Entrada vazia ou com valor não finito (nan, inf) levanta ValueError.
"""
import math
import random
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


def _inteiro(v):
    return isinstance(v, int) and not isinstance(v, bool)


def razao_max_soma(xs, p):
    """Razão máximo/soma acumulada R_n(p) = max(|x_1|^p..|x_n|^p) / Σ|x_i|^p, para n = 1..len(xs).
    Devolve a lista R_1..R_n. Com momento p finito a razão tende a 0; com cauda gorda (p >= alpha) não.
    `p` deve ser inteiro positivo. Soma nula (só zeros até ali) dá razão 0.0.
    Equação: razão máximo-soma R_n(p) — Statistical_Consequences_of_Fat_Tails, tópico max-to-sum ratio."""
    if not _inteiro(p) or p < 1:
        raise ValueError(f"p deve ser inteiro positivo, recebido {p!r}")
    xs = _validar(xs)
    maximo = soma = 0.0
    saida = []
    for x in xs:
        v = abs(x) ** p
        maximo = max(maximo, v)
        soma += v
        saida.append(maximo / soma if soma > 0 else 0.0)
    return saida


def hill(xs, k, cauda="esquerda"):
    """Estimador de Hill do índice de cauda alpha com as k maiores observações da cauda pedida:
    alpha = 1 / ( (1/k) Σ_{i=1..k} ln(x_(i) / x_(k+1)) ), x_(1) >= x_(2) >= ... em módulo.
    "esquerda" usa as perdas (-x para x<0); "direita" os ganhos (x para x>0); zeros e o outro lado são
    descartados. Exige 1 <= k < nº de observações da cauda, senão ValueError citando k e o disponível.
    Equação: estimador de Hill — Statistical_Consequences_of_Fat_Tails, tópico Hill estimator."""
    if cauda not in ("esquerda", "direita"):
        raise ValueError(f"cauda deve ser 'esquerda' ou 'direita', recebido {cauda!r}")
    xs = _validar(xs)
    cauda_xs = sorted((-x for x in xs if x < 0) if cauda == "esquerda" else (x for x in xs if x > 0),
                      reverse=True)
    if not _inteiro(k) or not 1 <= k < len(cauda_xs):
        raise ValueError(f"k={k!r} inválido: exige 1 <= k < {len(cauda_xs)} (observações disponíveis na "
                         f"cauda {cauda})")
    h = sum(math.log(cauda_xs[i] / cauda_xs[k]) for i in range(k)) / k
    if h <= 0:
        raise ValueError(f"k={k}: as {k + 1} maiores observações da cauda {cauda} são todas iguais")
    return 1.0 / h


def kappa(xs, n0=1, n=30, reamostras=4000, semente=7, robusto=False):
    """Métrica kappa(n0, n) de Taleb por reamostragem (bootstrap) de `xs`:
    κ = 2 − (ln n − ln n0) / ln(M(n)/M(n0)).  Gaussiano: κ=0; Cauchy: κ=1.
    Padrão (robusto=False), definição de Taleb: M(k) = média, sobre as reamostras, de |S_k − k·x̄|, com S_k a
    soma de k sorteios de `xs` e x̄ a média amostral. Com robusto=True: M(k) = MEDIANA das reamostras de
    |S_k − k·mediana(xs)|. A Cauchy não tem média, então a versão padrão deriva (0,76 a 0,92 conforme a
    semente) e o diagnóstico da Cauchy deve usar robusto=True. Sorteios por `random.Random(semente).choice`.
    Equação: kappa(n0, n) — Statistical_Consequences_of_Fat_Tails, tópico kappa."""
    xs = _validar(xs)
    for nome, v in (("n0", n0), ("n", n), ("reamostras", reamostras)):
        if not _inteiro(v) or v < 1:
            raise ValueError(f"{nome} deve ser inteiro >= 1, recebido {v!r}")
    if n <= n0:
        raise ValueError(f"exige n > n0, recebido n0={n0}, n={n}")
    r = random.Random(semente)
    centro = statistics.median(xs) if robusto else math.fsum(xs) / len(xs)
    agrega = statistics.median if robusto else (lambda v: math.fsum(v) / len(v))
    m = {}
    for kk in (n0, n):
        desvios = [abs(math.fsum(r.choice(xs) for _ in range(kk)) - kk * centro) for _ in range(reamostras)]
        m[kk] = agrega(desvios)
    if m[n0] <= 0 or m[n] <= 0 or m[n] == m[n0]:
        raise ValueError(f"M(n0)={m[n0]!r}, M(n)={m[n]!r}: kappa indefinido (amostra degenerada ou pequena)")
    return 2.0 - (math.log(n) - math.log(n0)) / math.log(m[n] / m[n0])


def sobrevivencia_loglog(xs):
    """Pontos (ln x, ln P(X>x)) da sobrevivência empírica de |x|, só para |x| > 0, em ordem crescente de x
    (um ponto por valor distinto). P é a fração dos |x| > 0 estritamente maiores que x; o último ponto, com
    P=0, fica de fora. Cauda de lei de potência aparece como reta de inclinação −alpha. Vazio → [].
    Equação: função de sobrevivência P(X>x) log-log — Statistical_Consequences_of_Fat_Tails, tópico
    survival function."""
    xs = _validar(xs) if len(xs) else []
    v = sorted(abs(x) for x in xs if x != 0)
    m = len(v)
    pontos = []
    for i, x in enumerate(v):
        if i + 1 < m and v[i + 1] == x:
            continue  # só o último de cada valor repetido
        if i + 1 == m:
            break  # P = 0
        pontos.append((math.log(x), math.log((m - i - 1) / m)))
    return pontos


def amostra_pareto(alpha, L, n, semente):
    """n sorteios Pareto(alpha, L) por inversa da CDF: L·u^(−1/alpha), u em (0,1] (nunca 0)."""
    r = random.Random(semente)
    return [L * (1.0 - r.random()) ** (-1.0 / alpha) for _ in range(n)]


def amostra_normal(n, semente):
    """n sorteios N(0,1) por `random.Random(semente).gauss`."""
    r = random.Random(semente)
    return [r.gauss(0, 1) for _ in range(n)]


def amostra_cauchy(n, semente):
    """n sorteios Cauchy(0,1) por inversa da CDF: tan(π(u − 0.5)), u em (0,1) (nunca 0 nem 1)."""
    r = random.Random(semente)
    saida = []
    while len(saida) < n:
        u = r.random()
        if u > 0.0:
            saida.append(math.tan(math.pi * (u - 0.5)))
    return saida
