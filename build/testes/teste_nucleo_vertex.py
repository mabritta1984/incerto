# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/teste_nucleo_vertex.py
"""Incerto: a rota Gemini do núcleo é o Vertex AI, endpoint global, com Bearer (D5)."""
import io
import json
import unittest
import urllib.error
from unittest import mock
from _carga import carregar

NUC = carregar("skills/lavra/scripts/nucleo.py")
CRED = {"INCERTO_GCP_PROJETO": "proj", "CLOUDSDK_AUTH_ACCESS_TOKEN": "tok-da-sessao"}


class Resposta(io.BytesIO):
    def __init__(self, obj):
        super().__init__(json.dumps(obj).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _erro(codigo, corpo, cabecalhos=None):
    return urllib.error.HTTPError("https://aiplatform.googleapis.com/x", codigo,
                                  "Erro — %s" % corpo, cabecalhos or {}, None)


class TesteURLeToken(unittest.TestCase):
    def test_url_global_do_projeto_e_modelo(self):
        self.assertEqual(NUC.url_vertex(CRED, "embedContent"),
                         "https://aiplatform.googleapis.com/v1/projects/proj/locations/global/publishers/google/"
                         "models/gemini-embedding-2:embedContent")

    def test_sem_projeto_sai_com_mensagem(self):
        with self.assertRaises(SystemExit) as ctx:
            NUC.url_vertex({}, "embedContent")
        self.assertIn("INCERTO_GCP_PROJETO", str(ctx.exception))

    def test_token_do_ambiente(self):
        self.assertEqual(NUC.token_vertex(CRED), "tok-da-sessao")

    def test_token_do_servidor_de_metadados(self):
        abridor = mock.Mock(); abridor.open.return_value = Resposta({"access_token": "tok-meta"})
        with mock.patch.dict(NUC.os.environ, {}, clear=True), \
                mock.patch.object(NUC.urllib.request, "build_opener", return_value=abridor):
            self.assertEqual(NUC.token_vertex({"INCERTO_GCP_PROJETO": "proj"}), "tok-meta")
        req = abridor.open.call_args[0][0]
        self.assertEqual(req.get_header("Metadata-flavor"), "Google")

    def test_sem_token_sai_listando_o_que_tentou(self):
        abridor = mock.Mock(); abridor.open.side_effect = OSError("sem rota")
        with mock.patch.dict(NUC.os.environ, {}, clear=True), \
                mock.patch.object(NUC.urllib.request, "build_opener", return_value=abridor):
            with self.assertRaises(SystemExit) as ctx:
                NUC.token_vertex({})
        self.assertIn("CLOUDSDK_AUTH_ACCESS_TOKEN", str(ctx.exception))
        self.assertIn("metadados", str(ctx.exception))


class TesteChamada(unittest.TestCase):
    def test_bearer_sem_chave_e_corpo_com_auto_truncate_falso(self):
        with mock.patch.object(NUC, "_abrir", return_value=Resposta(
                {"embedding": {"values": [0.5] * 3072}, "usageMetadata": {"promptTokenCount": 7}})) as ab:
            vetores, tokens = NUC.embed_gemini(CRED, ["title: none | text: ET0"], espera=lambda s: None)
        self.assertEqual(len(vetores[0]), 3072); self.assertEqual(tokens, 7)
        req = ab.call_args[0][0]
        self.assertEqual(req.get_header("Authorization"), "Bearer tok-da-sessao")
        self.assertIsNone(req.get_header("X-goog-api-key"))
        self.assertIn("/locations/global/", req.full_url)
        corpo = json.loads(req.data)
        self.assertIs(corpo["autoTruncate"], False)
        self.assertEqual(corpo["outputDimensionality"], 3072)

    def test_texto_acima_do_limite_e_recusado_nunca_truncado(self):
        excesso = _erro(400, '{"error": {"code": 400, "message": "The input text at index 0 exceeds the maximum '
                             'number of tokens this model can process (8192), and auto_truncate has been set to false"}}')
        with mock.patch.object(NUC, "_abrir", side_effect=excesso):
            vetores, tokens = NUC.embed_gemini(CRED, ["x" * 50000], espera=lambda s: None)
        self.assertEqual(vetores, [None]); self.assertEqual(tokens, 0)

    def test_truncated_na_resposta_tambem_e_recusa(self):
        with mock.patch.object(NUC, "_abrir", return_value=Resposta(
                {"embedding": {"values": [0.1] * 3072}, "truncated": True})):
            vetores, _t = NUC.embed_gemini(CRED, ["x"], espera=lambda s: None)
        self.assertEqual(vetores, [None])

    def test_outro_400_sobe(self):
        with mock.patch.object(NUC, "_abrir", side_effect=_erro(400, '{"error": {"message": "invalid argument"}}')):
            with self.assertRaises(urllib.error.HTTPError):
                NUC.embed_gemini(CRED, ["x"], espera=lambda s: None)

    def test_429_espera_retry_after_e_repete(self):
        esperas = []
        respostas = [_erro(429, "cota", {"Retry-After": "3"}),
                     Resposta({"embedding": {"values": [0.0] * 3072}})]
        with mock.patch.object(NUC, "_abrir", side_effect=respostas):
            vetores, _t = NUC.embed_gemini(CRED, ["x"], espera=esperas.append)
        self.assertEqual(esperas, [3.0]); self.assertEqual(len(vetores[0]), 3072)

    def test_401_nao_repete(self):
        with mock.patch.object(NUC, "_abrir", side_effect=_erro(401, "token recusado")) as ab:
            with self.assertRaises(urllib.error.HTTPError):
                NUC.embed_gemini(CRED, ["x"], espera=lambda s: None)
        self.assertEqual(ab.call_count, 1)


if __name__ == "__main__":
    unittest.main()
