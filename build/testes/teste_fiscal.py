# -*- coding: utf-8 -*-
"""Tasks 9 e 10: fiscal.py — fiscal algébrico por SymPy: P1 (parse), P2 (derivação declarada), P3 (condição
de validade); e a segunda via, P4: toda derivação e todo momento fechado exigem prova Wolfram registrada
e concordante. Os `srepr` saem do parser real da Task 8, para que o fiscal seja testado sobre exatamente
o que a extração produz."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from _carga import carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
EQ = sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
FI = carregar("skills/lavra/scripts/fiscal.py")
equivalente, relacional_parseia, provas_sympy = FI.equivalente, FI.relacional_parseia, FI.provas_sympy
provas, provas_wolfram = FI.provas, FI.provas_wolfram

ONDA = "2026-10-T9"


def srepr_de(latex):
    r = EQ.parsear_latex(latex)
    assert r["ok"], (latex, r["motivo"])
    return r["srepr"]


MAE_KELLY = r"\frac{p b}{1 + b f} - \frac{1 - p}{1 - f} = 0"
FILHA_KELLY = r"f = p - \frac{1 - p}{b}"


class TesteEquivalente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mae_kelly, cls.filha_kelly = srepr_de(MAE_KELLY), srepr_de(FILHA_KELLY)

    def test_p2_kelly_sai_da_condicao_de_primeira_ordem(self):
        self.assertEqual(equivalente(self.mae_kelly, self.filha_kelly, "f", {})["veredito"], "verde")

    def test_p2_filha_plantada_errada_e_vermelho_com_as_solucoes(self):
        r = equivalente(self.mae_kelly, srepr_de(r"f = p - (1 - p) b"), "f", {})
        self.assertEqual(r["veredito"], "vermelho")
        self.assertIn("f = ", r["detalhe"])

    def test_p2_razao_max_soma_invertida(self):
        self.assertEqual(equivalente(srepr_de("R = M/S"), srepr_de("S = M/R"), "S", {})["veredito"], "verde")

    def test_p2_alvo_ausente_e_indeterminado(self):
        self.assertEqual(equivalente(self.mae_kelly, self.filha_kelly, "q", {})["veredito"], "indeterminado")

    def test_p2_filha_que_nao_isola_o_alvo_e_indeterminado(self):
        r = equivalente(srepr_de("R = M/S"), srepr_de("R = M/S"), "S", {})
        self.assertEqual(r["veredito"], "indeterminado"); self.assertIn("S = ", r["detalhe"])

    def test_p2_sem_solucao_e_indeterminado(self):
        r = equivalente(srepr_de(r"y = \frac{1}{x} + y"), srepr_de("x = 1"), "x", {})
        self.assertEqual(r["veredito"], "indeterminado"); self.assertIn("solve não achou", r["detalhe"])

    def test_p2_mae_sem_igualdade_ou_substituicao_do_alvo_e_indeterminado(self):
        filha = srepr_de("S = M/R")
        self.assertEqual(equivalente(srepr_de("M/S"), filha, "S", {})["veredito"], "indeterminado")
        self.assertEqual(equivalente(srepr_de("R = M/S"), filha, "S", {"S": "2"})["veredito"], "indeterminado")
        self.assertEqual(equivalente(srepr_de("R = M/S"), filha, None, {})["veredito"], "indeterminado")

    def test_p2_substituicao_aplicada_aos_dois_lados(self):
        # mãe R = M/S com M := k*S² → R = k*S; a filha S = R/k só sai sob a substituição
        mae, filha = srepr_de("R = M/S"), srepr_de("S = R/k")
        self.assertEqual(equivalente(mae, filha, "S", {})["veredito"], "vermelho")
        self.assertEqual(equivalente(mae, filha, "S", {"M": "k*S**2"})["veredito"], "verde")

    def test_p2_pi_e_e_seguem_simbolos(self):
        self.assertEqual(equivalente(srepr_de(r"y = \pi x"), srepr_de(r"x = \frac{y}{\pi}"), "x", {})["veredito"], "verde")
        self.assertEqual(equivalente(srepr_de(r"y = \pi x"), srepr_de(r"x = \frac{y}{e}"), "x", {})["veredito"],
                         "vermelho")

    def test_p2_filha_que_escolhe_um_ramo_e_indeterminado(self):
        mae = srepr_de("y = x^{2}")
        for filha in (r"x = \sqrt{y}", r"x = -\sqrt{y}"):
            r = equivalente(mae, srepr_de(filha), "x", {})
            self.assertEqual(r["veredito"], "indeterminado", filha)
            self.assertIn("filha escolhe um ramo (1 de 2)", r["detalhe"])
            self.assertIn("sqrt(y)", r["detalhe"]); self.assertIn("-sqrt(y)", r["detalhe"])
        r = equivalente(srepr_de("x^{2} - 3 x + 2 = 0"), srepr_de("x = 2"), "x", {})
        self.assertEqual(r["veredito"], "indeterminado"); self.assertIn("(1 de 2)", r["detalhe"])

    def test_p2_lambda_na_substituicao(self):
        mae, filha = srepr_de(r"y = \lambda x"), srepr_de(r"x = \frac{y}{2 \mu}")
        self.assertEqual(equivalente(mae, filha, "x", {})["veredito"], "vermelho")
        self.assertEqual(equivalente(mae, filha, "x", {"lambda": "2*mu"})["veredito"], "verde")
        filha_l = srepr_de(r"x = \frac{y}{\lambda}")
        self.assertEqual(equivalente(srepr_de(r"y = k x"), filha_l, "x", {"k": "lambda"})["veredito"], "verde")

    def test_p2_substituicao_ilegivel_e_indeterminado(self):
        self.assertEqual(equivalente(self.mae_kelly, self.filha_kelly, "f", {"b": "(("})["veredito"], "indeterminado")


class TesteRelacional(unittest.TestCase):
    def test_p3_condicao_relacional_sobre_simbolos_da_equacao(self):
        self.assertTrue(relacional_parseia("alpha > 1", ["alpha", "L"]))
        self.assertFalse(relacional_parseia("beta > 1", ["alpha", "L"]))   # símbolo que a equação não USA

    def test_or_and_not_combinam_relacionais(self):
        self.assertTrue(relacional_parseia("kappa > 0.3 or alpha < 2", ["kappa", "alpha"]))
        self.assertTrue(relacional_parseia("alpha >= 1 and not (L <= 0)", ["alpha", "L"]))
        self.assertTrue(relacional_parseia("(alpha > 1) | (L < 0)", ["alpha", "L"]))
        self.assertFalse(relacional_parseia("kappa > 0.3 or beta < 2", ["kappa", "alpha"]))

    def test_constante_e_nao_relacional_nao_sao_condicao(self):
        for c in ("1 > 0", "True", "alpha", "alpha + 1", "alpha > 1 or 1 > 0", "", "alpha >"):
            self.assertFalse(relacional_parseia(c, ["alpha"]), c)

    def test_encadeada_e_funcao_indefinida_nao_sao_aceitas(self):
        self.assertFalse(relacional_parseia("0 < alpha < 1", ["alpha"]))
        self.assertFalse(relacional_parseia("g(alpha) > 1", ["alpha"]))
        self.assertTrue(relacional_parseia("log(alpha) > 1", ["alpha"]))

    def test_lambda_e_simbolo(self):
        self.assertTrue(relacional_parseia("lambda > 0", ["lambda", "x"]))
        self.assertTrue(relacional_parseia("lambda > 0 or x < lambda", ["lambda", "x"]))
        self.assertFalse(relacional_parseia("lambda > 0", ["x"]))

    def test_pi_e_e_sao_simbolos(self):
        self.assertTrue(relacional_parseia("x > pi", ["x", "pi"]))
        self.assertFalse(relacional_parseia("x > pi", ["x"]))
        self.assertTrue(relacional_parseia("Re < 2300", ["Re"]))


class TesteProvas(unittest.TestCase):
    def cand(self, nome, latex):
        r = EQ.parsear_latex(latex)
        return {"nome": nome, "latex": latex, "srepr": r["srepr"], "simbolos": r["simbolos"], "motivo": r["motivo"]}

    def test_p1_equacao_sem_srepr_e_vermelho_com_latex(self):
        linhas = provas_sympy([{"nome": "x", "latex": r"\Pr(X>x)", "srepr": None}], [], [])
        self.assertEqual((linhas[0]["prova"], linhas[0]["veredito"]), ("P1", "vermelho"))
        self.assertIn(r"\Pr", linhas[0]["detalhe"])

    def test_p1_p2_p3_em_ordem_com_ms(self):
        eqs = [self.cand("kelly#1", MAE_KELLY), self.cand("kelly#2", FILHA_KELLY)]
        ders = [{"filha": "kelly#2", "mae": "kelly#1", "alvo": "f", "substituicao": {}, "passo": "isola f"}]
        vals = [{"equacao": "kelly#2", "condicao": "b > 0"}, {"equacao": "kelly#2", "condicao": "q > 0"},
                {"equacao": "nada#9", "condicao": "b > 0"}]
        linhas = provas_sympy(eqs, ders, vals)
        self.assertEqual([(l["prova"], l["alvo"], l["veredito"]) for l in linhas],
                         [("P1", "kelly#1", "verde"), ("P1", "kelly#2", "verde"), ("P2", "kelly#2", "verde"),
                          ("P3", "kelly#2", "verde"), ("P3", "kelly#2", "vermelho"), ("P3", "nada#9", "vermelho")])
        self.assertIn("equação desconhecida", linhas[-1]["detalhe"])
        self.assertTrue(all(isinstance(l["ms"], int) for l in linhas))

    def test_linhas_distinguiveis_por_chaves_estruturadas(self):
        eqs = [self.cand("a#1", "R = M/S"), self.cand("a#2", "R = M/S + 0"), self.cand("a#3", "S = M/R")]
        ders = [{"filha": "a#3", "mae": "a#1", "alvo": "S", "substituicao": {}},
                {"filha": "a#3", "mae": "a#2", "alvo": "S", "substituicao": {"M": "M"}}]
        vals = [{"equacao": "a#3", "condicao": "M > 0"}, {"equacao": "a#3", "condicao": "R > 0"}]
        linhas = provas_sympy(eqs, ders, vals)
        p1 = [l for l in linhas if l["prova"] == "P1"]
        p2 = [l for l in linhas if l["prova"] == "P2"]
        p3 = [l for l in linhas if l["prova"] == "P3"]
        self.assertEqual([l["equacao"] for l in p1], ["a#1", "a#2", "a#3"])
        self.assertEqual([(l["mae"], l["filha"], l["simbolo"], l["substituicao"]) for l in p2],
                         [("a#1", "a#3", "S", {}), ("a#2", "a#3", "S", {"M": "M"})])
        self.assertEqual([(l["equacao"], l["condicao"]) for l in p3], [("a#3", "M > 0"), ("a#3", "R > 0")])
        self.assertTrue(all(l["alvo"] == "a#3" for l in p2 + p3))     # `alvo` mantido por compatibilidade

    def test_p2_equacao_desconhecida_ou_sem_srepr_e_vermelho(self):
        eqs = [self.cand("a#1", "R = M/S"), {"nome": "a#2", "latex": r"\Pr(X)", "srepr": None, "simbolos": []}]
        linhas = provas_sympy(eqs, [{"filha": "a#9", "mae": "a#1", "alvo": "S", "substituicao": {}},
                                    {"filha": "a#2", "mae": "a#1", "alvo": "S", "substituicao": {}}], [])
        p2 = [l for l in linhas if l["prova"] == "P2"]
        self.assertEqual([l["veredito"] for l in p2], ["vermelho", "vermelho"])
        self.assertIn("equação desconhecida", p2[0]["detalhe"]); self.assertIn("sem srepr", p2[1]["detalhe"])


SAIDA_ZERO = "Out[1]= 0"
SAIDA_ERRADA = "Out[1]= ((-1 + b^2)*(-1 + p))/b"


SEM_IMPRESSAO = "0" * 64


def _com_impressao(linha, onda):
    """`onda` = (equacoes, derivacoes): a impressão que o registrador gravaria; sem onda, uma qualquer."""
    linha["impressao"] = FI.impressao_esperada(FI.chave_wolfram(linha), *onda) if onda else SEM_IMPRESSAO
    return linha


def wolfram_p2(mae, filha, veredito, saida=SAIDA_ZERO, onda=None):
    return _com_impressao({"prova": "P2", "via": "wolfram", "mae": mae, "filha": filha, "veredito": veredito,
                           "saida": saida, "codigo": "Simplify[...]"}, onda)


def wolfram_momento(equacao, veredito, saida="Out[1]= 0", onda=None):
    return _com_impressao({"prova": "momento", "via": "wolfram", "equacao": equacao, "veredito": veredito,
                           "saida": saida, "codigo": "FullSimplify[...]"}, onda)


def indice(*linhas):
    return {FI.chave_wolfram(l): l for l in linhas}


class TesteP4(unittest.TestCase):
    def cand(self, nome, latex, **extra):
        r = EQ.parsear_latex(latex)
        return dict({"nome": nome, "latex": latex, "srepr": r["srepr"], "simbolos": r["simbolos"],
                     "motivo": r["motivo"]}, **extra)

    def setUp(self):
        self.eqs = [self.cand("kelly#1", MAE_KELLY), self.cand("kelly#2", FILHA_KELLY)]
        self.ders = [{"filha": "kelly#2", "mae": "kelly#1", "alvo": "f", "substituicao": {}, "passo": "isola f"}]

    def p4(self, linhas):
        return [l for l in linhas if l["prova"] == "P4"]

    def test_p4_deriva_de_sem_prova_wolfram_e_vermelho(self):
        linhas = provas(self.eqs, self.ders, [], {})
        self.assertEqual([l["prova"] for l in linhas], ["P1", "P1", "P2", "P4"])
        p4 = self.p4(linhas)[0]
        self.assertEqual((p4["veredito"], p4["alvo"], p4["mae"], p4["filha"]), ("vermelho", "kelly#2", "kelly#1", "kelly#2"))
        self.assertIn("sem prova Wolfram", p4["detalhe"])
        # prova de outra derivação não serve: a junção é por mãe + filha
        p4 = self.p4(provas(self.eqs, self.ders, [], indice(wolfram_p2("kelly#9", "kelly#2", "verde"))))[0]
        self.assertIn("sem prova Wolfram", p4["detalhe"])

    def test_p4_vias_divergem_e_vermelho_com_as_duas_saidas(self):
        linhas = provas(self.eqs, self.ders, [], indice(wolfram_p2("kelly#1", "kelly#2", "vermelho", SAIDA_ERRADA,
                                                                       (self.eqs, self.ders))))
        p2 = [l for l in linhas if l["prova"] == "P2"][0]
        p4 = self.p4(linhas)[0]
        self.assertEqual((p2["veredito"], p4["veredito"]), ("verde", "vermelho"))
        self.assertIn("vias divergem", p4["detalhe"])
        self.assertIn(p2["detalhe"], p4["detalhe"])          # a saída da via SymPy
        self.assertIn(SAIDA_ERRADA, p4["detalhe"])           # e a da via Wolfram, verbatim

    def test_p4_vias_concordam_e_verde(self):
        p4 = self.p4(provas(self.eqs, self.ders, [], indice(wolfram_p2("kelly#1", "kelly#2", "verde", onda=(self.eqs, self.ders)))))[0]
        self.assertEqual(p4["veredito"], "verde")
        self.assertIn("vias concordam", p4["detalhe"]); self.assertIn(SAIDA_ZERO, p4["detalhe"])
        self.assertEqual(sorted(p4), ["alvo", "detalhe", "filha", "mae", "ms", "prova", "veredito"])

    def test_p4_sympy_indeterminado_e_wolfram_verde_divergem(self):
        eqs = [self.cand("q#1", "y = x^{2}"), self.cand("q#2", r"x = \sqrt{y}")]
        ders = [{"filha": "q#2", "mae": "q#1", "alvo": "x", "substituicao": {}}]
        linhas = provas(eqs, ders, [], indice(wolfram_p2("q#1", "q#2", "verde", onda=(eqs, ders))))
        self.assertEqual([l["veredito"] for l in linhas if l["prova"] in ("P2", "P4")], ["indeterminado", "vermelho"])
        self.assertIn("vias divergem", self.p4(linhas)[0]["detalhe"])

    def test_p4_vias_que_concordam_no_vermelho_seguem_vermelho(self):
        eqs = self.eqs + [self.cand("kelly#3", r"f = p - (1 - p) b")]
        ders = [{"filha": "kelly#3", "mae": "kelly#1", "alvo": "f", "substituicao": {}}]
        p4 = self.p4(provas(eqs, ders, [], indice(wolfram_p2("kelly#1", "kelly#3", "vermelho", SAIDA_ERRADA,
                                                                        (eqs, ders)))))[0]
        self.assertEqual(p4["veredito"], "vermelho"); self.assertIn("vias concordam", p4["detalhe"])

    def test_momento_pareto_exige_wolfram(self):
        eqs = self.eqs + [self.cand("pareto#3", r"m = \frac{\alpha L}{\alpha - 1}",
                                    momento_fechado={"media": "alpha*L/(alpha-1)"}),
                          self.cand("pareto#4", "m = L", momento_fechado={})]          # vazio = não declarado
        p4 = self.p4(provas(eqs, [], [], {}))
        self.assertEqual([(l["alvo"], l["equacao"], l["veredito"]) for l in p4], [("pareto#3", "pareto#3", "vermelho")])
        self.assertIn("sem prova Wolfram", p4[0]["detalhe"])
        saida = "Out[1]= 0"
        p4 = self.p4(provas(eqs, [], [], indice(wolfram_momento("pareto#3", "verde", saida, (eqs, [])))))
        self.assertEqual(p4[0]["veredito"], "verde"); self.assertIn(saida, p4[0]["detalhe"])
        self.assertEqual(sorted(p4[0]), ["alvo", "detalhe", "equacao", "ms", "prova", "veredito"])
        for v in ("vermelho", "indeterminado"):
            p4 = self.p4(provas(eqs, [], [], indice(wolfram_momento("pareto#3", v, "Out[1]= alpha", (eqs, [])))))
            self.assertEqual(p4[0]["veredito"], v); self.assertIn("Out[1]= alpha", p4[0]["detalhe"])

    def test_p4_mae_e_filha_repetidas_sao_derivacao_ambigua_em_todas(self):
        ders = self.ders + [dict(self.ders[0], substituicao={"b": "2"})]
        w = wolfram_p2("kelly#1", "kelly#2", "verde", onda=(self.eqs, self.ders))   # válida para a primeira
        p4 = self.p4(provas(self.eqs, ders, [], indice(w)))
        self.assertEqual([l["veredito"] for l in p4], ["vermelho", "vermelho"])
        for l in p4:
            self.assertIn("derivação ambígua para a prova Wolfram", l["detalhe"])
        self.assertEqual([l["veredito"] for l in self.p4(provas(self.eqs, ders, [], {}))], ["vermelho", "vermelho"])

    def test_p2_desatualizada_depois_de_mudar_o_srepr_e_vermelho(self):
        w = wolfram_p2("kelly#1", "kelly#2", "verde", onda=(self.eqs, self.ders))
        self.assertEqual(self.p4(provas(self.eqs, self.ders, [], indice(w)))[0]["veredito"], "verde")
        reextraida = [self.eqs[0], self.cand("kelly#2", r"f = p - \frac{1 - p}{b} + 0 \cdot q")]
        self.assertNotEqual(reextraida[1]["srepr"], self.eqs[1]["srepr"])
        p4 = self.p4(provas(reextraida, self.ders, [], indice(w)))[0]
        self.assertEqual(p4["veredito"], "vermelho"); self.assertIn("prova Wolfram desatualizada", p4["detalhe"])
        # trocar a substituição declarada também desatualiza
        p4 = self.p4(provas(self.eqs, [dict(self.ders[0], substituicao={"q": "1"})], [], indice(w)))[0]
        self.assertIn("prova Wolfram desatualizada", p4["detalhe"])

    def test_momento_desatualizado_depois_de_editar_o_momento_fechado_e_vermelho(self):
        eqs = [self.cand("pareto#3", r"m = \frac{\alpha L}{\alpha - 1}", momento_fechado={"media": "alpha*L/(alpha-1)"})]
        w = wolfram_momento("pareto#3", "verde", "Out[1]= 0", (eqs, []))
        self.assertEqual(self.p4(provas(eqs, [], [], indice(w)))[0]["veredito"], "verde")
        editada = [dict(eqs[0], momento_fechado={"media": "alpha*L/(alpha-2)"})]
        p4 = self.p4(provas(editada, [], [], indice(w)))[0]
        self.assertEqual(p4["veredito"], "vermelho"); self.assertIn("prova Wolfram desatualizada", p4["detalhe"])

    def test_impressao_e_sha256_do_conteudo_declarado(self):
        conteudo = {"mae_srepr": self.eqs[0]["srepr"], "filha_srepr": self.eqs[1]["srepr"], "simbolo": "f",
                    "substituicao": {}}
        self.assertEqual(FI.impressao_esperada(("P2", "kelly#1", "kelly#2"), self.eqs, self.ders),
                         hashlib.sha256(json.dumps(conteudo, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest())
        for chave, ders in ((("P2", "kelly#2", "kelly#1"), self.ders), (("P2", "kelly#1", "kelly#2"), self.ders * 2),
                            (("momento", "kelly#1"), self.ders), (("momento", "nada#1"), self.ders)):
            with self.assertRaises(ValueError, msg=chave):
                FI.impressao_esperada(chave, self.eqs, ders)

    def test_p4_vem_depois_de_p1_p2_p3_e_provas_sympy_nao_muda(self):
        eqs = self.eqs + [self.cand("pareto#3", "m = L", momento_fechado={"media": "L"})]
        vals = [{"equacao": "kelly#2", "condicao": "b > 0"}]
        self.assertEqual([l["prova"] for l in provas(eqs, self.ders, vals, {})], ["P1"] * 3 + ["P2", "P3", "P4", "P4"])
        self.assertEqual([l["prova"] for l in provas_sympy(eqs, self.ders, vals)], ["P1"] * 3 + ["P2", "P3"])


class TesteProvasWolfram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.caminho = os.path.join(self.tmp, "provas.jsonl")

    def escrever(self, linhas):
        with io.open(self.caminho, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n" for l in linhas)

    def test_le_e_indexa_por_chave(self):
        self.escrever([wolfram_p2("a#1", "a#2", "verde"), wolfram_momento("p#3", "vermelho")])
        d = provas_wolfram(self.caminho)
        self.assertEqual(sorted(d), [("P2", "a#1", "a#2"), ("momento", "p#3")])
        self.assertEqual(d[("momento", "p#3")]["veredito"], "vermelho")

    def test_arquivo_ausente_e_nenhuma_prova(self):
        self.assertEqual(provas_wolfram(os.path.join(self.tmp, "nao-existe.jsonl")), {})

    def test_duplicata_ou_linha_malformada_falha_alto(self):
        for linhas in ([wolfram_p2("a#1", "a#2", "verde"), wolfram_p2("a#1", "a#2", "vermelho")],
                       [dict(wolfram_p2("a#1", "a#2", "verde"), via="sympy")],
                       [dict(wolfram_p2("a#1", "a#2", "verde"), prova="P5")],
                       [dict(wolfram_momento("p#3", "verde"), veredito="talvez")],
                       [dict(wolfram_momento("p#3", "verde"), impressao="abc")],
                       [{k: v for k, v in wolfram_momento("p#3", "verde").items() if k != "impressao"}],
                       [{"prova": "P2", "via": "wolfram", "mae": "a#1", "veredito": "verde", "saida": "0"}]):
            self.escrever(linhas)
            with self.assertRaises(ValueError, msg=linhas):
                provas_wolfram(self.caminho)


class TesteCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def escrever(self, prefixo, linhas):
        with io.open(os.path.join(self.tmp, "%s-%s.jsonl" % (prefixo, ONDA)), "w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n" for l in linhas)

    def rodar(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return FI.main(["--onda", ONDA, "--raiz-esteira", self.tmp] + list(extra))

    def ler(self, nome):
        with io.open(os.path.join(self.tmp, nome), encoding="utf-8", newline="") as f:
            return f.read()

    def preparar(self):
        r = EQ.parsear_latex("R = M/S"); s = EQ.parsear_latex("S = M/R")
        self.escrever("equacoes", [
            {"nome": "r#1", "latex": "R = M/S", "srepr": r["srepr"], "simbolos": r["simbolos"], "motivo": None},
            {"nome": "r#2", "latex": "S = M/R", "srepr": s["srepr"], "simbolos": s["simbolos"], "motivo": None},
            {"nome": "r#3", "latex": r"\Pr(X > x) | y", "srepr": None, "simbolos": [], "motivo": r"nao_suportado:\Pr"}])
        self.escrever("derivacoes", [{"filha": "r#2", "mae": "r#1", "alvo": "S", "substituicao": {}, "passo": "isola S"}])
        self.onda = (self.ler_linhas("equacoes"), self.ler_linhas("derivacoes"))

    def ler_linhas(self, prefixo):
        return [json.loads(l) for l in self.ler("%s-%s.jsonl" % (prefixo, ONDA)).splitlines()]

    def test_relatorio_tem_coluna_ms(self):
        self.preparar()
        md = os.path.join(self.tmp, "rel.md")
        self.assertEqual(self.rodar("--relatorio", md), 0)
        texto = self.ler("rel.md")
        self.assertIn("| prova | alvo | veredito | detalhe | ms |", texto)
        self.assertIn(r"\|", texto)      # o `|` do LaTeX não quebra a tabela
        self.assertEqual(len([l for l in texto.splitlines() if l.startswith("| P")]), 5)   # P1×3, P2, P4

    def test_jsonl_sem_ms_ordenado_e_deterministico(self):
        self.preparar()
        self.rodar(); primeiro = self.ler("fiscal-%s.jsonl" % ONDA)
        self.rodar(); self.assertEqual(self.ler("fiscal-%s.jsonl" % ONDA), primeiro)
        linhas = [json.loads(l) for l in primeiro.splitlines()]
        self.assertEqual([sorted(l) for l in linhas],
                         [["alvo", "detalhe", "equacao", "prova", "veredito"]] * 3
                         + [["alvo", "detalhe", "filha", "mae", "prova", "simbolo", "substituicao", "veredito"]]
                         + [["alvo", "detalhe", "filha", "mae", "prova", "veredito"]])
        self.assertEqual([l["veredito"] for l in linhas], ["verde", "verde", "vermelho", "verde", "vermelho"])
        for l in primeiro.splitlines():
            self.assertEqual(l, json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "fiscal-%s.md" % ONDA)))   # relatório no padrão

    def test_derivacoes_e_validades_ausentes_sao_nenhuma_declaracao(self):
        r = EQ.parsear_latex("R = M/S")
        self.escrever("equacoes", [{"nome": "r#1", "latex": "R = M/S", "srepr": r["srepr"], "simbolos": r["simbolos"]}])
        self.assertEqual(self.rodar(), 0)
        self.assertEqual([json.loads(l)["prova"] for l in self.ler("fiscal-%s.jsonl" % ONDA).splitlines()], ["P1"])

    def test_sem_equacoes_falha_alto(self):
        with self.assertRaises(SystemExit):
            self.rodar()

    def p4_do_jsonl(self):
        return [json.loads(l) for l in self.ler("fiscal-%s.jsonl" % ONDA).splitlines() if '"P4"' in l]

    def test_provas_wolfram_no_caminho_padrao_e_no_declarado(self):
        self.preparar()
        self.rodar("--provas-wolfram", os.path.join(self.tmp, "nao-existe.jsonl"))
        self.assertIn("sem prova Wolfram", self.p4_do_jsonl()[0]["detalhe"])
        self.escrever("provas", [wolfram_p2("r#1", "r#2", "verde", onda=self.onda)])   # <raiz>/provas-<onda>.jsonl
        self.rodar()
        self.assertEqual(self.p4_do_jsonl()[0]["veredito"], "verde")
        outro = os.path.join(self.tmp, "outro.jsonl")
        with io.open(outro, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(wolfram_p2("r#1", "r#2", "vermelho", SAIDA_ERRADA, self.onda), sort_keys=True) + "\n")
        self.rodar("--provas-wolfram", outro)
        p4 = self.p4_do_jsonl()[0]
        self.assertEqual(p4["veredito"], "vermelho"); self.assertIn("vias divergem", p4["detalhe"])

    def test_provas_wolfram_malformadas_falham_alto(self):
        self.preparar()
        self.escrever("provas", [wolfram_p2("r#1", "r#2", "verde")] * 2)
        with self.assertRaises(SystemExit):
            self.rodar()

    def test_onda_invalida_e_recusada(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            FI.main(["--onda", "../x", "--raiz-esteira", self.tmp])


if __name__ == "__main__":
    unittest.main()
