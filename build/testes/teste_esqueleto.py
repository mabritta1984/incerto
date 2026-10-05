# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_esqueleto.py
"""Incerto T1: manifesto, marketplace, regras de dono único e injetor em sincronia."""
import glob
import json
import os
import subprocess
import sys
import unittest
from _carga import RAIZ


def _ler(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


def _json(*partes):
    return json.loads(_ler(*partes))


class TesteManifesto(unittest.TestCase):
    def test_plugin_json_na_versao_0_1_0(self):
        p = _json(RAIZ, ".claude-plugin", "plugin.json")
        self.assertEqual(p["name"], "incerto")
        self.assertEqual(p["version"], "0.1.0")
        self.assertIn("Taleb", p["description"])

    def test_marketplace_tem_uma_entrada(self):
        mk = _json(RAIZ, ".claude-plugin", "marketplace.json")
        self.assertEqual(mk["name"], "incerto")
        self.assertEqual([x["name"] for x in mk["plugins"]], ["incerto"])
        self.assertEqual(mk["plugins"][0]["source"], "./")
        self.assertEqual(mk["plugins"][0]["version"], "0.1.0")


class TesteRegras(unittest.TestCase):
    def test_regras_do_incerto_e_dona_do_bloco(self):
        texto = _ler(RAIZ, "regras-do-incerto.md")
        self.assertIn("<!-- bloco:regras-do-incerto:inicio (dono deste bloco", texto)
        for regra in ("Escritor único", "Nada sem fonte", "Equação é nó", "Fiscal de duas vias",
                      "Wolfram", "Sem import cruzado", "Nunca recomendação", "[corpus]"):
            self.assertIn(regra, texto)

    def test_regra_da_perda_e_a_do_gate(self):
        # M1: a perda declarada vira :Equacao em staging com forma `perda` (aprovar_onda, grafo-incerto.md);
        # "nunca nó" contradizia o modelo
        texto = _ler(RAIZ, "regras-do-incerto.md")
        regra = texto[texto.index("**Equação é nó"):].split("\n\n", 1)[0]
        self.assertIn("perda declarada fica em staging com forma `perda`, nunca aprovada", " ".join(regra.split()))
        self.assertNotIn("nunca nó", regra)

    def test_readme_consome_as_regras(self):
        self.assertIn("<!-- bloco:regras-do-incerto:inicio (gerado de regras-do-incerto.md",
                      _ler(RAIZ, "README.md"))

    def test_injetor_em_sincronia(self):
        r = subprocess.run([sys.executable, "-B", os.path.join(RAIZ, "build", "injetar_regras.py"), "--check",
                            "--raiz", RAIZ, "--bloco-obrigatorio", "regras-do-incerto"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_nenhum_arquivo_cita_jazida_como_codigo(self):
        # proveniência em comentário é permitida; import/caminho de execução não.
        # (?m) ancora em linha: só linhas que COMEÇAM com import/from contam, então este
        # próprio arquivo e o injetar_regras.py não casam.
        for py in glob.glob(os.path.join(RAIZ, "**", "*.py"), recursive=True):
            self.assertNotRegex(_ler(py), r"(?m)^\s*(from|import)\s+(jazida|plugin|mineiro)\b", py)


if __name__ == "__main__":
    unittest.main()
