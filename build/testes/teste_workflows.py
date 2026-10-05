# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 build/testes_monorepo/teste_workflow_testes.py
# copiado de mabritta1984/Lastro@1676115 build/testes_monorepo/teste_workflow_conversao.py
"""Incerto T3: CI (testes.yml), disparo da conversão (conversao.yml) e hook de sessão.
Conferência textual, sem PyYAML. Nunca dispara uma onda nem toca a rede."""
import os
import re
import shutil
import subprocess
import unittest
from _carga import RAIZ

TESTES = os.path.join(RAIZ, ".github", "workflows", "testes.yml")
CONVERSAO = os.path.join(RAIZ, ".github", "workflows", "conversao.yml")
HOOK = os.path.join(RAIZ, ".claude", "hooks", "session-start.sh")
SETTINGS = os.path.join(RAIZ, ".claude", "settings.json")


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _passo(yml, nome):
    """Bloco `run: |` do passo cujo `- name:` contém `nome` (linhas desindentadas)."""
    m = re.search(r"- name: [^\n]*%s[^\n]*\n(.*?)(?=\n      - |\Z)" % re.escape(nome), yml, re.S)
    corpo = m.group(1)
    run = corpo[corpo.index("run: |") + len("run: |"):]
    linhas = [l for l in run.split("\n") if l.strip()]
    recuo = min(len(l) - len(l.lstrip()) for l in linhas)
    return "\n".join(l[recuo:] for l in linhas) + "\n"


class TesteTestesYml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = _ler(TESTES)

    def test_testes_yml_roda_verificador_e_unittest(self):
        for trecho in ("build/verificar_incerto.py", "unittest discover -s build/testes",
                       "neo4j:5", "NEO4J_TESTE_URI", "pip install -r build/requisitos.txt"):
            self.assertIn(trecho, self.y)

    def test_dispara_em_push_e_pr_com_matriz_310_e_312(self):
        self.assertIn("push:", self.y)
        self.assertIn("pull_request:", self.y)
        self.assertIn('"3.10"', self.y)
        self.assertIn('"3.12"', self.y)

    def test_service_container_aponta_para_query_api(self):
        self.assertIn("NEO4J_TESTE_URI: http://localhost:7474", self.y)
        for var in ("NEO4J_TESTE_USUARIO", "NEO4J_TESTE_SENHA", "NEO4J_TESTE_DATABASE"):
            self.assertIn(var, self.y)
        self.assertIn("/db/neo4j/query/v2", self.y)
        self.assertNotIn("databases.neo4j.io", self.y)  # nunca o Aura no CI

    def test_sem_segredo_nem_resto_do_lastro(self):
        self.assertNotIn("secrets.", self.y)
        for resto in ("jazida", "verificar_release", "verificar_tudo", "Lastro —"):
            self.assertNotIn(resto, self.y)


class TesteConversaoYml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = _ler(CONVERSAO)

    def test_conversao_yml_valida_nomes_e_usa_wif(self):
        for trecho in ("workload_identity_provider", "mineiro-onda",
                       "/mnt/corpus/originais/${ORIGEM}", "default: TALEB", "Valida"):
            self.assertIn(trecho, self.y)
        for proibido in ("GOOGLE_APPLICATION_CREDENTIALS", ".json", "credentials_json", "secrets."):
            self.assertNotIn(proibido, self.y)

    def test_so_manual_com_onda_e_origem(self):
        self.assertIn("workflow_dispatch:", self.y)
        for gatilho in ("push:", "pull_request:", "schedule:"):
            self.assertNotIn(gatilho, self.y)
        self.assertRegex(self.y, r"inputs:\s*\n\s+onda:")
        self.assertRegex(self.y, r"\n\s+origem:\s*\n")

    def test_executa_o_job_no_projeto_jazida_e_espera(self):
        self.assertIn("gcloud run jobs execute mineiro-onda", self.y)
        for arg in ("--region us-central1", "--project jazida", "--wait",
                    "run,/mnt/corpus/originais/${ORIGEM},--out,/mnt/corpus/extraidos/${ONDA},--config,/app/config-cloud.yaml"):
            self.assertIn(arg, self.y)

    def test_input_nunca_interpolado_no_shell(self):
        runs = re.findall(r"run: \|\n((?:\s{10,}.*\n?)+)", self.y)
        self.assertTrue(runs)
        for bloco in runs:
            self.assertNotIn("${{", bloco)
        self.assertIn("ONDA: ${{ inputs.onda }}", self.y)
        self.assertIn("ORIGEM: ${{ inputs.origem }}", self.y)

    def test_validacao_vem_antes_da_autenticacao(self):
        self.assertLess(self.y.index("Valida"), self.y.index("google-github-actions/auth"))

    @unittest.skipUnless(shutil.which("bash"), "sem bash")
    def test_validacao_dos_nomes_pelo_bash_do_workflow(self):
        script = _passo(self.y, "Valida")

        def roda(onda, origem):
            return subprocess.run(["bash", "-euo", "pipefail", "-c", script], capture_output=True, text=True,
                                  env={"ONDA": onda, "ORIGEM": origem, "PATH": os.environ.get("PATH", "")}).returncode
        self.assertEqual(roda("2026-10-TALEB-1", "TALEB"), 0)
        self.assertEqual(roda("onda_2.b", "fonte-x"), 0)
        for onda, origem in (("a,b", "TALEB"), ("x", "TALEB,--config,/tmp/x"), ("../x", "TALEB"), ("x", "a/b"),
                             ("a..b", "TALEB"), ("", "TALEB"), ("x", ""), ("-x", "TALEB"), (".x", "TALEB"),
                             ("a b", "TALEB"), ("x", "$(id)"), ("x", "TALEB\n")):
            self.assertNotEqual(roda(onda, origem), 0, (onda, origem))


class TesteHook(unittest.TestCase):
    def test_hook_so_na_nuvem(self):
        h = _ler(HOOK)
        self.assertIn("CLAUDE_CODE_REMOTE", h)
        self.assertIn("build/requisitos.txt", h)
        self.assertIn("build/verificar_incerto.py", h)
        for resto in ("jazida", "verificar_tudo"):
            self.assertNotIn(resto, h)

    def test_hook_nao_bloqueia_e_e_executavel(self):
        self.assertIn("||", _ler(HOOK))
        self.assertTrue(os.access(HOOK, os.X_OK))

    def test_settings_liga_o_hook_de_sessao(self):
        s = _ler(SETTINGS)
        self.assertIn("SessionStart", s)
        self.assertIn(".claude/hooks/session-start.sh", s)


if __name__ == "__main__":
    unittest.main()
