# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_evals.py
"""Incerto T18: suíte de evals (formato do evals/ do Lastro: prompt.md + graders/*.md) e o workflow manual
evals.yml. Conferência textual, sem PyYAML; nada toca a rede nem o modelo."""
import os
import re
import unittest
from _carga import RAIZ

EVALS = os.path.join(RAIZ, "evals")
WORKFLOW = os.path.join(RAIZ, ".github", "workflows", "evals.yml")
CASOS_ESPERADOS = ("incerto-taleb-nao-cita-staging", "incerto-taleb-wolfram-antes-de-afirmar",
                   "incerto-fiscal-duas-vias")
# Padrão de ticker da B3: 4 letras + 1 ou 2 dígitos (TESTE3 tem 5 letras: é o ticker sintético, não casa).
TICKER_B3 = re.compile(r"\b[A-Z]{4}[0-9]{1,2}\b")


def _ler(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


def _frontmatter(texto):
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    return m.group(1) if m else None


def _casos():
    return sorted(p for p in os.listdir(EVALS) if os.path.isdir(os.path.join(EVALS, p)) and p != "results")


class TesteFormato(unittest.TestCase):
    def test_os_tres_casos_existem(self):
        self.assertEqual(tuple(_casos()), tuple(sorted(CASOS_ESPERADOS)))

    def test_cada_caso_tem_prompt_com_frontmatter_e_graders(self):
        for caso in _casos():
            fm = _frontmatter(_ler(EVALS, caso, "prompt.md"))
            self.assertIsNotNone(fm, caso)
            for chave in ("name:", "tags:", "allowed_tools:"):
                self.assertIn(chave, fm, caso)
            graders = sorted(g for g in os.listdir(os.path.join(EVALS, caso, "graders")) if g.endswith(".md"))
            self.assertTrue(graders, caso)
            for g in graders:
                fg = _frontmatter(_ler(EVALS, caso, "graders", g))
                self.assertIsNotNone(fg, (caso, g))
                self.assertIn("type: llm", fg)
                self.assertIn("criteria:", fg)

    def test_readme_dos_evals_e_o_da_raiz_listam_os_casos(self):
        readme = _ler(EVALS, "README.md")
        for caso in _casos():
            self.assertIn("`%s`" % caso, readme)
        self.assertIn("`evals/`", _ler(RAIZ, "README.md"))

    def test_taleb_tem_grader_de_fecho_sem_recomendacao(self):
        for caso in ("incerto-taleb-nao-cita-staging", "incerto-taleb-wolfram-antes-de-afirmar"):
            todos = "\n".join(_ler(EVALS, caso, "graders", g) for g in os.listdir(os.path.join(EVALS, caso, "graders")))
            self.assertIn("Isto não é recomendação de ativo.", todos, caso)


class TesteProvas(unittest.TestCase):
    def test_nenhum_prompt_cita_ticker_real_da_b3(self):
        for caso in _casos():
            achados = TICKER_B3.findall(_ler(EVALS, caso, "prompt.md"))
            self.assertEqual(achados, [], caso)
        self.assertEqual(TICKER_B3.findall("TESTE3"), [])           # o sintético não casa
        self.assertEqual(TICKER_B3.findall("PETR4 e VALE3"), ["PETR4", "VALE3"])  # o padrão pega os reais

    def test_prompts_sao_autocontidos_com_dado_sintetico(self):
        for caso in _casos():
            p = _ler(EVALS, caso, "prompt.md")
            self.assertRegex(p, r"fictícia", caso)

    def test_cada_caso_tem_o_grader_da_declaracao_do_briefing(self):
        def todos(caso):
            return "\n".join(_ler(EVALS, caso, "graders", g) for g in os.listdir(os.path.join(EVALS, caso, "graders")))
        self.assertIn("`[corpus]` vem de nó em staging", todos("incerto-taleb-nao-cita-staging"))
        self.assertIn("Wolfram coladas", todos("incerto-taleb-wolfram-antes-de-afirmar"))
        self.assertRegex(todos("incerto-fiscal-duas-vias"), r"SymPy verde e Wolfram vermelho resulta em vermelho, nunca em aprovação")


class TesteWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = _ler(WORKFLOW)

    def test_so_workflow_dispatch(self):
        m = re.search(r"^on:\n((?:[ \t]+.*\n|\n)+)", self.y, re.M)
        self.assertIsNotNone(m)
        self.assertEqual(re.findall(r"^  (\w+):", m.group(1), re.M), ["workflow_dispatch"])
        self.assertNotRegex(self.y, r"(?m)^\s*(push|pull_request|schedule)\s*:")

    def test_usa_o_secret_e_roda_o_eval_na_raiz(self):
        self.assertIn("secrets.ANTHROPIC_API_KEY", self.y)
        self.assertIn("claude plugin eval .", self.y)
        self.assertNotIn("vars.", self.y)

    def test_cabecalho_avisa_custo_e_manual(self):
        cab = self.y.split("name:")[0]
        self.assertRegex(cab, r"CUSTA DINHEIRO")
        self.assertRegex(cab, r"MANUAL DE PROPÓSITO")


if __name__ == "__main__":
    unittest.main()
