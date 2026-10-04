# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_contrato_consumo.py
"""Jazida V3.3: contrato de consumo do que o mineiro grava em extraidos/<onda>/ (fixture real da onda
2026-09-PSX-1, depois do rerender). O leitor é skills/lavra/scripts/conferir_onda.py; as regras são as de
references/extracao-nuvem.md."""
import json
import os
import shutil
import tempfile
import unittest
from _carga import RAIZ, carregar

co = carregar("skills/lavra/scripts/conferir_onda.py")

FIXTURES = os.path.join(RAIZ, "build", "testes", "fixtures")
ONDA = "2026-09-PSX-1"
PASTA = os.path.join(FIXTURES, "extraidos", ONDA)
MOGHADDAM = "2018-Moghaddam-13b9e4a8-cf24-a1af-4306-2196b6b7d1e3.pdf"
GUAN = "2009-Guan-086d27f4-659c-4719-34ef-27e3e9abd50f.pdf"
BRINKROLF = "2021-Brinkrolf-27003130-0e9c-0ea3-7a35-817dd41cde88.pdf"
ASABE = "2005-ASABE-685465ae-4c50-a697-27e8-d45a6aa3439f.pdf"


class _Copia(unittest.TestCase):
    """Cópia da onda real numa pasta temporária, para montar os casos de reprovação."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jazida-onda-")
        self.pasta = os.path.join(self.tmp, ONDA)
        shutil.copytree(PASTA, self.pasta)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def relatorio(self, doc):
        with open(os.path.join(self.pasta, doc + ".report.json"), encoding="utf-8") as f:
            return json.load(f)

    def gravar(self, doc, rel):
        with open(os.path.join(self.pasta, doc + ".report.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(rel, f, ensure_ascii=False, indent=2)

    def conferir(self, doc):
        return co.conferir_documento(self.pasta, doc)


class TesteFixtureReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {d["documento"]: d for d in co.ler_onda(PASTA)}

    def test_quatro_documentos_ordenados_por_bytes_sem_o_lote(self):
        nomes = [d["documento"] for d in co.ler_onda(PASTA)]
        self.assertEqual(nomes, sorted([MOGHADDAM, GUAN, BRINKROLF, ASABE], key=lambda s: s.encode("utf-8")))

    def test_todos_aptos(self):
        for nome, d in self.docs.items():
            self.assertEqual(d["veredito"], "apto", (nome, d["motivos"]))
            self.assertEqual(d["motivos"], [])

    def test_equacao_com_katex(self):
        d = self.docs[MOGHADDAM]
        self.assertEqual(d["validador"], "katex")
        self.assertEqual(d["equacoes_detectadas"], 4)
        self.assertEqual(d["perdas"], [])

    def test_sem_equacao_aceita_validador_null(self):
        for nome in (BRINKROLF, ASABE):
            self.assertIsNone(self.docs[nome]["validador"])
            self.assertEqual(self.docs[nome]["equacoes_detectadas"], 0)

    def test_fallback_mermaid_e_perda_declarada_com_o_motivo(self):
        perdas = self.docs[BRINKROLF]["perdas"]
        self.assertEqual([(p["item"], p["rota"]) for p in perdas], [("pic_23", "mermaid"), ("pic_34", "mermaid")])
        for p in perdas:
            self.assertIn("finishReason=MAX_TOKENS", p["motivo"])
        self.assertEqual([p["rota"] for p in self.docs[GUAN]["perdas"]], ["mermaid"])

    def test_hash_dos_dois_arquivos(self):
        d = self.docs[ASABE]
        self.assertRegex(d["sha256_md"], r"^[0-9a-f]{64}$")
        self.assertRegex(d["sha256_report"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(d["sha256_md"], d["sha256_report"])


class TesteValidador(_Copia):
    def test_equacao_com_pylatexenc_reprova(self):
        rel = self.relatorio(MOGHADDAM)
        rel["summary"]["equacoes"]["validador"] = "pylatexenc"
        self.gravar(MOGHADDAM, rel)
        d = self.conferir(MOGHADDAM)
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("katex" in m for m in d["motivos"]), d["motivos"])

    def test_equacao_com_validador_null_reprova(self):
        rel = self.relatorio(MOGHADDAM)
        rel["summary"]["equacoes"]["validador"] = None
        self.gravar(MOGHADDAM, rel)
        self.assertEqual(self.conferir(MOGHADDAM)["veredito"], "reprovado")

    def test_equacao_sem_a_chave_validador_reprova(self):
        rel = self.relatorio(MOGHADDAM)
        del rel["summary"]["equacoes"]["validador"]
        self.gravar(MOGHADDAM, rel)
        self.assertEqual(self.conferir(MOGHADDAM)["veredito"], "reprovado")

    def test_sem_summary_equacoes_reprova(self):
        rel = self.relatorio(ASABE)
        del rel["summary"]["equacoes"]
        self.gravar(ASABE, rel)
        self.assertEqual(self.conferir(ASABE)["veredito"], "reprovado")

    def test_latex_invalido_no_fim_reprova(self):
        rel = self.relatorio(GUAN)
        rel["summary"]["equacoes"]["latex_invalido_final"] = 1
        self.gravar(GUAN, rel)
        d = self.conferir(GUAN)
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("latex_invalido_final" in m for m in d["motivos"]), d["motivos"])


class TestePerdaSilenciosa(_Copia):
    def test_item_nao_aprovado_sem_fallback_reprova(self):
        rel = self.relatorio(MOGHADDAM)
        rel["items"][0]["approved"] = False
        self.gravar(MOGHADDAM, rel)
        d = self.conferir(MOGHADDAM)
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("perda silenciosa" in m for m in d["motivos"]), d["motivos"])

    def test_fallback_ausente_do_md_reprova(self):
        caminho = os.path.join(self.pasta, BRINKROLF + ".md")
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
        rel = self.relatorio(BRINKROLF)
        final = [i for i in rel["items"] if i["item_id"] == "pic_23"][0]["final"]
        self.assertIn(final, texto)
        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(texto.replace(final, ""))
        d = self.conferir(BRINKROLF)
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("pic_23" in m for m in d["motivos"]), d["motivos"])

    def test_fallback_sem_a_marca_reprova(self):
        rel = self.relatorio(BRINKROLF)
        for i in rel["items"]:
            if i["item_id"] == "pic_34":
                i["final"] = "Texto qualquer."
        self.gravar(BRINKROLF, rel)
        self.assertEqual(self.conferir(BRINKROLF)["veredito"], "reprovado")

    def test_pagina_sem_texto_reprova(self):
        rel = self.relatorio(ASABE)
        rel["summary"]["parse"]["paginas_sem_texto"] = 2
        self.gravar(ASABE, rel)
        d = self.conferir(ASABE)
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("paginas_sem_texto" in m for m in d["motivos"]), d["motivos"])

    def test_pagina_falha_com_nota_e_perda_declarada_sem_nota_reprova(self):
        rel = self.relatorio(ASABE)
        rel["summary"]["parse"]["paginas_falhas"] = 1
        self.gravar(ASABE, rel)
        self.assertEqual(self.conferir(ASABE)["veredito"], "reprovado")
        with open(os.path.join(self.pasta, ASABE + ".md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n> ⚠️ [fallback] página 3 não convertida(s) pelo modelo; o erro está em "
                    "`erros` no relatório do documento.\n")
        d = self.conferir(ASABE)
        self.assertEqual(d["veredito"], "apto", d["motivos"])
        self.assertEqual([p["rota"] for p in d["perdas"]], ["parse"])


class TestePar(_Copia):
    def test_md_sem_relatorio_reprova(self):
        os.remove(os.path.join(self.pasta, ASABE + ".report.json"))
        docs = {d["documento"]: d for d in co.ler_onda(self.pasta)}
        self.assertEqual(docs[ASABE]["veredito"], "reprovado")

    def test_relatorio_sem_md_reprova(self):
        os.remove(os.path.join(self.pasta, ASABE + ".md"))
        docs = {d["documento"]: d for d in co.ler_onda(self.pasta)}
        self.assertEqual(docs[ASABE]["veredito"], "reprovado")

    def test_nome_sem_extensao_de_origem_reprova(self):
        for suf in (".md", ".report.json"):
            shutil.copy(os.path.join(self.pasta, ASABE + suf), os.path.join(self.pasta, "Relatorio" + suf))
        docs = {d["documento"]: d for d in co.ler_onda(self.pasta)}
        self.assertEqual(docs["Relatorio"]["veredito"], "reprovado")
        self.assertTrue(any("extensão de origem" in m for m in docs["Relatorio"]["motivos"]))

    def test_json_invalido_reprova(self):
        with open(os.path.join(self.pasta, ASABE + ".report.json"), "w", encoding="utf-8") as f:
            f.write("{")
        self.assertEqual(self.conferir(ASABE)["veredito"], "reprovado")

    def test_contagem_de_itens_divergente_reprova(self):
        rel = self.relatorio(ASABE)
        rel["summary"]["itens"] += 1
        self.gravar(ASABE, rel)
        self.assertEqual(self.conferir(ASABE)["veredito"], "reprovado")

    def test_lote_nao_e_documento_nem_e_lido(self):
        with open(os.path.join(self.pasta, "lote-2026-09-27.md"), "w", encoding="utf-8") as f:
            f.write("lixo que não é o resumo do lote")
        self.assertEqual(len(co.ler_onda(self.pasta)), 4)
        self.assertTrue(all(d["veredito"] == "apto" for d in co.ler_onda(self.pasta)))


if __name__ == "__main__":
    unittest.main()
