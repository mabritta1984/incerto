# -*- coding: utf-8 -*-
"""Task 14: convexidade.py — assimetria (fragil/robusto/antifragil), Kelly, barbell, ergodicidade e
assimetria empírica por quantis."""
import math
import random
import unittest
from _carga import carregar

C = carregar("skills/taleb/scripts/convexidade.py")


class TesteConvexidade(unittest.TestCase):
    def test_assimetria_x2_antifragil_menos_x2_fragil_linear_robusto(self):
        self.assertAlmostEqual(C.assimetria(lambda x: x * x, 0.0, 1.0), 1.0)
        self.assertAlmostEqual(C.assimetria(lambda x: -x * x, 0.0, 1.0), -1.0)
        self.assertEqual(C.classificar(C.assimetria(lambda x: 3 * x, 2.0, 1.0)), "robusto")
        self.assertEqual(C.classificar(1.0), "antifragil")
        self.assertEqual(C.classificar(-1.0), "fragil")

    def test_classificar_respeita_a_tolerancia(self):
        self.assertEqual(C.classificar(1e-10), "robusto")
        self.assertEqual(C.classificar(-1e-10), "robusto")
        self.assertEqual(C.classificar(0.05, tol=0.1), "robusto")
        self.assertEqual(C.classificar(0.2, tol=0.1), "antifragil")

    def test_assimetria_delta_invalido(self):
        for d in (0.0, -1.0, math.nan, math.inf):
            with self.assertRaises(ValueError) as c:
                C.assimetria(lambda x: x, 0.0, d)
            self.assertIn("delta", str(c.exception))

    def test_kelly(self):
        self.assertAlmostEqual(C.kelly(0.6, 1.0), 0.2)
        self.assertAlmostEqual(C.kelly(0.5, 2.0), 0.25)

    def test_kelly_vantagem_negativa_devolve_o_valor_da_formula(self):
        self.assertAlmostEqual(C.kelly(0.3, 1.0), -0.4)

    def test_kelly_fora_do_dominio(self):
        for p, b in ((1.2, 1.0), (-0.1, 1.0), (0.5, 0.0), (0.5, -1.0), (math.nan, 1.0), (0.5, math.inf)):
            with self.assertRaises(ValueError) as c:
                C.kelly(p, b)
            self.assertRegex(str(c.exception), r"\b(p|b)\b")

    def test_barbell(self):
        r = C.barbell(0.9)
        self.assertAlmostEqual(r["perda_maxima_carteira"], 0.1)
        self.assertAlmostEqual(r["fracao_segura"], 0.9)
        self.assertAlmostEqual(r["fracao_convexa"], 0.1)
        self.assertAlmostEqual(C.barbell(0.9, 0.5)["perda_maxima_carteira"], 0.05)

    def test_barbell_fora_do_dominio(self):
        for args, nome in (((1.5,), "fracao_segura"), ((-0.1,), "fracao_segura"),
                           ((0.9, 1.5), "perda_maxima_convexa"), ((0.9, -0.1), "perda_maxima_convexa")):
            with self.assertRaises(ValueError) as c:
                C.barbell(*args)
            self.assertIn(nome, str(c.exception))

    def test_ergodicidade_moeda_de_taleb(self):
        r = [0.5, -0.4]
        self.assertAlmostEqual(C.crescimento_ensemble(r), 0.05)
        self.assertAlmostEqual(C.crescimento_temporal(r), math.log(0.9) / 2)
        self.assertLess(C.crescimento_temporal(r), 0)

    def test_ruina_da_crescimento_temporal_menos_infinito(self):
        self.assertEqual(C.crescimento_temporal([0.1, -1.0]), -math.inf)
        self.assertEqual(C.crescimento_temporal([0.1, -1.5]), -math.inf)
        self.assertAlmostEqual(C.crescimento_ensemble([0.1, -1.0]), -0.45)

    def test_ergodicidade_entrada_invalida(self):
        for f in (C.crescimento_temporal, C.crescimento_ensemble):
            with self.assertRaises(ValueError):
                f([])
            with self.assertRaises(ValueError):
                f([0.1, math.nan])

    def test_assimetria_empirica_simetrica_perto_de_zero(self):
        r = random.Random(11)
        base = [r.gauss(0, 1) for _ in range(5000)]
        amostra = base + [-x for x in base]
        self.assertAlmostEqual(C.assimetria_empirica(amostra), 0.0, places=9)

    def test_assimetria_empirica_assimetrica_a_direita_positiva(self):
        r = random.Random(11)
        amostra = [math.exp(r.gauss(0, 0.5)) for _ in range(5000)]
        self.assertGreater(C.assimetria_empirica(amostra), 0.1)
        self.assertLess(C.assimetria_empirica([-x for x in amostra]), -0.1)

    def test_assimetria_empirica_valida_entrada(self):
        for s in (0.0, -1.0, math.nan):
            with self.assertRaises(ValueError) as c:
                C.assimetria_empirica([1.0, 2.0, 3.0], sigmas=s)
            self.assertIn("sigmas", str(c.exception))
        with self.assertRaises(ValueError):
            C.assimetria_empirica([])


if __name__ == "__main__":
    unittest.main()
