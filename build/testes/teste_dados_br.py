# -*- coding: utf-8 -*-
"""Task 12: dados_br.py — SGS do BCB e COTAHIST da B3. Nenhum teste toca a rede: `abrir` é falso e os
arquivos vêm de fixtures montadas à mão a partir dos formatos documentados; o cache é um diretório temporário."""
import contextlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import unittest
import urllib.error
import zipfile
from datetime import date
from _carga import RAIZ, carregar

DB = carregar("skills/taleb/scripts/dados_br.py")
FIX = os.path.join(RAIZ, "build", "testes", "fixtures", "dados_br")


def ler(caminho, modo="rb", **kw):
    with open(caminho, modo, **kw) as f:
        return f.read()


def gravar(caminho, conteudo, modo="w", **kw):
    with open(caminho, modo, **kw) as f:
        f.write(conteudo)


class Resp:
    def __init__(self, corpo, status=200):
        self.status = status
        self._corpo = corpo if isinstance(corpo, bytes) else corpo.encode("utf-8")

    def read(self):
        return self._corpo

    def close(self):
        pass


def abrir_fixture(nome):
    corpo = ler(os.path.join(FIX, nome))
    return lambda url, timeout=None: Resp(corpo)


def abrir_404(url, timeout=None):
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


class Contador:
    """`abrir` falso que registra as URLs e devolve, por janela, uma linha por ano pedido."""
    def __init__(self):
        self.urls = []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        m = re.search(r"dataInicial=(\d\d/\d\d/\d{4})&dataFinal=(\d\d/\d\d/\d{4})", url)
        corpo = [{"data": m.group(1), "valor": "1.5"}, {"data": m.group(2), "valor": "2.5"}]
        return Resp(json.dumps(corpo))


