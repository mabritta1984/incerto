# -*- coding: utf-8 -*-
"""Task 13: caudas.py — razão máx/soma, Hill, kappa e sobrevivência log-log, com geradores determinísticos.
Os dois kappa nos parâmetros do brief compartilham as amostras via setUpClass; os demais usam tamanhos pequenos."""
import math
import unittest
from _carga import carregar

C = carregar("skills/taleb/scripts/caudas.py")


class TesteCaudas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normal = C.amostra_normal(20000, 7)
        cls.cauchy = C.amostra_cauchy(20000, 7)
        cls.pareto = C.amostra_pareto(1.5, 1.0, 20000, 7)

    # --- geradores
    def test_geradores_sao_deterministicos_e_pareto_respeita_o_minimo(self):
        self.assertEqual(C.amostra_normal(50, 3), C.amostra_normal(50, 3))
        self.assertEqual(C.amostra_cauchy(50, 3), C.amostra_cauchy(50, 3))
        self.assertNotEqual(C.amostra_cauchy(50, 3), C.amostra_cauchy(50, 4))
        p = C.amostra_pareto(1.5, 2.0, 500, 3)
        self.assertEqual(p, C.amostra_pareto(1.5, 2.0, 500, 3))
        self.assertTrue(all(math.isfinite(x) and x >= 2.0 for x in p))

    # --- Hill
    def test_hill_recupera_alpha_de_pareto(self):
        self.assertLess(abs(C.hill(self.pareto, 500, "direita") - 1.5), 0.3)

    def test_hill_ignora_zeros_e_usa_modulo(self):  # Review Focus 3
        self.assertTrue(math.isfinite(C.hill([0.0, -1.0, -2.0, 0.0, -4.0, 3.0], 2, "esquerda")))

    def test_hill_usa_so_a_cauda_pedida(self):
        xs = [-1.0, -2.0, -4.0, 10.0, 20.0, 40.0, 80.0]
        # perdas 1,2,4: k=2 -> H = (ln(4/1) + ln(2/1))/2
        self.assertAlmostEqual(C.hill(xs, 2, "esquerda"), 1 / ((math.log(4) + math.log(2)) / 2))
        self.assertAlmostEqual(C.hill(xs, 3, "direita"), 1 / ((math.log(80 / 10) + math.log(40 / 10) + math.log(20 / 10)) / 3))

    def test_hill_k_invalido_diz_k_e_disponiveis(self):
        for k in (0, -1, 3, 9):
            with self.assertRaises(ValueError) as c:
                C.hill([-1.0, -2.0, -4.0, 5.0], k, "esquerda")
            self.assertIn(str(k), str(c.exception))
            self.assertIn("3", str(c.exception))
        with self.assertRaises(ValueError):
            C.hill([1.0, 2.0, 3.0], 1, "centro")
        with self.assertRaises(ValueError):
            C.hill([1.0, 2.0, 3.0], 1, "esquerda")  # nenhuma perda

    # --- razão máx/soma
    def test_razao_max_soma_gaussiana_vai_a_zero(self):
        self.assertLess(C.razao_max_soma(self.normal, 4)[-1], 0.05)

    def test_razao_max_soma_pareto_nao_vai_a_zero(self):
        self.assertGreater(C.razao_max_soma(self.pareto, 2)[-1], 0.1)

    def test_razao_max_soma_valores_exatos(self):
        self.assertEqual(C.razao_max_soma([1.0, -3.0, 2.0], 1), [1.0, 3 / 4, 3 / 6])
        self.assertEqual(C.razao_max_soma([0.0, 2.0], 2), [0.0, 1.0])

    def test_razao_max_soma_p_invalido(self):
        for p in (0, -2, 1.5, "2", True):
            with self.assertRaises(ValueError):
                C.razao_max_soma([1.0, 2.0], p)

    # --- kappa
    def test_kappa_gaussiana_zero_cauchy_um(self):
        # Cauchy não tem média: o kappa da definição de Taleb (centrado na média amostral) deriva a
        # 0.76-0.92 conforme a semente (sonda do controlador, 05/10/2026, n=20000, 4000 reamostras:
        # sementes 7/8/9 -> 0.921/0.796/0.755; versão pela mediana -> 0.996/0.990/1.008; nesta implementação,
        # semente 7, a ordem dos sorteios difere e dá 0.974 (média) e 0.993 (mediana)). Por isso o
        # caso Cauchy usa robusto=True.
        self.assertLess(abs(C.kappa(self.normal)), 0.15)
        self.assertLess(abs(C.kappa(self.cauchy, robusto=True) - 1.0), 0.15)

    def test_kappa_1_da_student_t3_reproduz_o_corpus(self):
        # rodada corpus C: conferido no Wolfram, Student T(3) dá κ_1 = κ(1, 2) = 0,2904 e
        # n_ν = 30^(-1/(κ_1 − 1)) = 120,7 — os "120 observations" de SCFT 8.3.2. Por simulação, semente fixa e
        # tolerância folgada (a razão M(2)/M(1) por bootstrap oscila ±0,04 entre sementes com 200 mil reamostras)
        import random
        r = random.Random(11)
        t3 = [r.gauss(0, 1) / math.sqrt(sum(r.gauss(0, 1) ** 2 for _ in range(3)) / 3) for _ in range(100000)]
        k1 = C.kappa(t3, 1, 2, reamostras=200000)
        self.assertLess(abs(k1 - 0.29), 0.06, k1)
        self.assertGreater(k1, 0.15)                                    # acima do limiar do corpus
        self.assertAlmostEqual(30 ** (-1 / (0.2904 - 1)), 120.7, delta=0.1)

    def test_kappa_e_deterministico_pela_semente(self):
        xs = C.amostra_normal(300, 1)
        a = C.kappa(xs, n=10, reamostras=200, semente=5)
        self.assertEqual(a, C.kappa(xs, n=10, reamostras=200, semente=5))
        self.assertNotEqual(a, C.kappa(xs, n=10, reamostras=200, semente=6))
        b = C.kappa(xs, n=10, reamostras=200, semente=5, robusto=True)
        self.assertEqual(b, C.kappa(xs, n=10, reamostras=200, semente=5, robusto=True))

    def test_kappa_validacao(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        for args in ({"n0": 0}, {"n": 1}, {"n0": 5, "n": 5}, {"reamostras": 0}):
            with self.assertRaises(ValueError):
                C.kappa(xs, **args)
        with self.assertRaises(ValueError):
            C.kappa([1.0, 1.0, 1.0], n=3, reamostras=10)  # M(k) = 0

    # --- sobrevivência
    def test_sobrevivencia_loglog_decrescente(self):
        pts = C.sobrevivencia_loglog(self.pareto)
        self.assertTrue(pts)
        self.assertTrue(all(b[0] > a[0] and b[1] < a[1] for a, b in zip(pts, pts[1:])))
        self.assertTrue(all(math.isfinite(x) and math.isfinite(y) for x, y in pts))

    def test_sobrevivencia_loglog_exata(self):
        pts = C.sobrevivencia_loglog([0.0, -1.0, 2.0, -4.0, 4.0])  # |x| > 0: 1, 2, 4, 4
        self.assertEqual(len(pts), 2)  # o último valor distinto tem P = 0 e sai
        self.assertAlmostEqual(pts[0][0], 0.0)
        self.assertAlmostEqual(pts[0][1], math.log(3 / 4))
        self.assertAlmostEqual(pts[1][0], math.log(2))
        self.assertAlmostEqual(pts[1][1], math.log(2 / 4))
        self.assertEqual(C.sobrevivencia_loglog([]), [])
        self.assertEqual(C.sobrevivencia_loglog([0.0, 0.0]), [])

    # --- validação de entrada
    def test_entrada_vazia_ou_nao_finita(self):
        chamadas = [lambda x: C.razao_max_soma(x, 2), lambda x: C.hill(x, 1), lambda x: C.kappa(x, n=2, reamostras=5),
                    C.sobrevivencia_loglog]
        for f in chamadas:
            for ruim in ([float("nan"), 1.0, 2.0], [1.0, float("inf"), 2.0]):
                with self.assertRaises(ValueError):
                    f(ruim)
        for f in chamadas[:3]:
            with self.assertRaises(ValueError):
                f([])


if __name__ == "__main__":
    unittest.main()
