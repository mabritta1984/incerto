# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_verificar_jazida.py
"""Incerto T2: verificar_incerto.py — cada prova contra uma árvore temporária que a reprova."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from _carga import carregar, RAIZ

VI = carregar("build/verificar_incerto.py")
AGULHA = "BEGIN " + "PRIVATE KEY"      # nunca o literal: o próprio grep acharia este arquivo


class Arvore(unittest.TestCase):
    """Repositório falso e mínimo, em diretório temporário removido ao fim (nada vaza para o repositório)."""

    def setUp(self):
        self.raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.escreve(".claude-plugin/plugin.json", json.dumps({"name": "incerto", "version": "0.1.0-dev"}))
        self.escreve(".claude-plugin/marketplace.json", json.dumps({"plugins": [{"name": "incerto", "version": "0.1.0-dev"}]}))
        self.escreve("README.md", "**Versão:** `0.1.0-dev`\n")
        self.escreve("regras-do-incerto.md", "# regras-do-incerto — fonte única (v0.1.0-dev)\n")
        self.escreve("skills/taleb/scripts/nucleo.py", "import json\n")

    def escreve(self, rel, texto):
        caminho = os.path.join(self.raiz, *rel.split("/"))
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)


class TesteArvoreTemporaria(Arvore):
    def test_arvore_minima_passa_nas_cinco_provas_locais(self):
        for fn in (VI.prova_versao, VI.prova_sintaxe, VI.prova_import_cruzado, VI.prova_dependencias, VI.prova_segredos):
            ok, detalhe = fn(self.raiz)
            self.assertTrue(ok, "%s: %s" % (fn.__name__, detalhe))

    def test_reprova_import_no_topo_de_modulo(self):
        self.escreve("skills/taleb/scripts/x.py", "import sympy\n")
        ok, detalhe = VI.prova_dependencias(self.raiz)
        self.assertFalse(ok); self.assertIn("x.py", detalhe); self.assertIn("sympy", detalhe)

    def test_reprova_import_no_topo_mesmo_em_arquivo_permitido(self):
        self.escreve("skills/lavra/scripts/fiscal.py", "import sympy\n")
        ok, detalhe = VI.prova_dependencias(self.raiz)
        self.assertFalse(ok); self.assertIn("topo", detalhe)

    def test_import_dentro_de_funcao_em_arquivo_permitido_passa(self):
        self.escreve("skills/lavra/scripts/extrair_equacoes.py", "def f():\n    import sympy, mpmath\n    from antlr4 import x\n")
        ok, detalhe = VI.prova_dependencias(self.raiz)
        self.assertTrue(ok, detalhe)

    def test_dependencia_nao_declarada_reprova(self):
        self.escreve("skills/lavra/scripts/fiscal.py", "def f():\n    import numpy\n")
        ok, detalhe = VI.prova_dependencias(self.raiz)
        self.assertFalse(ok); self.assertIn("numpy", detalhe)

    def test_reprova_import_de_jazida(self):
        self.escreve("skills/taleb/scripts/x.py", "from jazida import x\n")
        ok, detalhe = VI.prova_import_cruzado(self.raiz)
        self.assertFalse(ok); self.assertIn("jazida", detalhe)

    def test_carregador_para_fora_da_arvore_reprova(self):
        self.escreve("skills/taleb/scripts/x.py",
                     "import importlib.util, os\n"
                     "s = importlib.util.spec_from_file_location('m', os.path.join('..', 'jazida', 'a.py'))\n")
        ok, detalhe = VI.prova_import_cruzado(self.raiz)
        self.assertFalse(ok); self.assertIn("spec_from_file_location", detalhe)

    def test_sys_path_reprova(self):
        self.escreve("skills/taleb/scripts/x.py", "import sys\nsys.path.insert(0, '..')\n")
        self.assertFalse(VI.prova_import_cruzado(self.raiz)[0])

    def test_reprova_chave_privada(self):
        self.escreve("skills/taleb/cred.json", '{"k": "-----%s-----"}' % AGULHA)
        ok, detalhe = VI.prova_segredos(self.raiz)
        self.assertFalse(ok); self.assertIn("cred.json", detalhe)

    def test_erro_de_sintaxe_reprova(self):
        self.escreve("skills/taleb/scripts/x.py", "def (:\n")
        self.assertFalse(VI.prova_sintaxe(self.raiz)[0])

    def test_versao_aceita_dev_e_rejeita_divergencia_ou_formato(self):
        self.assertTrue(VI.prova_versao(self.raiz)[0])
        self.escreve(".claude-plugin/marketplace.json", json.dumps({"plugins": [{"name": "incerto", "version": "0.1.0"}]}))
        ok, detalhe = VI.prova_versao(self.raiz)
        self.assertFalse(ok); self.assertIn("marketplace", detalhe)
        self.escreve(".claude-plugin/plugin.json", json.dumps({"name": "incerto", "version": "0.1"}))
        self.assertFalse(VI.prova_versao(self.raiz)[0])


class TesteNoRepositorioReal(unittest.TestCase):
    def test_aprova_arvore_atual(self):
        r = subprocess.run([sys.executable, "-B", os.path.join(RAIZ, "build", "verificar_incerto.py"), "--raiz", RAIZ],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("INCERTO APROVADO", r.stdout)

    def test_requisitos_so_os_tres_pinos(self):
        with open(os.path.join(RAIZ, "build", "requisitos.txt"), encoding="utf-8") as f:
            linhas = [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]
        self.assertEqual(sorted(linhas), sorted(["sympy==1.14.0", "mpmath==1.3.0", "antlr4-python3-runtime==4.11.1"]))


if __name__ == "__main__":
    unittest.main()
