# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_nucleo.py
"""Incerto: o núcleo contra um servidor HTTP falso (Query API e sonda com respostas gravadas)
e, com @precisa_neo4j, contra um Neo4j 5 de verdade — no CI, o service container; nunca o Aura."""
import base64
import json
import os
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from _banco import banco_de_teste, cred_de_teste, limpar_banco_de_teste, precisa_neo4j
from _carga import carregar

NUC = carregar("skills/lavra/scripts/nucleo.py")


class ServidorFalso:
    """Query API v2 falsa em 127.0.0.1:<porta livre>. `respostas`: lista de (status, corpo) consumida por
    POST; o último item se repete. GET / responde 200 (camada 2 da sonda); GET /api/tags imita o Ollama."""

    def __init__(self, respostas=None, por_statement=None):
        self.pedidos, self.respostas, self.por_statement = [], list(respostas or []), por_statement or {}
        dono = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responde(self, status, corpo):
                dados = json.dumps(corpo).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                if self.path == "/api/tags":
                    return self._responde(200, {"models": [{"name": "embeddinggemma:latest"}]})
                return self._responde(200, {"neo4j_version": "5.27-falso"})

            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                dono.pedidos.append({"path": self.path, "auth": self.headers.get("Authorization"), "corpo": corpo})
                for trecho, resposta in dono.por_statement.items():
                    if trecho in corpo["statement"]:
                        return self._responde(*resposta)
                resposta = dono.respostas.pop(0) if len(dono.respostas) > 1 else dono.respostas[0]
                return self._responde(*resposta)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.porta = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def fechar(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def cred(self, **extra):
        return dict({"NEO4J_URI": "bolt://127.0.0.1:1", "NEO4J_QUERY_URL": "http://127.0.0.1:%d" % self.porta,
                     "NEO4J_USERNAME": "neo4j", "NEO4J_PASSWORD": "segredo"}, **extra)


def _valores(*linhas):
    return 202, {"data": {"fields": ["x"], "values": [list(l) for l in linhas]}, "bookmarks": ["b"]}


class ComServidor(unittest.TestCase):
    def servidor(self, *a, **k):
        s = ServidorFalso(*a, **k)
        self.addCleanup(s.fechar)
        return s


class TesteQueryApi(ComServidor):
    def test_post_na_rota_v2_com_basic_e_parametros(self):
        s = self.servidor([_valores([1, "a"])])
        linhas = NUC.query_api(s.cred(), "7a5fa0fc", "MATCH (n) WHERE n.x = $x RETURN 1, 'a'", {"x": 2})
        self.assertEqual(linhas, [[1, "a"]])
        p = s.pedidos[0]
        self.assertEqual(p["path"], "/db/7a5fa0fc/query/v2")
        self.assertEqual(p["auth"], "Basic " + base64.b64encode(b"neo4j:segredo").decode())
        self.assertEqual(p["corpo"], {"statement": "MATCH (n) WHERE n.x = $x RETURN 1, 'a'", "parameters": {"x": 2}})

    def test_erro_no_payload_vira_runtimeerror_com_codigo(self):
        s = self.servidor([(202, {"errors": [{"code": "Neo.ClientError.Statement.SyntaxError", "message": "ruim"}]})])
        with self.assertRaises(RuntimeError) as ctx:
            NUC.query_api(s.cred(), "neo4j", "RETURN")
        self.assertIn("Neo.ClientError.Statement.SyntaxError: ruim", str(ctx.exception))

    def test_http_400_traz_o_corpo_do_neo4j_na_mensagem(self):
        s = self.servidor([(400, {"errors": [{"code": "Neo.ClientError.Request.Invalid", "message": "json torto"}]})])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            NUC.query_api(s.cred(), "neo4j", "RETURN 1")
        self.assertIn("Neo.ClientError.Request.Invalid: json torto", str(ctx.exception))

    def test_alvo_local_nao_passa_pelo_proxy(self):
        s = self.servidor([_valores([1])])
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9"}):
            self.assertEqual(NUC.query_api(s.cred(), "neo4j", "RETURN 1"), [[1]])

    def test_localhost_vira_127(self):
        self.assertEqual(NUC.base_query({"NEO4J_QUERY_URL": "http://localhost:7474/"}), "http://127.0.0.1:7474")


class TesteRetentativa(ComServidor):
    def setUp(self):
        p = mock.patch.object(NUC.time, "sleep"); self.sono = p.start(); self.addCleanup(p.stop)

    def test_503_repete_e_depois_responde(self):
        s = self.servidor([(503, {"errors": [{"code": "Neo.TransientError.General.DatabaseUnavailable", "message": "x"}]}),
                           _valores([7])])
        self.assertEqual(NUC.query_com_retentativa(s.cred(), "neo4j", "RETURN 7", {}), [[7]])
        self.assertEqual(len(s.pedidos), 2); self.sono.assert_called_once_with(3)

    def test_401_nao_repete(self):
        s = self.servidor([(401, {"errors": [{"code": "Neo.ClientError.Security.Unauthorized", "message": "não"}]})])
        with self.assertRaises(urllib.error.HTTPError):
            NUC.query_com_retentativa(s.cred(), "neo4j", "RETURN 1", {})
        self.assertEqual(len(s.pedidos), 1); self.sono.assert_not_called()


class TesteDatabase(ComServidor):
    def test_declarado_vence_sem_consultar(self):
        s = self.servidor([_valores(["outro"])])
        self.assertEqual(NUC.database(s.cred(NEO4J_DATABASE="7a5fa0fc"), verboso=False), "7a5fa0fc")
        self.assertEqual(s.pedidos, [])

    def test_sem_declarado_descobre_o_home_no_system(self):
        s = self.servidor([_valores(["meu_home"])])
        self.assertEqual(NUC.database(s.cred(), verboso=False), "meu_home")
        self.assertEqual(s.pedidos[0]["path"], "/db/system/query/v2")
        self.assertIn("SHOW DATABASES", s.pedidos[0]["corpo"]["statement"])


class TesteSondaGravada(ComServidor):
    """Respostas gravadas no formato do que a sonda achou no Aura em 27/09 (jazida, 27/09):
    database declarado = id da instância, `ai.text.embedBatch` só sob CYPHER 25."""

    def test_query_api_pronta_com_database_declarado_e_procedure_no_dialeto(self):
        s = self.servidor([_valores()], por_statement={
            "CYPHER 25 SHOW PROCEDURES": _valores(["ai.text.embedBatch"]),
            "SHOW PROCEDURES": _valores()})
        r = NUC.sonda(s.cred(NEO4J_DATABASE="7a5fa0fc", OLLAMA_URL="http://127.0.0.1:%d" % s.porta), verboso=False)
        self.assertEqual(r["camada 2 (origem)"], "HTTP 200")
        self.assertEqual(r["database"], "7a5fa0fc")
        self.assertEqual(r["database_origem"], "declarado (NEO4J_DATABASE)")
        self.assertEqual(r["procedure_embedding"], "ai.text.embedBatch")
        self.assertEqual(r["dialeto"], "CYPHER 25")
        self.assertTrue(r["veredito"].startswith("Query API pronta — database '7a5fa0fc'"), r["veredito"])

    def test_bolt_fechado_nao_derruba_a_sonda(self):
        s = self.servidor([_valores()])
        r = NUC.sonda(s.cred(NEO4J_DATABASE="neo4j", OLLAMA_URL="http://127.0.0.1:9"), verboso=False)
        self.assertIn("camada 3 (bolt :1)", r)
        self.assertTrue(r["veredito"].startswith("Query API pronta"))
        self.assertEqual(r["n10s"], "plugin não carregado (0 procedures) — rota rdflib")

    def test_origem_muda_para_o_veredito_de_instancia_parada(self):
        s = self.servidor([_valores()]); porta = s.porta; s.fechar()
        r = NUC.sonda({"NEO4J_URI": "bolt://127.0.0.1:1", "NEO4J_QUERY_URL": "http://127.0.0.1:%d" % porta,
                       "NEO4J_USERNAME": "x", "NEO4J_PASSWORD": "x"}, verboso=False)
        self.assertNotIn("Query API pronta", r["veredito"])


class TesteTravaDoAura(unittest.TestCase):
    def test_aura_nunca_e_banco_de_teste(self):
        import _banco
        with mock.patch.dict(os.environ, {"NEO4J_TESTE_URI": "https://7a5fa0fc.databases.neo4j.io"}):
            self.assertEqual(_banco.cred_de_teste()["NEO4J_QUERY_URL"], "")
        with mock.patch.dict(os.environ, {"NEO4J_TESTE_URI": "http://localhost:7474"}):
            self.assertEqual(_banco.cred_de_teste()["NEO4J_QUERY_URL"], "http://localhost:7474")


class TesteBancoDeTeste(ComServidor):
    def test_limpa_so_a_particao_do_incerto_e_devolve_cred_e_db(self):
        s = self.servidor([_valores()])
        env = {"NEO4J_TESTE_URI": "http://127.0.0.1:%d" % s.porta, "NEO4J_TESTE_DATABASE": "meudb"}
        with mock.patch.dict(os.environ, env):
            cred, db = banco_de_teste()
            self.assertEqual(db, "meudb")
            self.assertEqual(cred["NEO4J_QUERY_URL"], env["NEO4J_TESTE_URI"])
            limpar_banco_de_teste(cred, db)
        self.assertEqual(len(s.pedidos), 2)
        for p in s.pedidos:
            self.assertEqual(p["path"], "/db/meudb/query/v2")
            self.assertIn("DETACH DELETE", p["corpo"]["statement"])
            self.assertEqual(p["corpo"]["parameters"], {"corpus": "incerto-teste"})


@precisa_neo4j
class TesteNeo4jDeVerdade(unittest.TestCase):
    """Só com NEO4J_TESTE_URI (no CI, o service container neo4j:5). Grava e apaga só nós `corpus: 'incerto-teste'`."""

    def setUp(self):
        self.cred, self.db = banco_de_teste()
        self.addCleanup(limpar_banco_de_teste, self.cred, self.db)

    def test_home_descoberto_sem_declarar(self):
        cred = dict(self.cred); cred.pop("NEO4J_DATABASE", None)
        self.assertEqual(NUC.database(cred, verboso=False), "neo4j")

    def test_ida_e_volta_com_parametros_e_chave_nfc(self):
        nfd = "evapotranspiração"
        NUC.query_com_retentativa(self.cred, self.db, "MERGE (n {corpus:'incerto-teste', chave:$c}) SET n.v = $v, n.t = $t",
                                  {"c": NUC.chave(nfd), "v": [0.0023, 17.8], "t": "três"})
        linhas = NUC.query_api(self.cred, self.db, "MATCH (n {corpus:'incerto-teste'}) RETURN n.chave, n.v, n.t")
        self.assertEqual(linhas, [["evapotranspiração", [0.0023, 17.8], "três"]])

    def test_erro_de_sintaxe_sobe_sem_retentativa(self):
        with mock.patch.object(NUC.time, "sleep") as sono:
            with self.assertRaises((RuntimeError, urllib.error.HTTPError)):
                NUC.query_com_retentativa(self.cred, self.db, "MATCH (n RETURN n", {})
        sono.assert_not_called()

    def test_sonda_contra_o_container(self):
        r = NUC.sonda(dict(self.cred, OLLAMA_URL="http://127.0.0.1:9"), verboso=False)
        self.assertTrue(r["veredito"].startswith("Query API pronta — database '%s'" % self.db), r)


if __name__ == "__main__":
    unittest.main()
