# -*- coding: utf-8 -*-
"""Task 10: registrar_prova.py — a prova Wolfram que o agente rodou pelo MCP vira uma linha de
`provas-<onda>.jsonl`, com código e saída verbatim, chaves ordenadas e sem timestamp; chave repetida é
recusada sem `--substituir`."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from _carga import carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
sys.modules.setdefault("fiscal", carregar("skills/lavra/scripts/fiscal.py"))   # vizinho do import local
RP = carregar("skills/lavra/scripts/registrar_prova.py")

ONDA = "2026-10-T10"
CODIGO_KELLY = "Simplify[(p - (1 - p)/b) - (f /. First@Solve[p b/(1 + b f) - (1 - p)/(1 - f) == 0, f])]\n"
SAIDA_KELLY = "Out[1]= 0\n"
CODIGO_PARETO = ("Expectation[x, x \\[Distributed] ParetoDistribution[L, alpha], "
                 "Assumptions -> alpha > 1 && L > 0]\n")
SAIDA_PARETO = "Symbol::undefined: Warning: Global symbol L is undefined.\n\nOut[1]= (alpha*L)/(-1 + alpha)\n"


class TesteRegistrar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.arquivo = os.path.join(self.tmp, "provas-%s.jsonl" % ONDA)

    def texto(self, nome, conteudo):
        caminho = os.path.join(self.tmp, nome)
        with io.open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)
        return caminho

    def rodar(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return RP.main(["--onda", ONDA, "--raiz-esteira", self.tmp] + list(args))

    def p2(self, mae="kelly#1", filha="kelly#2", veredito="verde", saida=SAIDA_KELLY, *extra):
        return self.rodar("--prova", "P2", "--mae", mae, "--filha", filha,
                          "--codigo", self.texto("k.wl", CODIGO_KELLY), "--saida", self.texto("k.txt", saida),
                          "--veredito", veredito, *extra)

    def momento(self, equacao="pareto#3", veredito="verde", *extra):
        return self.rodar("--prova", "momento", "--equacao", equacao,
                          "--codigo", self.texto("p.wl", CODIGO_PARETO), "--saida", self.texto("p.txt", SAIDA_PARETO),
                          "--veredito", veredito, *extra)

    def linhas(self):
        with io.open(self.arquivo, encoding="utf-8", newline="") as f:
            return f.read()

    def test_registrar_anexa_linha_ordenada_sem_timestamp(self):
        self.assertEqual(self.p2(), 0)
        self.assertEqual(self.momento(), 0)
        texto = self.linhas()
        self.assertTrue(texto.endswith("\n")); self.assertNotIn("\r", texto)
        brutas = texto.splitlines()
        self.assertEqual(len(brutas), 2)
        for l in brutas:
            self.assertEqual(l, json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False))
        p2, mom = (json.loads(l) for l in brutas)
        self.assertEqual(p2, {"prova": "P2", "via": "wolfram", "mae": "kelly#1", "filha": "kelly#2",
                              "codigo": CODIGO_KELLY, "saida": SAIDA_KELLY, "veredito": "verde"})
        self.assertEqual(mom, {"prova": "momento", "via": "wolfram", "equacao": "pareto#3",
                               "codigo": CODIGO_PARETO, "saida": SAIDA_PARETO, "veredito": "verde"})
        self.assertIn("\\[Distributed]", brutas[1])           # código verbatim, nada reescrito

    def test_mesma_sequencia_da_os_mesmos_bytes(self):
        self.p2(); self.momento()
        primeiro = self.linhas()
        os.remove(self.arquivo)
        self.p2(); self.momento()
        self.assertEqual(self.linhas(), primeiro)

    def test_saida_verbatim_com_acento_e_sem_traducao_de_quebra(self):
        saida = "Out[1]= ((-1 + b^2)*(-1 + p))/b\r\nnão é zero\n"
        self.assertEqual(self.p2("kelly#1", "kelly#9", "vermelho", saida), 0)
        linha = self.linhas()
        self.assertIn("não é zero", linha)                    # ensure_ascii=False
        self.assertEqual(json.loads(linha)["saida"], saida)  # o \r\n da saída é preservado

    def test_chave_repetida_e_recusada_sem_substituir(self):
        self.p2()
        antes = self.linhas()
        with self.assertRaises(SystemExit):
            self.p2(veredito="vermelho")
        self.assertEqual(self.linhas(), antes)
        self.momento()
        with self.assertRaises(SystemExit):
            self.momento()
        self.assertEqual(self.p2("kelly#1", "kelly#3"), 0)    # outra filha da mesma mãe é outra chave

    def test_substituir_reescreve_sem_a_linha_antiga(self):
        self.p2(); self.momento(); self.p2("a#1", "a#2")
        self.assertEqual(self.p2("kelly#1", "kelly#2", "indeterminado", SAIDA_KELLY, "--substituir"), 0)
        linhas = [json.loads(l) for l in self.linhas().splitlines()]
        self.assertEqual([(l["prova"], l.get("mae"), l.get("filha"), l.get("equacao"), l["veredito"]) for l in linhas],
                         [("momento", None, None, "pareto#3", "verde"), ("P2", "a#1", "a#2", None, "verde"),
                          ("P2", "kelly#1", "kelly#2", None, "indeterminado")])
        self.assertEqual(self.momento("pareto#4", "verde", "--substituir"), 0)   # substituir sem antiga = anexar
        self.assertEqual(len(self.linhas().splitlines()), 4)

    def test_caminho_padrao_e_sobrescrevivel(self):
        outro = os.path.join(self.tmp, "sub", "minhas.jsonl")
        self.assertEqual(self.momento("pareto#3", "verde", "--provas-wolfram", outro), 0)
        self.assertFalse(os.path.exists(self.arquivo))
        with io.open(outro, encoding="utf-8") as f:
            self.assertEqual(json.loads(f.read())["equacao"], "pareto#3")

    def test_argumentos_incoerentes_sao_recusados(self):
        cod, sai = self.texto("c.wl", CODIGO_KELLY), self.texto("s.txt", SAIDA_KELLY)
        base = ["--codigo", cod, "--saida", sai, "--veredito", "verde"]
        for args in (["--prova", "P2", "--mae", "a#1"] + base,                               # sem filha
                     ["--prova", "P2", "--mae", "a#1", "--filha", "a#2", "--equacao", "a#2"] + base,
                     ["--prova", "momento"] + base,                                        # sem equação
                     ["--prova", "momento", "--equacao", "a#1", "--mae", "a#0"] + base,
                     ["--prova", "P5", "--equacao", "a#1"] + base,
                     ["--prova", "momento", "--equacao", "a#1", "--codigo", cod, "--saida", sai, "--veredito", "talvez"],
                     ["--prova", "momento", "--equacao", "a#1", "--codigo", cod, "--saida", self.texto("v.txt", " \n"),
                      "--veredito", "verde"],                                              # saída vazia
                     ["--prova", "momento", "--equacao", "a#1", "--codigo", os.path.join(self.tmp, "nao.wl"),
                      "--saida", sai, "--veredito", "verde"]):
            with self.assertRaises(SystemExit, msg=args):
                self.rodar(*args)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            RP.main(["--onda", "../x", "--prova", "momento", "--equacao", "a#1"] + base)
        self.assertFalse(os.path.exists(self.arquivo))


if __name__ == "__main__":
    unittest.main()
