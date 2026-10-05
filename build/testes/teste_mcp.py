# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 build/testes/teste_mcp.py (adaptado)
"""Incerto: mcp/consulta_incerto.py — servidor `incerto-consulta`, só o corpus aprovado.

Locais (sem rede): protocolo por subprocesso (initialize, tools/list com exatamente as quatro ferramentas),
ida e volta de tools/call com banco falso, degradação lexical sem Vertex, e a guarda estática de que todo
nó e toda aresta do Cypher filtram `corpus` e `status = 'aprovado'`. Com banco real (`@precisa_neo4j`, CI,
partição `incerto-teste`): staging nunca sai, nem nó nem aresta entre nós aprovados, nem outro corpus."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import unittest
from unittest import mock
from _banco import PARTICAO, banco_de_teste, limpar_banco_de_teste, precisa_neo4j
from _carga import RAIZ, carregar

MCP = carregar("mcp/consulta_incerto.py")
CAMINHO_MCP = os.path.join(RAIZ, "mcp", "consulta_incerto.py")
QUATRO = {"buscar_equacao", "ler_equacao", "ler_conceito", "situacao_camada"}


def fonte(documento, topico):
    return json.dumps({"documento": documento, "topico": topico}, sort_keys=True, ensure_ascii=False)


class BancoFalso:
    """`consultar(statement, parametros)` falso: responde por qual constante do módulo chegou e guarda tudo."""
    def __init__(self, respostas=None):
        self.respostas = respostas or {}
        self.chamadas = []

    def __call__(self, stmt, par=None):
        self.chamadas.append((stmt, par or {}))
        for chave, cypher in MCP.CYPHER.items():
            if stmt == cypher:
                r = self.respostas.get(chave, [])
                if isinstance(r, Exception):
                    raise r
                return r(par) if callable(r) else r
        raise AssertionError("statement fora de MCP.CYPHER: %r" % stmt[:80])

    def usadas(self):
        return [k for s, _ in self.chamadas for k, c in MCP.CYPHER.items() if s == c]


class ComBancoFalso(unittest.TestCase):
    def usar(self, banco):
        MCP.CONTEXTO = ({"NEO4J_USERNAME": "x"}, "neo4j", banco)
        self.addCleanup(setattr, MCP, "CONTEXTO", None)
        return banco


def _rpc(*mensagens):
    return "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mensagens)


class TesteProtocolo(unittest.TestCase):
    def test_initialize_e_tools_list_tem_as_quatro(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("NEO4J_", "INCERTO_", "VERTEX_"))}
        r = subprocess.run([sys.executable, "-B", CAMINHO_MCP],
                           input=_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                       "params": {"protocolVersion": "2025-06-18"}},
                                      {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                      {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                                      {"jsonrpc": "2.0", "id": 3, "method": "ping"}),
                           capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        respostas = {m["id"]: m for m in map(json.loads, r.stdout.splitlines())}
        self.assertEqual(sorted(respostas), [1, 2, 3])          # notificação não tem resposta
        info = respostas[1]["result"]
        self.assertEqual(info["serverInfo"]["name"], "incerto-consulta")
        self.assertEqual(info["protocolVersion"], "2025-06-18")
        self.assertIn("tools", info["capabilities"])
        ferramentas = respostas[2]["result"]["tools"]
        self.assertEqual(len(ferramentas), 4)
        self.assertEqual({t["name"] for t in ferramentas}, QUATRO)
        for t in ferramentas:
            self.assertTrue(t["annotations"]["readOnlyHint"], t["name"])
        self.assertEqual(respostas[3]["result"], {})

    def test_versao_do_servidor_e_a_do_plugin(self):
        with io.open(os.path.join(RAIZ, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            self.assertEqual(MCP.versao(), json.load(f)["version"])

    def test_tools_call_ida_e_volta_com_banco_falso(self):
        banco = BancoFalso({"equacao": [["x = y", "Equality(Symbol('x'), Symbol('y'))", "algebrica", None, [],
                                         fonte("Doc.pdf.md", "T1"), []]]})
        MCP.CONTEXTO = ({}, "neo4j", banco)
        self.addCleanup(setattr, MCP, "CONTEXTO", None)
        saida = io.StringIO()
        entrada = io.StringIO(_rpc(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
             "params": {"name": "ler_equacao", "arguments": {"nome": "Doc.pdf.md#1"}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "apagar_tudo", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 9, "method": "metodo/inexistente"}))
        with mock.patch.object(sys, "stdin", entrada), contextlib.redirect_stdout(saida):
            MCP.main()
        respostas = {m["id"]: m for m in map(json.loads, saida.getvalue().splitlines())}
        r7 = respostas[7]["result"]
        self.assertFalse(r7["isError"])
        corpo = json.loads(r7["content"][0]["text"])
        self.assertEqual(corpo["nome"], "Doc.pdf.md#1")
        self.assertEqual(corpo["latex"], "x = y")
        self.assertEqual(corpo["fonte"], {"documento": "Doc.pdf.md", "topico": "T1"})
        self.assertEqual(banco.chamadas[0][1]["corpus"], "incerto")
        self.assertEqual(respostas[8]["error"]["code"], -32602)
        self.assertEqual(respostas[9]["error"]["code"], -32601)

    def test_erro_da_ferramenta_vira_isError_com_proximo_passo(self):
        MCP.CONTEXTO = ({}, "neo4j", BancoFalso({"equacao": OSError("Connection refused")}))
        self.addCleanup(setattr, MCP, "CONTEXTO", None)
        saida = io.StringIO()
        entrada = io.StringIO(_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                    "params": {"name": "ler_equacao", "arguments": {"nome": "a"}}},
                                   {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                    "params": {"name": "ler_equacao", "arguments": {}}}))
        with mock.patch.object(sys, "stdin", entrada), contextlib.redirect_stdout(saida):
            MCP.main()
        respostas = {m["id"]: m for m in map(json.loads, saida.getvalue().splitlines())}
        self.assertTrue(respostas[1]["result"]["isError"])
        self.assertIn("Connection refused", respostas[1]["result"]["content"][0]["text"])
        self.assertIn("próximo passo", respostas[1]["result"]["content"][0]["text"])
        self.assertTrue(respostas[2]["result"]["isError"])
        self.assertIn("nome obrigatório", respostas[2]["result"]["content"][0]["text"])


class TesteMcpJson(unittest.TestCase):
    def test_mcp_json_usa_plugin_root(self):
        with io.open(os.path.join(RAIZ, ".mcp.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"mcpServers": {"incerto-consulta": {
                "command": "${INCERTO_PYTHON:-python}",
                "args": ["${CLAUDE_PLUGIN_ROOT}/mcp/consulta_incerto.py"]}}})

    def test_cabecalho_de_copia(self):
        with io.open(CAMINHO_MCP, encoding="utf-8") as f:
            self.assertIn("# copiado de mabritta1984/Lastro@1676115 plugin/mcp/busca_semantica.py (adaptado)",
                          f.read(400))


# Padrões de nó `(x:Rotulo {…})` e de aresta `[r:TIPO {…}]` de todo Cypher do módulo.
RE_NO = re.compile(r"\((\w*):(\w+)\s*(\{[^}]*\})?\)")
RE_ARESTA = re.compile(r"\[(\w*):(\w+)\s*(\{[^}]*\})?\]")


class TesteCypherFiltrado(unittest.TestCase):
    """Guarda estática: o pior defeito deste servidor é devolver staging ou outro corpus."""

    def test_todo_cypher_de_leitura_filtra_o_corpus(self):
        for chave, cypher in MCP.CYPHER.items():
            if chave == "indices":
                continue
            self.assertIn("$corpus", cypher, chave)

    def test_todo_no_e_toda_aresta_casados_exigem_corpus_e_aprovado(self):
        vistos = 0
        for chave, cypher in MCP.CYPHER.items():
            for _var, rotulo, props in RE_NO.findall(cypher) + RE_ARESTA.findall(cypher):
                vistos += 1
                self.assertIn("corpus: $corpus", props, "%s: %s sem corpus" % (chave, rotulo))
                if rotulo != "Trecho":       # camada de evidência: sem status (grafo-incerto.md)
                    self.assertIn("status: 'aprovado'", props, "%s: %s sem status aprovado" % (chave, rotulo))
        self.assertGreaterEqual(vistos, 15)

    def test_arestas_percorridas_sao_as_do_modelo(self):
        tipos = {t for c in MCP.CYPHER.values() for _v, t, _p in RE_ARESTA.findall(c)}
        self.assertEqual(tipos, {"USA", "VALIDA_SOB", "DERIVA_DE", "SUSTENTA", "EXPRESSA"})

    def test_busca_nos_indices_filtra_corpus_e_nao_devolve_texto(self):
        for chave in ("busca_lexical", "busca_vetorial"):
            c = MCP.CYPHER[chave]
            self.assertIn("t.corpus = $corpus", c)
            self.assertNotIn("texto", c.split("RETURN", 1)[1])
        self.assertIn("'trecho_texto_incerto'", MCP.CYPHER["busca_lexical"])
        self.assertIn("'trecho_embedding_incerto'", MCP.CYPHER["busca_vetorial"])

    def test_nenhum_cypher_escreve(self):
        for chave, cypher in MCP.CYPHER.items():
            self.assertIsNone(re.search(r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DETACH)\b", cypher), chave)

    def test_corpus_padrao_e_incerto_e_o_ambiente_so_troca_a_particao(self):
        with mock.patch.dict(os.environ, {"INCERTO_CORPUS": ""}):
            self.assertEqual(MCP.corpus(), "incerto")
        with mock.patch.dict(os.environ, {"INCERTO_CORPUS": PARTICAO}):
            self.assertEqual(MCP.corpus(), PARTICAO)


class TesteBuscarEquacao(ComBancoFalso):
    def _banco(self):
        return self.usar(BancoFalso({
            "busca_vetorial": [["A.pdf.md", "Kappa"], ["A.pdf.md", "Kappa"], ["B.pdf.md", "Hill"]],
            "busca_lexical": [["B.pdf.md", "Hill"], ["C.pdf.md", "Kelly"]],
            "equacoes_das_fontes": [[fonte("B.pdf.md", "Hill"), "B.pdf.md#2"],
                                    [fonte("A.pdf.md", "Kappa"), "A.pdf.md#1"]]}))

    def test_buscar_equacao_devolve_sem_texto(self):
        banco = self._banco()
        with mock.patch.object(MCP.NUC, "embed_gemini", return_value=([[0.5] * 4], 3)):
            r = MCP.tool_buscar_equacao({"pergunta": "o que é kappa?"})
        self.assertEqual(r["modo"], "hibrido")
        self.assertEqual(r["corpus"], "incerto")
        self.assertEqual(r["resultados"][0], {"documento": "B.pdf.md", "topico": "Hill", "equacao": ["B.pdf.md#2"]})
        self.assertEqual([(x["documento"], x["topico"]) for x in r["resultados"]],
                         [("B.pdf.md", "Hill"), ("A.pdf.md", "Kappa"), ("C.pdf.md", "Kelly")])
        self.assertEqual(r["resultados"][2]["equacao"], [])
        for x in r["resultados"]:
            self.assertEqual(set(x), {"documento", "topico", "equacao"})
        self.assertNotIn("texto", json.dumps(r, ensure_ascii=False).replace("sem texto", ""))
        self.assertNotIn("score", json.dumps(r))
        self.assertEqual(banco.usadas(), ["busca_vetorial", "busca_lexical", "equacoes_das_fontes"])
        par_eq = banco.chamadas[-1][1]
        self.assertEqual(par_eq["corpus"], "incerto")
        self.assertIn(fonte("C.pdf.md", "Kelly"), par_eq["fontes"])

    def test_k_corta_e_k_invalido_avisa(self):
        self._banco()
        with mock.patch.object(MCP.NUC, "embed_gemini", return_value=([[0.5] * 4], 3)):
            self.assertEqual(len(MCP.tool_buscar_equacao({"pergunta": "kappa", "k": 1})["resultados"]), 1)
            r = MCP.tool_buscar_equacao({"pergunta": "kappa", "k": 99})
        self.assertIn("aparado", r["aviso"])

    def test_sem_vertex_degrada_para_lexical_e_diz(self):
        banco = self._banco()
        with mock.patch.object(MCP.NUC, "embed_gemini",
                               side_effect=SystemExit("rota Vertex: INCERTO_GCP_PROJETO ausente")):
            r = MCP.tool_buscar_equacao({"pergunta": "kappa"})
        self.assertEqual(r["modo"], "lexical")
        self.assertIn("INCERTO_GCP_PROJETO", r["aviso"])
        self.assertEqual(banco.usadas(), ["busca_lexical", "equacoes_das_fontes"])
        self.assertEqual([x["documento"] for x in r["resultados"]], ["B.pdf.md", "C.pdf.md"])

    def test_indice_vetorial_que_falha_degrada_para_lexical(self):
        banco = self._banco()
        banco.respostas["busca_vetorial"] = RuntimeError("There is no such vector schema index")
        with mock.patch.object(MCP.NUC, "embed_gemini", return_value=([[0.5] * 4], 3)):
            r = MCP.tool_buscar_equacao({"pergunta": "kappa"})
        self.assertEqual(r["modo"], "lexical")
        self.assertIn("vector schema index", r["aviso"])

    def test_pergunta_e_escapada_para_o_lucene(self):
        banco = self._banco()
        with mock.patch.object(MCP.NUC, "embed_gemini", side_effect=SystemExit("sem")):
            MCP.tool_buscar_equacao({"pergunta": "E[X] (cauda): x^2?"})
        self.assertEqual(banco.chamadas[0][1]["q"], r"E\[X\] \(cauda\)\: x\^2\?")

    def test_pergunta_obrigatoria(self):
        self._banco()
        with self.assertRaisesRegex(RuntimeError, "pergunta obrigatória"):
            MCP.tool_buscar_equacao({"pergunta": "  "})


class TesteLeituras(ComBancoFalso):
    def test_ler_equacao_monta_campos(self):
        banco = self.usar(BancoFalso({
            "equacao": [["\\kappa", "Symbol('kappa')", "algebrica", json.dumps({"media": "0"}), ["n > 1"],
                         fonte("A.pdf.md", "Kappa"), ["P3"]]],
            "equacao_variaveis": [["n", "n", "entrada", ["n"]]],
            "equacao_valida_sob": [["n > 1", "n", fonte("A.pdf.md", "Kappa"), ["P3"]]],
            "equacao_deriva_de": [["A.pdf.md#0", 1, "kappa", json.dumps({"x": "y"}), ["sympy@1.14.0"],
                                   fonte("A.pdf.md", "Kappa"), ["P4"]]]}))
        r = MCP.tool_ler_equacao({"nome": "A.pdf.md#1"})
        self.assertEqual(r["srepr"], "Symbol('kappa')")
        self.assertEqual(r["momento_fechado"], {"media": "0"})
        self.assertEqual(r["variaveis"], [{"nome": "n", "simbolo": "n", "papel": "entrada", "simbolos": ["n"]}])
        self.assertEqual(r["valida_sob"], [{"condicao": "n > 1", "variavel": "n", "aceites_po": ["P3"],
                                            "fonte": {"documento": "A.pdf.md", "topico": "Kappa"}}])
        # I3: a via aceita pelo PO não é verificação — vem em `aceites_po`, ao lado de `verificado_por`
        self.assertEqual(r["deriva_de"][0]["verificado_por"], ["sympy@1.14.0"])
        self.assertEqual(r["deriva_de"][0]["aceites_po"], ["P4"])
        self.assertEqual(r["aceites_po"], ["P3"])
        self.assertEqual(r["deriva_de"][0]["substituicao"], {"x": "y"})
        self.assertEqual(r["status"], "aprovado")
        self.assertTrue(all(p["corpus"] == "incerto" and p["nome"] == "A.pdf.md#1" for _s, p in banco.chamadas))

    def test_nao_encontrada_tem_a_mesma_mensagem_nas_duas(self):
        banco = self.usar(BancoFalso())
        self.assertEqual(MCP.tool_ler_equacao({"nome": "X#1"}), {"erro": "não encontrada no corpus aprovado"})
        self.assertEqual(MCP.tool_ler_conceito({"nome": "antifragilidade"}),
                         {"erro": "não encontrada no corpus aprovado"})
        self.assertEqual(banco.usadas(), ["equacao", "conceito"])   # não sondou arestas de quem não existe

    def test_ler_conceito_monta_campos(self):
        self.usar(BancoFalso({
            "conceito": [["fenomeno", "ganha com a desordem", ["antifrágil"], fonte("A.pdf.md", "Tríade")]],
            "conceito_heuristicas": [["barbell", "90/10", "kappa > 0.3", fonte("A.pdf.md", "Barbell")]],
            "conceito_equacoes": [["A.pdf.md#3", "f(x)", fonte("A.pdf.md", "Convexidade")]]}))
        r = MCP.tool_ler_conceito({"nome": "antifragilidade"})
        self.assertEqual(r["definicao"], "ganha com a desordem")
        self.assertEqual(r["sinonimos"], ["antifrágil"])
        self.assertEqual(r["heuristicas"][0]["nome"], "barbell")
        self.assertEqual(r["equacoes"][0]["nome"], "A.pdf.md#3")
        self.assertEqual(r["fonte"], {"documento": "A.pdf.md", "topico": "Tríade"})

    def test_situacao_camada_conta_aprovados_e_indices(self):
        self.usar(BancoFalso({"contagem_aprovados": [["Conceito", 2], ["Equacao", 5]],
                              "contagem_trechos": [[40]],
                              "indices": [["trecho_texto_incerto", "FULLTEXT", "ONLINE"], ["outro", "RANGE", "ONLINE"]]}))
        r = MCP.tool_situacao_camada({})
        self.assertEqual(r["corpus"], "incerto")
        self.assertEqual(r["aprovados"], {"Conceito": 2, "Equacao": 5})
        self.assertEqual(r["trechos"], 40)
        self.assertEqual(r["indices"], {"trecho_texto_incerto": "FULLTEXT ONLINE", "trecho_embedding_incerto": "ausente"})

    def test_situacao_camada_com_banco_fora_nao_lanca(self):
        self.usar(BancoFalso({"contagem_aprovados": OSError("Connection refused")}))
        r = MCP.tool_situacao_camada({})
        self.assertIn("Connection refused", r["neo4j"])


# ---------- banco real (CI): partição incerto-teste ----------

SEMEAR_NOS = """UNWIND $linhas AS l
CALL { WITH l WITH l WHERE l.rotulo = 'Equacao'
       CREATE (:Equacao {corpus: l.corpus, nome: l.nome, status: l.status, latex: l.nome, fonte: l.fonte}) }
