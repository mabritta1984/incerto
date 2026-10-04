# -*- coding: utf-8 -*-
"""Task 8: extrair_equacoes.py — LaTeX → `srepr` do SymPy com a definição estrita de "parseável"
(`parse_latex(strict=True)` + normalização de símbolos compostos + conferência dos símbolos contra o
LaTeX), perda declarada com o LaTeX preservado, candidatos a `:Equacao` em staging e a coluna
"parseáveis pelo SymPy" do portão (decisão 1b)."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from _carga import RAIZ, carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
EQ = sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
CO = carregar("skills/lavra/scripts/conferir_onda.py")
parsear_latex, normalizar_latex, equacoes_do_documento = EQ.parsear_latex, EQ.normalizar_latex, EQ.equacoes_do_documento

FIXTURES = os.path.join(RAIZ, "build", "testes", "fixtures")
ONDA = "2026-09-PSX-1"
MOGHADDAM = "2018-Moghaddam-13b9e4a8-cf24-a1af-4306-2196b6b7d1e3.pdf"


class TesteParse(unittest.TestCase):
    def test_kelly_parseia_com_dois_simbolos_e_b(self):
        r = parsear_latex(r"f^{*} = p - \frac{1 - p}{b}")
        self.assertTrue(r["ok"]); self.assertEqual(sorted(r["simbolos"]), ["b", "f_star", "p"])   # `^{*}` normaliza para `_star`
        self.assertIsNone(r["motivo"])
        self.assertTrue(r["srepr"].startswith("Equality("))

    def test_subscrito_composto_e_simbolo_unico(self):
        r = parsear_latex(r"T_{max} - T_{min}")
        self.assertEqual(sorted(r["simbolos"]), ["T_max", "T_min"])

    def test_nome_de_duas_letras_partido_e_perda(self):
        r = parsear_latex(r"TC = a")
        self.assertFalse(r["ok"]); self.assertTrue(r["motivo"].startswith("simbolo_partido"))
        self.assertEqual(r["motivo"], "simbolo_partido:TC")
        self.assertIsNone(r["srepr"])

    def test_forall_e_perda_em_strict(self):
        self.assertFalse(parsear_latex(r"\forall i, x_i > 0")["ok"])

    def test_esperanca_vira_funcao(self):
        r = parsear_latex(r"\mathbb{E}[X] = \frac{\alpha L}{\alpha - 1}")
        self.assertTrue(r["ok"]); self.assertIn("Function('E')", r["srepr"])
        self.assertEqual(sorted(r["simbolos"]), ["L", "X", "alpha"])

    def test_pr_e_dx_sao_perda_declarada_com_latex_preservado(self):
        for latex in (r"\Pr(X > x) = x^{-\alpha}", r"\int f(x)\,\mathrm{d}x"):
            r = parsear_latex(latex); self.assertFalse(r["ok"]); self.assertTrue(r["motivo"].startswith("nao_suportado"))
        self.assertEqual(parsear_latex(r"\Pr(X > x) = x^{-\alpha}")["motivo"], r"nao_suportado:\Pr")
        self.assertEqual(parsear_latex(r"\int f(x)\,\mathrm{d}x")["motivo"], r"nao_suportado:\mathrm{d}")

    def test_aligned_e_perda_antes_do_parse(self):
        r = parsear_latex("\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}")
        self.assertEqual(r["motivo"], r"nao_suportado:\begin{aligned}")

    def test_mathit_explicito_e_simbolo_unico(self):
        r = parsear_latex(r"\mathit{TC} = a")
        self.assertTrue(r["ok"]); self.assertEqual(sorted(r["simbolos"]), ["TC", "a"])

    def test_comando_virando_simbolo_nunca_passa(self):
        # o parser do SymPy aceita estes em strict, mas com símbolos falsos (mathrm, operatorname, dots...)
        for latex in (r"\mathrm{TC} = a", r"a \dots b", r"\text{if } x", r"\mathbb{R}"):
            r = parsear_latex(latex)
            self.assertFalse(r["ok"], latex)

    def test_subscrito_simples_canonico(self):
        r = parsear_latex(r"x_{1} + x_2 + \alpha_i")
        self.assertTrue(r["ok"]); self.assertEqual(sorted(r["simbolos"]), ["alpha_i", "x_1", "x_2"])

    def test_tag_e_pontuacao_final_nao_contam(self):
        r = parsear_latex(r"Y_i = P_d \times A \tag{3}")
        self.assertTrue(r["ok"]); self.assertEqual(sorted(r["simbolos"]), ["A", "P_d", "Y_i"])
        self.assertTrue(parsear_latex(r"y = a b,")["ok"])

    def test_relacao_encadeada_e_perda(self):
        self.assertEqual(parsear_latex(r"a = b = c")["motivo"], "nao_suportado:relacao_encadeada")
        self.assertFalse(parsear_latex(r"1 \le x \le n")["ok"])     # o SymPy recusa (TypeError): `strict`

    def test_subscrito_simples_nao_engole_o_comando_seguinte(self):
        # sem chaves, o parser lê `P_d \times A` como Symbol('P_{dtimes}')·A — a conferência pegaria, mas é parseável
        r = parsear_latex(r"P_d \times A")
        self.assertTrue(r["ok"]); self.assertEqual(sorted(r["simbolos"]), ["A", "P_d"])

    def test_operatorname_vira_funcao(self):
        r = parsear_latex(r"\operatorname{Var}(X) = \sigma^{2}")
        self.assertTrue(r["ok"]); self.assertIn("Function('Var')", r["srepr"])
        self.assertEqual(sorted(r["simbolos"]), ["X", "sigma"])
        self.assertIn("Function('E')", parsear_latex(r"\operatorname{E}(X) = \mu")["srepr"])

    def test_max_e_min_sao_os_do_sympy(self):
        r = parsear_latex(r"y = \max(a, b)")
        self.assertTrue(r["ok"]); self.assertIn("Max(", r["srepr"]); self.assertNotIn("Function('max')", r["srepr"])

    def test_composto_aplicado_e_ambiguo(self):
        r = parsear_latex(r"T_{max}(t) = 1")
        self.assertFalse(r["ok"]); self.assertTrue(r["motivo"].startswith("nao_suportado"))

    def test_erro_do_parser_e_strict(self):
        self.assertEqual(parsear_latex(r"\frac{1}{")["motivo"], "strict")

    def test_normalizar(self):
        self.assertEqual(normalizar_latex(r"T_{max} - f^{*}"), r"\mathit{T_max} - \mathit{f_star}")
        self.assertEqual(normalizar_latex(r"\mathbb{E}[X]"), "E(X)")
        self.assertEqual(normalizar_latex(r"\operatorname{Var}(X)"), r"\operatorname{Var}(X)")
        self.assertEqual(normalizar_latex(r"\left( x_{1} \right) \tag{2}"), "( x_1 )")

    def test_deterministico(self):
        a = parsear_latex(r"\frac{p b}{1 + b f} - \frac{1 - p}{1 - f} = 0")
        self.assertEqual(a, parsear_latex(r"\frac{p b}{1 + b f} - \frac{1 - p}{1 - f} = 0"))


class TesteDocumento(unittest.TestCase):
    def test_equacoes_do_documento_herdam_topico(self):
        md = "## Kelly\n\ntexto\n\n$$f = p - \\frac{1-p}{b}$$\n\n## Pareto\n\n$$E = 3$$\n"
        eqs = equacoes_do_documento(md, "Statistical_Consequences_of_Fat_Tails.pdf.md")
        self.assertEqual([e["topico"] for e in eqs], ["Kelly", "Pareto"]); self.assertEqual(eqs[0]["ordem"], 1)
        self.assertEqual([e["ordem"] for e in eqs], [1, 2])
        self.assertEqual(eqs[0]["documento"], "Statistical_Consequences_of_Fat_Tails.pdf.md")
        self.assertEqual(eqs[0]["latex"], "f = p - \\frac{1-p}{b}")

    def test_abertura_multilinha_e_topico_repetido_como_no_recorte(self):
        md = "$$\na = b\n$$\n\n# Parte A\n\n## Kelly\n\n$$x = 1$$\n\n# Parte B\n\n## Kelly\n\n$$y = 2$$\n"
        eqs = equacoes_do_documento(md, "X.pdf.md")
        self.assertEqual([e["topico"] for e in eqs], ["(abertura)", "Kelly — Parte A", "Kelly — Parte B"])
        self.assertEqual(eqs[0]["latex"], "a = b")


def _corpus(raiz):
    """conferidos/<onda>/ com os .md da fixture e o que não é documento (pulado)."""
    ext = os.path.join(FIXTURES, "extraidos", ONDA)
    conf = os.path.join(raiz, "conferidos", ONDA)
    shutil.copytree(ext, conf)
    with io.open(os.path.join(conf, "manifesto.json"), "w", encoding="utf-8") as f:
        f.write("{}\n")
    os.makedirs(os.path.join(conf, MOGHADDAM + ".assets"))
    with io.open(os.path.join(conf, MOGHADDAM + ".assets", "nota.md"), "w", encoding="utf-8") as f:
        f.write("$$a = b$$\n")
    return conf


class TesteCLI(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="incerto-eq-")
        _corpus(self.raiz)
        self.saida = os.path.join(self.raiz, "_esteira", "incerto", "equacoes-%s.jsonl" % ONDA)

    def tearDown(self):
        shutil.rmtree(self.raiz)

    def rodar(self, onda=ONDA, saida=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return EQ.main(["--raiz", self.raiz, "--onda", onda, "--saida", saida or self.saida])

    def linhas(self):
        with io.open(self.saida, encoding="utf-8", newline="") as f:
            return f.read()

    def test_candidatos_em_staging(self):
        self.assertEqual(self.rodar(), 0)
        texto = self.linhas()
        self.assertNotIn("\r", texto)
        cands = [json.loads(l) for l in texto.splitlines()]
        self.assertEqual(len(cands), 15)                      # 11 blocos no Guan + 4 no Moghaddam; .assets e lote pulados
        docs = [c["fonte"]["documento"] for c in cands]
        self.assertEqual(docs, sorted(docs, key=lambda s: s.encode("utf-8")))
        for c in cands:
            self.assertEqual(c["status"], "staging")
            self.assertEqual(c["nome"], "%s#%d" % (c["fonte"]["documento"], c["ordem"]))
            self.assertEqual(c["forma"], "perda" if c["srepr"] is None else c["forma"])
            self.assertEqual([v["nome"] for v in c["variaveis"]], c["simbolos"])
            self.assertTrue(c["latex"])
        ok = [c for c in cands if c["forma"] != "perda"]
        self.assertEqual(len(ok), 1)
        self.assertEqual(ok[0]["forma"], "algebrica")
        self.assertEqual(ok[0]["simbolos"], ["A", "D_f", "D_o", "D_s", "P_d", "Y_i"])
        self.assertEqual(ok[0]["fonte"], {"documento": MOGHADDAM + ".md", "topico": ok[0]["fonte"]["topico"]})
        tc2 = [c for c in cands if c["latex"].startswith(r"TC = \frac")][0]
        self.assertEqual(tc2["motivo"], "simbolo_partido:TC")      # `C` partido vem de `TC`, não de `C_i`
        tc = [c for c in cands if c["latex"].startswith("TC = Y_i")][0]
        self.assertEqual((tc["forma"], tc["motivo"], tc["srepr"]), ("perda", "simbolo_partido:TC", None))
        self.assertIn(r"\tag{4}", tc["latex"])                 # LaTeX preservado como veio
        for linha in texto.splitlines():
            self.assertEqual(linha, json.dumps(json.loads(linha), sort_keys=True, ensure_ascii=False))

    def test_forma_funcional_sem_igual(self):
        conf = os.path.join(self.raiz, "conferidos", "f")
        os.makedirs(conf)
        with io.open(os.path.join(conf, "A.pdf.md"), "w", encoding="utf-8") as f:
            f.write("## T\n\n$$T_{max} - T_{min}$$\n")
        saida = os.path.join(self.raiz, "f.jsonl")
        self.assertEqual(self.rodar("f", saida), 0)
        with io.open(saida, encoding="utf-8") as f:
            c = json.loads(f.read())
        self.assertEqual((c["forma"], c["simbolos"], c["fonte"]), ("funcional", ["T_max", "T_min"],
                                                                  {"documento": "A.pdf.md", "topico": "T"}))

    def test_reexecucao_identica_e_nao_reescreve_edicao_do_po(self):
        self.rodar()
        antes = self.linhas()
        self.assertEqual(self.rodar(), 0)
        self.assertEqual(self.linhas(), antes)
        with io.open(self.saida, "w", encoding="utf-8", newline="\n") as f:
            f.write(antes.replace("#1\"", "#1-renomeada\"", 1))
        editado = self.linhas()
        with self.assertRaises(SystemExit):
            self.rodar()
        self.assertEqual(self.linhas(), editado)

    def test_onda_invalida_e_onda_ausente(self):
        for onda in ("../x", "nao-existe"):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.rodar(onda)


class TestePortao(unittest.TestCase):
    def test_conferir_onda_mede_parseaveis(self):  # decisão 1b
        # a fixture de Task 5 passa a mostrar um número na coluna, não "não medido"
        docs = CO.ler_onda(os.path.join(FIXTURES, "extraidos", ONDA))
        md = CO.relatorio_md(ONDA, docs, CO.resumir(docs))
        m = re.search(r"^\| parseáveis pelo SymPy \| (\d+)/(\d+) \|$", md, re.M)
        self.assertIsNotNone(m, md)
        self.assertEqual((int(m.group(1)), int(m.group(2))), (1, 15))
        self.assertNotIn("não medido", md)
        self.assertEqual(CO.resumir(docs)["equacoes"]["parseaveis_sympy"], {"parseaveis": 1, "total": 15})


if __name__ == "__main__":
    unittest.main()
