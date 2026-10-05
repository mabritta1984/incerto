# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_extracao_nuvem.py
"""Jazida V3.1: references/extracao-nuvem.md — o contrato de consumo do que o mineiro grava no bucket."""
import os
import re
import unittest
from _carga import RAIZ

CAMINHO = os.path.join(RAIZ, "skills", "lavra", "references", "extracao-nuvem.md")


class TesteExtracaoNuvem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CAMINHO, encoding="utf-8") as f:
            cls.t = f.read()

    def test_dono_unico_e_fronteira_com_o_mineiro(self):
        self.assertIn("dono único", self.t)
        self.assertIn("mineiro", self.t)
        self.assertIn("não descreve o conversor", self.t)

    def test_layout_do_bucket(self):
        for prefixo in ("originais/<fonte>/", "extraidos/<onda>/", "conferidos/<onda>/", "_esteira/"):
            self.assertIn(prefixo, self.t)
        self.assertIn("versionamento", self.t)

    def test_o_que_o_mineiro_grava_por_documento_e_por_lote(self):
        for artefato in ("<nome>.<ext>.md", "<nome>.<ext>.report.json", "<nome>.<ext>.assets/", "lote-<data>.md"):
            self.assertIn(artefato, self.t)
        for chave in ("generated_at", "source", "summary", "items", "item_id", "route", "approved", "fallback"):
            self.assertIn("`%s`" % chave, self.t)

    def test_regra_do_validador(self):
        self.assertIn('summary.equacoes.validador', self.t)
        self.assertIn('"katex"', self.t)
        self.assertIn("equacoes_detectadas == 0", self.t)

    def test_soma_pelos_relatorios_nunca_pelo_lote(self):
        self.assertRegex(self.t, r"nunca\s+(pelo|do)\s+`lote-")

    def test_manifesto_da_onda(self):
        self.assertIn("manifesto.json", self.t)
        for campo in ("sha256", "motivos", "veredito", "perdas"):
            self.assertIn(campo, self.t)

    def test_rota_de_pdf_sem_camada_de_texto(self):
        self.assertIn("paginas_sem_texto", self.t)
        self.assertIn("sem camada de texto", self.t)

    def test_portao_do_po(self):
        self.assertIn("portão do PO", self.t)
        self.assertIn("conferir_onda.py", self.t)
        self.assertIn("--aprovar", self.t)

    def test_nao_ensina_a_converter(self):
        # O Jazida consome; prompt de conversão, extrator e parâmetro de modelo são do mineiro.
        for proibido in ("temperature", "system_instruction", "pdfplumber", "docling --to"):
            self.assertNotIn(proibido, self.t)

    def test_readme_lista_a_reference(self):
        with open(os.path.join(RAIZ, "README.md"), encoding="utf-8") as f:
            self.assertIn("extracao-nuvem.md", f.read())


if __name__ == "__main__":
    unittest.main()
