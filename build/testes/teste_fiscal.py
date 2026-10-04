# -*- coding: utf-8 -*-
"""Task 9: fiscal.py — fiscal algébrico por SymPy: P1 (parse), P2 (derivação declarada), P3 (condição de
validade). Os `srepr` saem do parser real da Task 8, para que o fiscal seja testado sobre exatamente o
que a extração produz."""
import contextlib
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

    def test_relatorio_tem_coluna_ms(self):
        self.preparar()
        md = os.path.join(self.tmp, "rel.md")
        self.assertEqual(self.rodar("--relatorio", md), 0)
        texto = self.ler("rel.md")
        self.assertIn("| prova | alvo | veredito | detalhe | ms |", texto)
        self.assertIn(r"\|", texto)      # o `|` do LaTeX não quebra a tabela
        self.assertEqual(len([l for l in texto.splitlines() if l.startswith("| P")]), 4)

    def test_jsonl_sem_ms_ordenado_e_deterministico(self):
        self.preparar()
        self.rodar(); primeiro = self.ler("fiscal-%s.jsonl" % ONDA)
        self.rodar(); self.assertEqual(self.ler("fiscal-%s.jsonl" % ONDA), primeiro)
        linhas = [json.loads(l) for l in primeiro.splitlines()]
        self.assertEqual([sorted(l) for l in linhas],
                         [["alvo", "detalhe", "equacao", "prova", "veredito"]] * 3
                         + [["alvo", "detalhe", "filha", "mae", "prova", "simbolo", "substituicao", "veredito"]])
        self.assertEqual([l["veredito"] for l in linhas], ["verde", "verde", "vermelho", "verde"])
        for l in primeiro.splitlines():
            self.assertEqual(l, json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "fiscal-%s.md" % ONDA)))   # relatório no padrão

    def test_derivacoes_e_validades_ausentes_sao_nenhuma_declaracao(self):
        r = EQ.parsear_latex("R = M/S")
        self.escrever("equacoes", [{"nome": "r#1", "latex": "R = M/S", "srepr": r["srepr"], "simbolos": r["simbolos"]}])
        self.assertEqual(self.rodar(), 0)
        self.assertEqual([json.loads(l)["prova"] for l in self.ler("fiscal-%s.jsonl" % ONDA).splitlines()], ["P1"])

    def test_sem_equacoes_falha_alto_e_wolfram_aceito(self):
        with self.assertRaises(SystemExit):
            self.rodar()
        self.preparar()
        self.assertEqual(self.rodar("--provas-wolfram", os.path.join(self.tmp, "nao-existe.jsonl")), 0)

    def test_onda_invalida_e_recusada(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            FI.main(["--onda", "../x", "--raiz-esteira", self.tmp])


if __name__ == "__main__":
    unittest.main()