class TesteSGS(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_sgs_le_valor_string_e_data_ddmmaaaa(self):
        serie = DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=abrir_fixture("sgs-11.json"))
        self.assertEqual(serie[0], (date(2026, 9, 1), 0.055131))
        self.assertIsInstance(serie[0][1], float)

    def test_sgs_url_exata(self):
        c = Contador()
        DB.sgs(11, date(2026, 1, 2), date(2026, 3, 4), cache=self.tmp, abrir=c)
        self.assertEqual(c.urls, ["https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados"
                                  "?formato=json&dataInicial=02/01/2026&dataFinal=04/03/2026"])

    def test_sgs_codigo_invalido_e_erro_legivel(self):
        with self.assertRaises(DB.DadosIndisponiveis) as c:
            DB.sgs(999999, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=abrir_404)
        msg = str(c.exception)
        self.assertIn("999999", msg)
        self.assertIn("https://api.bcb.gov.br/dados/serie/bcdata.sgs.999999/dados", msg)
        self.assertIsInstance(c.exception, Exception)

    def test_sgs_status_diferente_de_200_e_erro(self):
        with self.assertRaises(DB.DadosIndisponiveis) as c:
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=lambda u, timeout=None: Resp("[]", 500))
        self.assertIn("11", str(c.exception))

    def test_sgs_corpo_nao_lista_e_erro(self):
        corpo = '{"error": "Value(s) not found"}'
        with self.assertRaises(DB.DadosIndisponiveis):
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=lambda u, timeout=None: Resp(corpo))
        with self.assertRaises(DB.DadosIndisponiveis):
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=lambda u, timeout=None: Resp("<html>"))

    def test_sgs_falha_de_rede_e_erro_legivel(self):
        def cai(url, timeout=None):
            raise urllib.error.URLError("bloqueado")
        with self.assertRaises(DB.DadosIndisponiveis) as c:
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=cai)
        self.assertIn("bcdata.sgs.11", str(c.exception))

    def test_sgs_erro_nao_grava_cache(self):
        with self.assertRaises(DB.DadosIndisponiveis):
            DB.sgs(999999, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=abrir_404)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_sgs_usa_cache_na_segunda_chamada(self):
        c = Contador()
        a = DB.sgs(11, date(2026, 1, 2), date(2026, 3, 4), cache=self.tmp, abrir=c)
        b = DB.sgs(11, date(2026, 1, 2), date(2026, 3, 4), cache=self.tmp, abrir=c)
        self.assertEqual(len(c.urls), 1)
        self.assertEqual(a, b)

    def test_sgs_periodo_que_chega_a_hoje_nunca_vai_ao_cache(self):
        # M4: o dia corrente (ou futuro) ainda não fechou; cacheá-lo congelaria uma série incompleta
        hoje = date(2026, 10, 5)
        for fim in (hoje, date(2026, 10, 9)):
            c = Contador()
            DB.sgs(11, date(2026, 10, 1), fim, cache=self.tmp, abrir=c, hoje=hoje)
            self.assertEqual(os.listdir(self.tmp), [], fim)
            gravar(DB._caminho_cache(self.tmp, 11, date(2026, 10, 1), fim), "[]")      # cache antigo, de antes
            self.assertTrue(DB.sgs(11, date(2026, 10, 1), fim, cache=self.tmp, abrir=c, hoje=hoje))
            self.assertEqual(len(c.urls), 2, fim)                                    # foi à rede as duas vezes
            os.remove(DB._caminho_cache(self.tmp, 11, date(2026, 10, 1), fim))
        c = Contador()
        DB.sgs(11, date(2026, 10, 1), date(2026, 10, 4), cache=self.tmp, abrir=c, hoje=hoje)   # até ontem: cacheia
        self.assertEqual(os.listdir(self.tmp), ["sgs-11-2026-10-01-2026-10-04.json"])

    def test_sgs_cache_cria_pasta_e_nome_deterministico(self):
        pasta = os.path.join(self.tmp, "novo", "dados")
        DB.sgs(11, date(2026, 9, 1), date(2026, 9, 2), cache=pasta, abrir=abrir_fixture("sgs-11.json"))
        self.assertEqual(os.listdir(pasta), ["sgs-11-2026-09-01-2026-09-02.json"])
        bruto = ler(os.path.join(pasta, "sgs-11-2026-09-01-2026-09-02.json"))
        self.assertNotIn(b"\r", bruto)
        self.assertEqual(bruto.decode("utf-8"), json.dumps(json.loads(bruto), sort_keys=True, ensure_ascii=False))

    def test_sgs_cache_gerado_e_identico_em_duas_pastas(self):
        outra = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outra, True)
        for p in (self.tmp, outra):
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 2), cache=p, abrir=abrir_fixture("sgs-11.json"))
        nome = "sgs-11-2026-09-01-2026-09-02.json"
        self.assertEqual(ler(os.path.join(self.tmp, nome)), ler(os.path.join(outra, nome)))

    def test_sgs_janela_de_ate_10_anos_nao_divide(self):
        c = Contador()
        DB.sgs(11, date(2016, 1, 1), date(2025, 12, 31), cache=self.tmp, abrir=c)
        self.assertEqual(len(c.urls), 1)

    def test_sgs_divide_em_janelas_de_ate_10_anos(self):
        c = Contador()
        serie = DB.sgs(11, date(2000, 1, 1), date(2025, 6, 30), cache=self.tmp, abrir=c)
        janelas = [re.search(r"dataInicial=(\S+)&dataFinal=(\S+)", u).groups() for u in c.urls]
        self.assertEqual(janelas, [("01/01/2000", "31/12/2009"), ("01/01/2010", "31/12/2019"),
                                   ("01/01/2020", "30/06/2025")])
        datas = [d for d, _ in serie]
        self.assertEqual(datas, sorted(datas))
        self.assertEqual(len(datas), len(set(datas)))
        self.assertEqual(datas[0], date(2000, 1, 1))
        self.assertEqual(datas[-1], date(2025, 6, 30))
        # o arquivo de cache é um só, com o intervalo pedido inteiro
        self.assertEqual(os.listdir(self.tmp), ["sgs-11-2000-01-01-2025-06-30.json"])

    def test_sgs_divisao_com_29_de_fevereiro(self):
        c = Contador()
        DB.sgs(11, date(2020, 2, 29), date(2040, 1, 1), cache=self.tmp, abrir=c)
        janelas = [re.search(r"dataInicial=(\S+)&dataFinal=(\S+)", u).groups() for u in c.urls]
        self.assertEqual(janelas[0][0], "29/02/2020")
        self.assertEqual(janelas[0][1], "27/02/2030")
        self.assertEqual(janelas[1][0], "28/02/2030")

    def test_sgs_deduplica_datas_na_fronteira_das_janelas(self):
        def abrir(url, timeout=None):  # devolve sempre a mesma data de fronteira
            return Resp(json.dumps([{"data": "31/12/2009", "valor": "1.0"}, {"data": "31/12/2009", "valor": "1.0"}]))
        serie = DB.sgs(11, date(2000, 1, 1), date(2015, 1, 1), cache=self.tmp, abrir=abrir)
        self.assertEqual(serie, [(date(2009, 12, 31), 1.0)])

    def test_sgs_intervalo_invertido_e_erro_de_uso(self):
        with self.assertRaises(ValueError):
            DB.sgs(11, date(2026, 9, 2), date(2026, 9, 1), cache=self.tmp, abrir=abrir_fixture("sgs-11.json"))

    def test_sgs_linha_malformada_e_erro_legivel(self):
        corpo = json.dumps([{"data": "01/09/2026", "valor": ""}])
        with self.assertRaises(DB.DadosIndisponiveis) as c:
            DB.sgs(11, date(2026, 9, 1), date(2026, 9, 1), cache=self.tmp, abrir=lambda u, timeout=None: Resp(corpo))
        self.assertIn("11", str(c.exception))

    def test_series_documentadas(self):
        self.assertEqual(DB.SERIES, {"selic_diaria": 11, "cdi_diaria": 12, "selic_meta": 432,
                                     "ipca_mensal": 433, "ptax_venda": 1, "ibovespa": 7})


