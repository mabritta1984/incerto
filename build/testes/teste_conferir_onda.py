# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_conferir_onda.py
"""Jazida V4.1: conferir_onda.py — relatório de fidelidade ao PO, manifesto da onda e o portão
(`--aprovar` copia os aptos para conferidos/<onda>/; reprovado fica em extraidos/ com o motivo)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from _carga import RAIZ, carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))   # vizinhos do
sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))   # import local
co = carregar("skills/lavra/scripts/conferir_onda.py")

SCRIPT = os.path.join(RAIZ, "skills", "lavra", "scripts", "conferir_onda.py")
FIXTURES = os.path.join(RAIZ, "build", "testes", "fixtures")
ONDA = "2026-09-PSX-1"
MOGHADDAM = "2018-Moghaddam-13b9e4a8-cf24-a1af-4306-2196b6b7d1e3.pdf"
BRINKROLF = "2021-Brinkrolf-27003130-0e9c-0ea3-7a35-817dd41cde88.pdf"
ASABE = "2005-ASABE-685465ae-4c50-a697-27e8-d45a6aa3439f.pdf"


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


class TesteResumo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = co.ler_onda(os.path.join(FIXTURES, "extraidos", ONDA))
        cls.r = co.resumir(cls.docs)

    def test_totais_somados_dos_relatorios(self):
        r = self.r
        self.assertEqual((r["documentos"], r["aptos"], r["reprovados"]), (4, 4, 0))
        self.assertEqual((r["itens"], r["fallbacks"]), (169, 3))
        self.assertEqual(r["tokens"], {"prompt": 112151, "output": 51704, "thoughts": 81929, "total": 245784})
        self.assertAlmostEqual(r["segundos"], 738.6, places=1)

    def test_fallback_por_rota(self):
        rotas = self.r["por_rota"]
        self.assertEqual(rotas["mermaid"], {"itens": 11, "fallbacks": 3, "nao_aprovados": 3})
        self.assertEqual(rotas["equation"], {"itens": 11, "fallbacks": 0, "nao_aprovados": 0})
        self.assertEqual(rotas["parse"]["fallbacks"], 0)
        self.assertEqual(list(rotas), sorted(rotas, key=lambda s: s.encode("utf-8")))

    def test_mermaid_valido_pelos_relatorios_nao_pelo_lote(self):
        self.assertEqual((self.r["mermaid_valido"], self.r["mermaid_total"]), (8, 11))

    def test_equacoes(self):
        eq = self.r["equacoes"]
        self.assertEqual(eq["equacoes_detectadas"], 11)
        self.assertEqual(eq["latex_invalido_final"], 0)
        self.assertEqual((eq["documentos_com_equacao"], eq["documentos_katex"]), (2, 2))
        self.assertEqual(eq["parseaveis_sympy"], {"parseaveis": 1, "total": 15})   # via extrair_equacoes.py (decisão 1b)

    def test_custo_nulo_e_nao_informado_nunca_zero(self):
        self.assertIsNone(self.r["custo_usd"])


class TesteRelatorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = co.ler_onda(os.path.join(FIXTURES, "extraidos", ONDA))
        cls.md = co.relatorio_md(ONDA, docs, co.resumir(docs))

    def test_secoes(self):
        for s in ("# Conferência da onda `2026-09-PSX-1`", "## Resumo", "## Por rota", "## Equações",
                  "## Perdas declaradas", "## Veredito por documento"):
            self.assertIn(s, self.md)

    def test_perdas_com_motivo_por_rota(self):
        self.assertIn("| %s | pic_23 | mermaid |" % BRINKROLF, self.md)
        self.assertIn("finishReason=MAX_TOKENS", self.md)

    def test_numeros_dos_relatorios(self):
        self.assertIn("8 de 11", self.md)
        self.assertIn("245784", self.md)
        self.assertIn("não informado", self.md)
        self.assertIn("| parseáveis pelo SymPy | 1/15 |", self.md)   # decisão 1b do PO (28/09): extrair_equacoes.py (Task 8)
        self.assertNotIn("não medido", self.md)
        self.assertNotIn("pendente", self.md)

    def test_nada_do_lote_e_nada_de_timestamp(self):
        self.assertNotIn("0.0% (0/133)", self.md)
        self.assertNotIn("Errno 2", self.md)
        self.assertNotIn("2026-09-27T", self.md)            # generated_at dos relatórios

    def test_deterministico(self):
        docs = co.ler_onda(os.path.join(FIXTURES, "extraidos", ONDA))
        self.assertEqual(co.relatorio_md(ONDA, docs, co.resumir(docs)), self.md)


class TesteNomeDaOnda(unittest.TestCase):
    def test_aceita(self):
        for n in ("2026-09-PSX-1", "PSX", "onda_2.b"):
            co.validar_nome(n)

    def test_recusa(self):
        for n in ("", "a/b", "..", "../x", "a..b", "a,b", " a", "-x", ".oculto", "a b", "a\\b"):
            with self.assertRaises(ValueError, msg=n):
                co.validar_nome(n)


class _Corpus(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="jazida-corpus-")
        shutil.copytree(os.path.join(FIXTURES, "extraidos"), os.path.join(self.raiz, "extraidos"))
        self.ext = os.path.join(self.raiz, "extraidos", ONDA)
        self.conf = os.path.join(self.raiz, "conferidos", ONDA)
        os.makedirs(os.path.join(self.ext, ASABE + ".assets"))
        with open(os.path.join(self.ext, ASABE + ".assets", "fig_1.png"), "wb") as f:
            f.write(b"\x89PNG falso")

    def tearDown(self):
        shutil.rmtree(self.raiz)

    def reprovar_moghaddam(self):
        caminho = os.path.join(self.ext, MOGHADDAM + ".report.json")
        with open(caminho, encoding="utf-8") as f:
            rel = json.load(f)
        rel["summary"]["equacoes"]["validador"] = "pylatexenc"
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rel, f, ensure_ascii=False, indent=2)

    def portao(self, recusas=None):
        return co.aprovar(self.raiz, ONDA, co.ler_onda(self.ext), recusas or {})


class TesteManifesto(_Corpus):
    def test_campos_sem_timestamp_e_deterministico(self):
        docs = co.ler_onda(self.ext)
        m = co.manifesto(self.raiz, ONDA, docs, co.resumir(docs))
        self.assertEqual((m["onda"], m["ferramenta"]), (ONDA, "mineiro"))
        d = {x["documento"]: x for x in m["documentos"]}[MOGHADDAM]
        for campo in ("veredito", "motivos", "perdas", "sha256_md", "sha256_report", "original",
                      "sha256_original", "engine", "model_versions", "validador", "equacoes_detectadas"):
            self.assertIn(campo, d)
        self.assertNotIn("_relatorio", d)
        texto = co.json_manifesto(m)
        self.assertNotIn("generated_at", texto)
        self.assertEqual(texto, co.json_manifesto(co.manifesto(self.raiz, ONDA, co.ler_onda(self.ext), co.resumir(docs))))

    def test_sha256_do_original_quando_legivel_no_mesmo_disco(self):
        orig = os.path.join(self.raiz, "originais", "PSX", ASABE)
        os.makedirs(os.path.dirname(orig))
        with open(orig, "wb") as f:
            f.write(b"%PDF-1.4 falso")
        docs = {x["documento"]: x for x in co.manifesto(self.raiz, ONDA, co.ler_onda(self.ext), {})["documentos"]}
        self.assertEqual(docs[ASABE]["sha256_original"], hashlib.sha256(b"%PDF-1.4 falso").hexdigest())
        self.assertIsNone(docs[MOGHADDAM]["sha256_original"])
        self.assertEqual(docs[ASABE]["original"], "/mnt/corpus/originais/PSX/" + ASABE)


class TestePortao(_Corpus):
    def test_aprovar_copia_os_aptos_e_nao_apaga_extraidos(self):
        self.reprovar_moghaddam()
        antes = sorted(os.listdir(self.ext))
        copiados = self.portao()
        self.assertEqual(sorted(copiados), sorted(n for n in (ASABE, BRINKROLF, "2009-Guan-086d27f4-659c-4719-34ef-27e3e9abd50f.pdf")))
        for suf in (".md", ".report.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.conf, ASABE + suf)))
            self.assertFalse(os.path.exists(os.path.join(self.conf, MOGHADDAM + suf)))
        self.assertTrue(os.path.isfile(os.path.join(self.conf, ASABE + ".assets", "fig_1.png")))
        self.assertFalse(os.path.exists(os.path.join(self.conf, "lote-2026-09-27.md")))
        self.assertEqual(sorted(os.listdir(self.ext)), sorted(antes + ["manifesto.json"]))

    def test_manifesto_nos_dois_lados_com_o_motivo_do_reprovado(self):
        self.reprovar_moghaddam()
        self.portao()
        m_ext = _ler(os.path.join(self.ext, "manifesto.json"))
        self.assertEqual(m_ext, _ler(os.path.join(self.conf, "manifesto.json")))
        d = {x["documento"]: x for x in json.loads(m_ext)["documentos"]}[MOGHADDAM]
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("katex" in m for m in d["motivos"]))

    def test_recusa_do_po(self):
        self.portao({ASABE: "tabela 2 deslocada"})
        self.assertFalse(os.path.exists(os.path.join(self.conf, ASABE + ".md")))
        d = {x["documento"]: x for x in json.loads(_ler(os.path.join(self.ext, "manifesto.json")))["documentos"]}[ASABE]
        self.assertEqual((d["veredito"], d["motivos"]), ("recusado_pelo_po", ["PO: tabela 2 deslocada"]))

    def test_recusa_de_documento_inexistente_e_erro(self):
        with self.assertRaises(ValueError):
            self.portao({"nao-existe.pdf": "x"})

    def test_idempotente(self):
        self.portao()
        self.assertEqual(len(self.portao()), 4)

    def test_conferidos_nao_se_reescreve(self):
        self.portao()
        alvo = os.path.join(self.conf, ASABE + ".md")
        with open(alvo, "a", encoding="utf-8") as f:
            f.write("edição à mão\n")
        m_antes = _ler(os.path.join(self.conf, "manifesto.json"))
        with self.assertRaises(co.Conflito) as ctx:
            self.portao({BRINKROLF: "mudou de ideia"})
        self.assertIn(ASABE + ".md", str(ctx.exception))
        self.assertIn(BRINKROLF, str(ctx.exception))            # já está em conferidos e agora ficaria de fora
        self.assertEqual(_ler(os.path.join(self.conf, "manifesto.json")), m_antes)

    def test_reprovado_que_volta_apto_entra_e_o_manifesto_e_regravado(self):
        self.reprovar_moghaddam()
        self.portao()
        shutil.copyfile(os.path.join(FIXTURES, "extraidos", ONDA, MOGHADDAM + ".report.json"),
                        os.path.join(self.ext, MOGHADDAM + ".report.json"))      # o rerender corrigiu
        self.assertEqual(len(self.portao()), 4)
        self.assertTrue(os.path.isfile(os.path.join(self.conf, MOGHADDAM + ".md")))
        d = {x["documento"]: x for x in json.loads(_ler(os.path.join(self.conf, "manifesto.json")))["documentos"]}
        self.assertEqual(d[MOGHADDAM]["veredito"], "apto")

    def test_sem_apto_nao_cria_conferidos(self):
        co.aprovar(self.raiz, ONDA, co.ler_onda(self.ext), {d: "x" for d in co.documentos(self.ext)})
        self.assertFalse(os.path.exists(self.conf))
        self.assertTrue(os.path.isfile(os.path.join(self.ext, "manifesto.json")))


class TesteLinhaDeComando(_Corpus):
    def rodar(self, *args):
        return subprocess.run([sys.executable, "-B", SCRIPT] + list(args), capture_output=True, text=True,
                              encoding="utf-8")

    def test_so_relata_sem_escrever(self):
        r = self.rodar("--raiz", self.raiz, "--onda", ONDA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# Conferência da onda", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.ext, "manifesto.json")))
        self.assertFalse(os.path.exists(self.conf))

    def test_aprovar_e_reprovado_sai_1(self):
        self.reprovar_moghaddam()
        r = self.rodar("--raiz", self.raiz, "--onda", ONDA, "--aprovar", "--recusar", ASABE + "=tabela torta")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(sorted(x for x in os.listdir(self.conf) if x.endswith(".md")),
                         sorted([BRINKROLF + ".md", "2009-Guan-086d27f4-659c-4719-34ef-27e3e9abd50f.pdf.md"]))

    def test_nome_de_onda_invalido_sai_2(self):
        r = self.rodar("--raiz", self.raiz, "--onda", "../x")
        self.assertEqual(r.returncode, 2)

    def test_onda_inexistente_sai_2(self):
        self.assertEqual(self.rodar("--raiz", self.raiz, "--onda", "nao-existe").returncode, 2)

    def test_conflito_sai_2(self):
        self.rodar("--raiz", self.raiz, "--onda", ONDA, "--aprovar")
        with open(os.path.join(self.conf, ASABE + ".md"), "a", encoding="utf-8") as f:
            f.write("x")
        r = self.rodar("--raiz", self.raiz, "--onda", ONDA, "--aprovar")
        self.assertEqual(r.returncode, 2)
        self.assertIn("conferidos", r.stderr)


if __name__ == "__main__":
    unittest.main()