CALL { WITH l WITH l WHERE l.rotulo = 'Variavel'
       CREATE (:Variavel {corpus: l.corpus, nome: l.nome, simbolo: l.nome, status: l.status, fonte: l.fonte}) }
CALL { WITH l WITH l WHERE l.rotulo = 'Conceito'
       CREATE (:Conceito {corpus: l.corpus, nome: l.nome, definicao: l.nome, status: l.status, fonte: l.fonte}) }
CALL { WITH l WITH l WHERE l.rotulo = 'Heuristica'
       CREATE (:Heuristica {corpus: l.corpus, nome: l.nome, enunciado: l.nome, status: l.status, fonte: l.fonte}) }
CALL { WITH l WITH l WHERE l.rotulo = 'Trecho'
       CREATE (:Trecho {corpus: l.corpus, documento: l.documento, topico: l.topico, parte: 1, texto: l.texto}) }"""

SEMEAR_ARESTA = {
    tipo: ("UNWIND $linhas AS l MATCH (a {corpus: $corpus, nome: l.de}) MATCH (b {corpus: $corpus, nome: l.para}) "
           "CREATE (a)-[:%s {corpus: $corpus, status: l.status, fonte: l.fonte, condicao: l.condicao, "
           "verificado_por: l.verificado_por}]->(b)" % tipo)
    for tipo in ("USA", "VALIDA_SOB", "DERIVA_DE", "SUSTENTA", "EXPRESSA")}


@precisa_neo4j
class TesteSoAprovadoNoBanco(unittest.TestCase):
    def setUp(self):
        self.cred, self.db = banco_de_teste()
        self.addCleanup(limpar_banco_de_teste, self.cred, self.db)
        self.q = lambda s, p=None: MCP.NUC.query_api(self.cred, self.db, s, p or {})
        MCP.CONTEXTO = (self.cred, self.db, self.q)
        self.addCleanup(setattr, MCP, "CONTEXTO", None)
        amb = mock.patch.dict(os.environ, {"INCERTO_CORPUS": PARTICAO})
        amb.start()
        self.addCleanup(amb.stop)
        self.f = fonte("D.pdf.md", "T")

    def nos(self, *linhas):
        self.q(SEMEAR_NOS, {"linhas": [dict({"corpus": PARTICAO, "fonte": self.f, "documento": None,
                                             "topico": None, "texto": None, "nome": None}, **l) for l in linhas]})

    def aresta(self, tipo, de, para, status, **extra):
        linha = dict({"de": de, "para": para, "status": status, "fonte": self.f, "condicao": None,
                      "verificado_por": None}, **extra)
        self.q(SEMEAR_ARESTA[tipo], {"corpus": PARTICAO, "linhas": [linha]})

    def test_ler_equacao_nunca_devolve_staging(self):
        self.nos({"rotulo": "Equacao", "nome": "D.pdf.md#1", "status": "staging"},
                 {"rotulo": "Equacao", "nome": "D.pdf.md#2", "status": "aprovado"})
        self.assertEqual(MCP.tool_ler_equacao({"nome": "D.pdf.md#1"}), {"erro": "não encontrada no corpus aprovado"})
        self.assertEqual(MCP.tool_ler_equacao({"nome": "D.pdf.md#9"}), {"erro": "não encontrada no corpus aprovado"})
        self.assertEqual(MCP.tool_ler_equacao({"nome": "D.pdf.md#2"})["latex"], "D.pdf.md#2")

    def test_aresta_em_staging_entre_nos_aprovados_nao_aparece(self):
        self.nos({"rotulo": "Equacao", "nome": "E#filha", "status": "aprovado"},
                 {"rotulo": "Equacao", "nome": "E#mae", "status": "aprovado"},
                 {"rotulo": "Equacao", "nome": "E#mae2", "status": "aprovado"},
                 {"rotulo": "Equacao", "nome": "E#mae-staging", "status": "staging"},
                 {"rotulo": "Variavel", "nome": "x", "status": "aprovado"},
                 {"rotulo": "Variavel", "nome": "y", "status": "aprovado"},
                 {"rotulo": "Conceito", "nome": "convexidade", "status": "aprovado"},
                 {"rotulo": "Heuristica", "nome": "h-ok", "status": "aprovado"},
                 {"rotulo": "Heuristica", "nome": "h-staging-aresta", "status": "aprovado"},
                 {"rotulo": "Heuristica", "nome": "h-staging-no", "status": "staging"})
        vp = ["sympy@1.14.0", "wolfram"]
        self.aresta("DERIVA_DE", "E#filha", "E#mae", "staging", verificado_por=[])      # aresta em staging
        self.aresta("DERIVA_DE", "E#filha", "E#mae2", "aprovado", verificado_por=vp)
        self.aresta("DERIVA_DE", "E#filha", "E#mae-staging", "aprovado", verificado_por=vp)   # ponta em staging
        self.aresta("USA", "E#filha", "x", "aprovado")
        self.aresta("USA", "E#filha", "y", "staging")
        self.aresta("VALIDA_SOB", "E#filha", "x", "staging", condicao="x > 0")
        self.aresta("VALIDA_SOB", "E#filha", "x", "aprovado", condicao="x < 9")
        self.aresta("SUSTENTA", "h-ok", "convexidade", "aprovado")
        self.aresta("SUSTENTA", "h-staging-aresta", "convexidade", "staging")
        self.aresta("SUSTENTA", "h-staging-no", "convexidade", "aprovado")
        self.aresta("EXPRESSA", "E#mae", "convexidade", "staging")
        self.aresta("EXPRESSA", "E#mae2", "convexidade", "aprovado")
        eq = MCP.tool_ler_equacao({"nome": "E#filha"})
        self.assertEqual([d["mae"] for d in eq["deriva_de"]], ["E#mae2"])
        self.assertEqual(eq["deriva_de"][0]["verificado_por"], vp)
        self.assertEqual([v["nome"] for v in eq["variaveis"]], ["x"])
        self.assertEqual([v["condicao"] for v in eq["valida_sob"]], ["x < 9"])
        c = MCP.tool_ler_conceito({"nome": "convexidade"})
        self.assertEqual([h["nome"] for h in c["heuristicas"]], ["h-ok"])
        self.assertEqual([e["nome"] for e in c["equacoes"]], ["E#mae2"])
        sit = MCP.tool_situacao_camada({})
        self.assertEqual(sit["aprovados"], {"Conceito": 1, "Equacao": 3, "Heuristica": 2, "Variavel": 2})

    def test_outro_corpus_nao_aparece(self):
        self.nos({"rotulo": "Equacao", "nome": "D.pdf.md#1", "status": "aprovado"},
                 {"rotulo": "Conceito", "nome": "peru", "status": "aprovado"})
        with mock.patch.dict(os.environ, {"INCERTO_CORPUS": PARTICAO + "-outro"}):
            self.assertEqual(MCP.tool_ler_equacao({"nome": "D.pdf.md#1"}), {"erro": "não encontrada no corpus aprovado"})
            self.assertEqual(MCP.tool_ler_conceito({"nome": "peru"}), {"erro": "não encontrada no corpus aprovado"})
            self.assertEqual(MCP.tool_situacao_camada({})["aprovados"], {})

    def test_buscar_equacao_lexical_so_cita_aprovada_e_nunca_o_texto(self):
        self.q("CREATE FULLTEXT INDEX trecho_texto_incerto IF NOT EXISTS FOR (t:Trecho) ON EACH [t.texto]")
        self.q("CALL db.awaitIndexes(300)")
        f_kappa = fonte("K.pdf.md", "Kappa")
        self.nos({"rotulo": "Trecho", "documento": "K.pdf.md", "topico": "Kappa", "texto": "a métrica kappa de Taleb"},
                 {"rotulo": "Equacao", "nome": "K.pdf.md#1", "status": "aprovado", "fonte": f_kappa},
                 {"rotulo": "Equacao", "nome": "K.pdf.md#2", "status": "staging", "fonte": f_kappa})
        with mock.patch.object(MCP.NUC, "embed_gemini", side_effect=SystemExit("rota Vertex: sem token")):
            r = MCP.tool_buscar_equacao({"pergunta": "kappa"})
            self.assertEqual(r["modo"], "lexical")
            self.assertEqual(r["resultados"], [{"documento": "K.pdf.md", "topico": "Kappa", "equacao": ["K.pdf.md#1"]}])
            self.assertNotIn("métrica", json.dumps(r, ensure_ascii=False))
            with mock.patch.dict(os.environ, {"INCERTO_CORPUS": PARTICAO + "-outro"}):
                self.assertEqual(MCP.tool_buscar_equacao({"pergunta": "kappa"})["resultados"], [])


if __name__ == "__main__":
    unittest.main()