class TesteCotahist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.txt = os.path.join(FIX, "cotahist-minimo.txt")

    def test_fixture_tem_245_caracteres_por_linha(self):
        for l in ler(self.txt, "r", encoding="latin-1", newline="").split("\r\n")[:-1]:
            self.assertEqual(len(l), 245)

    def test_cotahist_ignora_cabecalho_e_rodape_e_divide_por_100(self):
        linhas = DB.cotahist_ler(self.txt, {"PETR4"})
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0]["preult"], 32.50)
        self.assertEqual(linhas[0]["data"], date(2025, 1, 2))
        self.assertEqual(linhas[0]["codneg"], "PETR4")
        self.assertEqual((linhas[0]["preabe"], linhas[0]["premax"], linhas[0]["premin"]), (32.10, 32.90, 31.90))
        self.assertEqual(linhas[0]["voltot"], 12345678.90)
        self.assertEqual(linhas[1]["data"], date(2025, 1, 3))

    def test_cotahist_sem_filtro_traz_so_registros_01(self):
        linhas = DB.cotahist_ler(self.txt)
        self.assertEqual([l["codneg"] for l in linhas], ["PETR4", "VALE3", "PETR4", "PETR4F"])
        self.assertTrue(all(l["tipreg"] == "01" for l in linhas))

    def test_cotahist_filtro_e_por_codigo_exato(self):
        self.assertEqual([l["codneg"] for l in DB.cotahist_ler(self.txt, {"VALE3"})], ["VALE3"])
        self.assertEqual(DB.cotahist_ler(self.txt, {"ITUB4"}), [])

    def test_cotahist_le_zip_pelo_primeiro_membro(self):
        caminho = os.path.join(self.tmp, "COTAHIST_A2025.ZIP")
        with zipfile.ZipFile(caminho, "w") as z:
            z.write(self.txt, "COTAHIST_A2025.TXT")
        self.assertEqual(DB.cotahist_ler(caminho, {"PETR4"}), DB.cotahist_ler(self.txt, {"PETR4"}))

    def test_cotahist_decodifica_latin1(self):
        # NOMRES 28–39 com acento: "AÇÃO" em latin-1 não pode virar lixo nem quebrar
        bruto = ler(self.txt).replace(b"VALE        ", "AÇÃO        ".encode("latin-1"))
        caminho = os.path.join(self.tmp, "acento.txt")
        gravar(caminho, bruto, "wb")
        self.assertEqual(DB.cotahist_ler(caminho, {"VALE3"})[0]["nomres"], "AÇÃO")

    def test_cotahist_registro_curto_ou_preco_corrompido_e_erro_com_numero_da_linha(self):
        linhas = ler(self.txt, "r", encoding="latin-1", newline="").split("\r\n")
        curta = os.path.join(self.tmp, "curta.txt")
        gravar(curta, "\r\n".join([linhas[0], linhas[1][:100]]), "w", encoding="latin-1", newline="")
        with self.assertRaisesRegex(ValueError, "linha 2"):
            DB.cotahist_ler(curta)
        ruim = os.path.join(self.tmp, "ruim.txt")
        l = linhas[1][:108] + "00000000ABCDE" + linhas[1][121:]
        gravar(ruim, "\r\n".join([linhas[0], l]), "w", encoding="latin-1", newline="")
        with self.assertRaisesRegex(ValueError, "linha 2"):
            DB.cotahist_ler(ruim)

    def test_cotahist_url(self):
        self.assertEqual(DB.cotahist_url(2025), "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A2025.ZIP")


