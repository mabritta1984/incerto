# -*- coding: utf-8 -*-
"""Incerto: ingerir_trechos.py — ingestão idempotente e retomável de :Trecho com embedding Vertex.

O Vertex é falso (nenhum teste toca rede): `nucleo._abrir` é substituído por um servidor de mentira que
responde `embedContent` e conta as chamadas. Os testes de banco real são `@precisa_neo4j` (CI)."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from _banco import PARTICAO, banco_de_teste, limpar_banco_de_teste, precisa_neo4j
from _carga import carregar

NUC = sys.modules.setdefault("nucleo", carregar("skills/lavra/scripts/nucleo.py"))   # o `import nucleo` do script
ING = carregar("skills/lavra/scripts/ingerir_trechos.py")
CRED = {"INCERTO_GCP_PROJETO": "proj", "CLOUDSDK_AUTH_ACCESS_TOKEN": "tok-falso"}


class Resposta(io.BytesIO):
    def __init__(self, obj):
        super().__init__(json.dumps(obj).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class VertexFalso:
    """Substitui `nucleo._abrir`: embedContent do Vertex é respondido aqui; o resto passa para o original."""
    def __init__(self):
        self.textos = []
        self._original = NUC._abrir

    def __call__(self, req, timeout):
        if "aiplatform.googleapis.com" in req.full_url:
            self.textos.append(json.loads(req.data)["content"]["parts"][0]["text"])
            return Resposta({"embedding": {"values": [0.25] * NUC.GEMINI_DIM},
                             "usageMetadata": {"promptTokenCount": 3}})
        return self._original(req, timeout)


def trecho(i, corpus=PARTICAO, **extra):
    l = {"documento": "Doc%d.pdf.md" % (i // 3), "topico": "Tópico %d" % i, "parte": 1, "ordem": i,
         "corpus": corpus, "onda": "onda-t", "texto": "## Tópico %d\ntexto verbatim %d" % (i, i)}
    l.update(extra)
    return l


def escrever_jsonl(caminho, linhas):
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        for l in linhas:
            f.write(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "_esteira", "incerto", "ingestao-onda-t.json")
        self.vertex = VertexFalso()
        p = mock.patch.object(NUC, "_abrir", self.vertex)
        p.start(); self.addCleanup(p.stop)

    def calar(self, f, *a, **k):
        return f(*a, saida=lambda s: None, **k)


class TesteSemBanco(Base):
    def setUp(self):
        super().setUp()
        self.escritas = []

        def falso(cred, db, stmt, params):
            if stmt == ING.CYPHER_GRAVAR:
                if len(self.escritas) == self.falhar_no:
                    raise RuntimeError("banco caiu")
                self.escritas.append(params["linhas"])
            return []
        self.falhar_no = None
        p = mock.patch.object(NUC, "query_com_retentativa", falso)
        p.start(); self.addCleanup(p.stop)

    def test_retomavel_pelo_state(self):
        linhas = [trecho(i) for i in range(40)]                   # 16 + 16 + 8
        self.falhar_no = 2                                          # cai no 3º lote, após o 2º
        with self.assertRaises(RuntimeError):
            self.calar(ING.ingerir, CRED, "db", linhas, PARTICAO, self.state)
        self.assertEqual(len(self.vertex.textos), 40)               # o 3º lote (8) já tinha sido embedado
        with io.open(self.state, encoding="utf-8") as f:
            gravado = json.load(f)["gravadas"]
        self.assertEqual(len(gravado), 32); self.assertEqual(gravado, sorted(gravado))
        self.vertex.textos.clear(); self.falhar_no = None
        agora, recusadas = self.calar(ING.ingerir, CRED, "db", linhas, PARTICAO, self.state)
        self.assertEqual((agora, recusadas), (8, []))
        self.assertEqual(len(self.vertex.textos), 8)                # só os 8 restantes foram ao Vertex
        self.vertex.textos.clear()
        self.assertEqual(self.calar(ING.ingerir, CRED, "db", linhas, PARTICAO, self.state), (0, []))
        self.assertEqual(self.vertex.textos, [])

    def test_state_com_formato_deterministico(self):
        self.calar(ING.ingerir, CRED, "db", [trecho(1), trecho(0)], PARTICAO, self.state)
        with io.open(self.state, encoding="utf-8", newline="") as f:
            bruto = f.read()
        self.assertNotIn("\r", bruto)
        self.assertEqual(json.loads(bruto), {"corpus": PARTICAO, "gravadas": sorted(json.loads(bruto)["gravadas"])})
        self.assertIn("Tópico 0", bruto)                            # ensure_ascii=False

    def test_cabecalho_entra_no_vetor_mas_o_no_guarda_so_o_texto(self):
        l = trecho(0, parte=2, cabecalho="## Tópico 0", junta="\n", texto="resto do texto")
        self.calar(ING.ingerir, CRED, "db", [l], PARTICAO, self.state)
        self.assertEqual(self.vertex.textos, ["## Tópico 0\nresto do texto"])
        gravada = self.escritas[0][0]
        self.assertEqual((gravada["texto"], gravada["cabecalho"], gravada["junta"]),
                         ("resto do texto", "## Tópico 0", "\n"))
        self.assertEqual(len(gravada["embedding"]), NUC.GEMINI_DIM)

    def test_nunca_grava_sem_corpus(self):
        sem = trecho(1); del sem["corpus"]
        caminho = os.path.join(self.tmp, "t.jsonl")
        escrever_jsonl(caminho, [trecho(0), sem])
        with self.assertRaises(ValueError) as ctx:
            ING.ler_trechos(caminho, PARTICAO)
        self.assertIn("corpus", str(ctx.exception))
        # pelo main: antes de abrir o banco ou chamar o Vertex
        with mock.patch.object(NUC, "abrir_banco", side_effect=AssertionError("rede")):
            with self.assertRaises(ValueError):
                ING.main(["--entrada", caminho, "--corpus", PARTICAO])
        self.assertEqual(self.vertex.textos, [])

    def test_state_de_outro_corpus_e_recusado_e_state_novo_grava(self):
        self.calar(ING.ingerir, CRED, "db", [trecho(0)], PARTICAO, self.state)
        self.vertex.textos.clear(); n = len(self.escritas)
        with self.assertRaises(ValueError) as ctx:
            self.calar(ING.ingerir, CRED, "db", [trecho(0, corpus="incerto")], "incerto", self.state)
        self.assertIn(PARTICAO, str(ctx.exception)); self.assertIn("incerto", str(ctx.exception))
        self.assertIn(self.state, str(ctx.exception))
        self.assertEqual((self.vertex.textos, len(self.escritas)), ([], n))      # nada embedado nem gravado
        novo = os.path.join(self.tmp, "outro.json")
        self.assertEqual(self.calar(ING.ingerir, CRED, "db", [trecho(0, corpus="incerto")], "incerto", novo)[0], 1)
        self.assertEqual(len(self.escritas), n + 1)

    def test_state_legado_sem_corpus_e_recusado_antes_da_rede(self):
        os.makedirs(os.path.dirname(self.state))
        with io.open(self.state, "w", encoding="utf-8") as f:
            json.dump({"gravadas": []}, f)
        caminho = os.path.join(self.tmp, "t.jsonl"); escrever_jsonl(caminho, [trecho(0)])
        with mock.patch.object(NUC, "abrir_banco", side_effect=AssertionError("rede")):
            with self.assertRaises(ValueError):
                ING.main(["--entrada", caminho, "--corpus", PARTICAO, "--state", self.state])

    def test_corpus_divergente_do_argumento_e_recusado(self):
        caminho = os.path.join(self.tmp, "t.jsonl")
        escrever_jsonl(caminho, [trecho(0, corpus="incerto")])
        with self.assertRaises(ValueError):
            ING.ler_trechos(caminho, PARTICAO)

    def test_acima_do_limite_nao_vai_ao_state(self):
        with mock.patch.object(NUC, "embed_gemini", return_value=([None, [0.0] * NUC.GEMINI_DIM], 0)):
            agora, recusadas = self.calar(ING.ingerir, CRED, "db", [trecho(0), trecho(1)], PARTICAO, self.state)
        self.assertEqual((agora, len(recusadas)), (1, 1))
        self.assertEqual(len(ING.ler_state(self.state, PARTICAO)), 1)


class TesteVerificar(unittest.TestCase):
    def test_acusa_dimensao_errada(self):
        linhas, ok = ING.avaliar_verificacao([["onda-t", 1]], [], [["Doc.pdf.md", "T", 1, 10]])
        self.assertFalse(ok)
        self.assertTrue(any(l.startswith("✘") and "dimensão" in l for l in linhas))
        self.assertTrue(any("tamanho 10" in l for l in linhas))

    def test_acusa_duplicada_e_banco_vazio(self):
        self.assertFalse(ING.avaliar_verificacao([["onda-t", 2]], [["D", "T", 1, 2]], [])[1])
        self.assertFalse(ING.avaliar_verificacao([], [], [])[1])

    def test_tudo_certo(self):
        linhas, ok = ING.avaliar_verificacao([["a", 2], ["b", 1]], [], [])
        self.assertTrue(ok); self.assertIn("  a: 2", linhas)

    def test_exit_1_quando_falha(self):
        respostas = {ING.CYPHER_POR_ONDA: [["o", 1]], ING.CYPHER_DUPLICADAS: [],
                     ING.CYPHER_DIMENSAO: [["D", "T", 1, 10]]}
        with mock.patch.object(NUC, "abrir_banco", return_value=({}, "db", None)), \
                mock.patch.object(NUC, "query_api", lambda c, d, s, p=None: respostas[s]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ING.main(["--verificar", "--corpus", PARTICAO]), 1)
        self.assertIn("✘", out.getvalue())


@precisa_neo4j
class TesteBancoReal(Base):
    def setUp(self):
        super().setUp()
        self.cred, self.db = banco_de_teste()
        self.addCleanup(limpar_banco_de_teste, self.cred, self.db)
        self.cred.update(CRED)

    def contar(self, rotulo):
        return NUC.query_api(self.cred, self.db, "MATCH (n:%s {corpus: $c}) RETURN count(n)" % rotulo,
                             {"c": PARTICAO})[0][0]

    def test_idempotente_duas_execucoes_mesma_contagem(self):
        linhas = [trecho(i) for i in range(7)] + [trecho(2, parte=2, cabecalho="## Tópico 2", junta="\n")]
        for rodada in (1, 2):
            # sem state na 2ª rodada: o MERGE sozinho tem de segurar a idempotência
            state = os.path.join(self.tmp, "s%d.json" % rodada)
            self.calar(ING.ingerir, self.cred, self.db, linhas, PARTICAO, state)
            self.assertEqual(self.contar("Trecho"), 8)
            self.assertEqual(self.contar("Documento"), 3)
        arestas = NUC.query_api(self.cred, self.db, "MATCH (:Trecho {corpus:$c})-[r:PERTENCE_A]->(:Documento) "
                                "RETURN count(r)", {"c": PARTICAO})[0][0]
        self.assertEqual(arestas, 8)
        self.assertTrue(ING.verificar(self.cred, self.db, PARTICAO, saida=lambda s: None))
        nomes = {r[0] for r in NUC.query_api(self.cred, self.db, "SHOW INDEXES YIELD name")}
        self.assertTrue({ING.INDICE_VETORIAL, ING.INDICE_TEXTO} <= nomes)


if __name__ == "__main__":
    unittest.main()