class TesteRetornos(unittest.TestCase):
    def test_retornos_log(self):
        d1, d2 = date(2026, 1, 2), date(2026, 1, 5)
        r = DB.retornos_log([(d1, 100.0), (d2, 110.0)])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0][0], d2)
        self.assertAlmostEqual(r[0][1], math.log(1.1))

    def test_retornos_log_descarta_preco_nao_positivo(self):
        s = [(date(2026, 1, 2), 100.0), (date(2026, 1, 5), 0.0), (date(2026, 1, 6), -3.0),
             (date(2026, 1, 7), 110.0), (date(2026, 1, 8), 121.0)]
        r = DB.retornos_log(s)
        # o 0.0 e o -3.0 somem; os consecutivos válidos são 100->110 (par em 7/1) e 110->121 (par em 8/1)
        self.assertEqual([d for d, _ in r], [date(2026, 1, 7), date(2026, 1, 8)])
        self.assertAlmostEqual(r[0][1], math.log(1.1))
        self.assertAlmostEqual(r[1][1], math.log(1.1))

    def test_retornos_log_vazio_ou_um_ponto(self):
        self.assertEqual(DB.retornos_log([]), [])
        self.assertEqual(DB.retornos_log([(date(2026, 1, 2), 5.0)]), [])


class TesteCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def rodar(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                codigo = DB.main(list(args), abrir=abrir_fixture("sgs-11.json"))
            except SystemExit as e:
                codigo = e.code
        return codigo, out.getvalue(), err.getvalue()

    def test_cli_sgs(self):
        cod, out, _ = self.rodar("--sgs", "11", "--inicio", "2026-09-01", "--fim", "2026-09-02", "--cache", self.tmp)
        self.assertEqual(cod, 0)
        self.assertEqual(out.splitlines()[0], "2026-09-01\t0.055131")

    def test_cli_cotahist_com_ticker(self):
        cod, out, _ = self.rodar("--cotahist", os.path.join(FIX, "cotahist-minimo.txt"), "--ticker", "PETR4")
        self.assertEqual(cod, 0)
        self.assertEqual(out.splitlines(), ["2025-01-02\tPETR4\t32.5", "2025-01-03\tPETR4\t33.15"])

    def test_cli_erro_de_dados_sai_2_sem_traceback(self):
        def abrir(url, timeout=None):
            raise urllib.error.HTTPError(url, 404, "x", {}, None)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cod = DB.main(["--sgs", "999999", "--inicio", "2026-09-01", "--fim", "2026-09-01", "--cache", self.tmp], abrir=abrir)
        self.assertEqual(cod, 2)
        self.assertIn("999999", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
