# -*- coding: utf-8 -*-
"""Task 15: relatorio.py — relatório por ativo, com marcação de fonte por número e veredito que nunca
recomenda ativo. Fixture SINTÉTICA (Student-t, df=3, semente 15): B3 é inalcançável aqui e o ticker é fictício."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from _carga import RAIZ, carregar

sys.modules.setdefault("dados_br", carregar("skills/taleb/scripts/dados_br.py"))
sys.modules.setdefault("caudas", carregar("skills/taleb/scripts/caudas.py"))
sys.modules.setdefault("convexidade", carregar("skills/taleb/scripts/convexidade.py"))
R = carregar("skills/taleb/scripts/relatorio.py")
D = sys.modules["dados_br"]

FIX = os.path.join(RAIZ, "build", "testes", "fixtures", "dados_br")
FECHAMENTO = "Isto não é recomendação de ativo."
SECOES = ("## Caudas", "## Convexidade", "## Ergodicidade", "## Veredito")


def retornos_sinteticos():
    with open(os.path.join(FIX, "retornos-sinteticos.json"), encoding="utf-8") as f:
        dados = json.load(f)
    return [(date.fromisoformat(d), r) for d, r in dados["retornos"]]


class TesteRelatorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rets = retornos_sinteticos()

    def rel(self, status=None, **kw):
        return R.relatorio_ativo("TESTE3", self.rets, 0.0005, status, **kw)

    def test_fixture_e_sintetica_e_declara_a_origem(self):
        with open(os.path.join(FIX, "retornos-sinteticos.json"), encoding="utf-8") as f:
            dados = json.load(f)
        self.assertEqual(set(dados), {"gerado_por", "retornos"})
        self.assertGreaterEqual(len(dados["retornos"]), 500)
        self.assertIn("random.Random(15)", dados["gerado_por"])

    def test_secoes_fixas_presentes_e_em_ordem(self):
        t = self.rel()
        posicoes = [t.index(s) for s in SECOES]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertIn("TESTE3", t.split("\n")[0])

    def test_sem_grafo_tudo_e_externo(self):
        for status in (None, {}):
            t = self.rel(status)
            self.assertNotIn("[corpus]", t)
            self.assertNotIn("[staging]", t)
            self.assertIn("[externo]", t)

    def test_aprovado_vira_corpus_e_so_a_equacao_certa(self):
        t = self.rel({R.EQ_KAPPA: "aprovado", R.EQ_HILL: "staging"})
        linhas = t.split("\n")
        kappa = [l for l in linhas if "`kappa`" in l and "κ" in l and "domínio" not in l]
        self.assertTrue(kappa and all("[corpus]" in l for l in kappa))
        hill = [l for l in linhas if f"`{R.EQ_HILL}`" in l]
        self.assertTrue(hill and all("[staging]" in l and "[corpus]" not in l for l in hill))
        temporal = [l for l in linhas if f"`{R.EQ_CRESC_TEMPORAL}`" in l]
        self.assertTrue(temporal and all("[externo]" in l for l in temporal))
        dominio = [l for l in linhas if l.startswith("- domínio")]
        self.assertTrue(dominio and dominio[0].endswith("[staging]"))  # mais fraca entre corpus e staging

    def test_status_desconhecido_e_externo(self):
        t = self.rel({R.EQ_KAPPA: "rejeitado"})
        self.assertNotIn("[corpus]", t)

    def test_todo_numero_traz_equacao_e_marca(self):
        t = self.rel({R.EQ_KAPPA: "aprovado"})
        for l in t.split("\n"):
            if l.startswith("- ") and re.search(r"\d|[<>≤≥]", l):
                self.assertRegex(l, r"\[(corpus|staging|externo)\]$", l)
                self.assertTrue(re.search(r"`\w+`", l) or "fonte:" in l or "limiar do incerto" in l, l)

    def test_veredito_nunca_recomenda(self):
        # Escolha: o fecho fixo "Isto não é recomendação de ativo." contém "recomend". O teste mantém o regex
        # original do brief e exclui EXATAMENTE essa linha (e exige que ela seja a última do relatório).
        for status in (None, {R.EQ_KAPPA: "aprovado", R.EQ_HILL: "staging"}):
            t = self.rel(status)
            linhas = [l for l in t.rstrip("\n").split("\n")]
            self.assertEqual(linhas[-1], FECHAMENTO)
            restante = "\n".join(linhas[:-1])
            self.assertIsNone(re.search(r"\b(comprar|vender|recomend)", restante, re.I), restante)
            self.assertEqual(t.count(FECHAMENTO), 1)

    def test_veredito_usa_so_o_vocabulario_permitido(self):
        t = self.rel()
        veredito = t[t.index("## Veredito"):]
        self.assertRegex(veredito, r"Extremistão|Mediocristão")
        self.assertRegex(veredito, r"frágil|robusto|antifrágil")

    def test_veredito_extremistao_para_cauda_gorda_e_mediocristao_para_gaussiana(self):
        t = self.rel()
        self.assertIn("Extremistão", t[t.index("## Veredito"):])
        import random
        r = random.Random(3)
        g = [(date(2020, 1, 1), r.gauss(0, 0.01)) for _ in range(400)]
        t2 = R.relatorio_ativo("TESTE3", g, 0.0, None)
        v = t2[t2.index("## Veredito"):]
        self.assertIn("Mediocristão", v)
        self.assertIn("domínio: **Mediocristão**", v)
        self.assertNotIn("**Extremistão**", v)

    def test_classificacao_vem_da_assimetria_empirica(self):
        C = sys.modules["convexidade"]
        h = C.assimetria_empirica([r for _, r in self.rets])
        t = self.rel()
        baixo, alto = R.intervalo_h([r for _, r in self.rets])
        self.assertLessEqual(baixo, h)
        self.assertGreaterEqual(alto, h)
        esperado = R.classe_fragilidade(baixo, alto)
        v = t[t.index("## Veredito"):]
        self.assertIn(f"fragilidade: **{esperado}**", v)
        self.assertIn(f"[{baixo:.6f}; {alto:.6f}]", v)
        self.assertIn(f"[{baixo:.6f}; {alto:.6f}]", t[t.index("## Convexidade"):t.index("## Ergodicidade")])

    def classe(self, retornos):
        t = R.relatorio_ativo("TESTE3", retornos, 0.0, None)
        return re.search(r"- fragilidade: \*\*(\w+)\*\*", t).group(1)

    def test_gaussiana_simetrica_e_robusta(self):
        import random
        r = random.Random(11)
        g = [(date(2020, 1, 1), r.gauss(0, 0.015)) for _ in range(500)]
        self.assertEqual(self.classe(g), "robusto")

    def test_amostra_assimetrica_e_antifragil_ou_fragil(self):
        import random
        r = random.Random(12)
        # cauda direita longa e consistente (ganhos grandes frequentes): convexa
        direita = [(date(2020, 1, 1), r.gauss(0, 0.01) + (0.08 if r.random() < 0.08 else 0.0)) for _ in range(800)]
        esquerda = [(d, -x) for d, x in direita]
        self.assertEqual(self.classe(direita), "antifrágil")
        self.assertEqual(self.classe(esquerda), "frágil")

    def test_aviso_de_precos_nao_ajustados(self):
        self.assertIn("Preços do COTAHIST não são ajustados por proventos ou desdobramentos; "
                      "um desdobramento aparece como retorno espúrio.", self.rel())

    def test_relatorio_e_deterministico_byte_a_byte(self):
        a, b = self.rel({R.EQ_KAPPA: "aprovado"}), self.rel({R.EQ_KAPPA: "aprovado"})
        self.assertEqual(a.encode("utf-8"), b.encode("utf-8"))
        self.assertTrue(a.endswith("\n"))

    def test_taxa_livre_so_na_ergodicidade_com_fonte(self):
        a = R.relatorio_ativo("TESTE3", self.rets, 0.0005, None, fonte_taxa_livre="SGS série 11")
        b = R.relatorio_ativo("TESTE3", self.rets, 0.0010, None, fonte_taxa_livre="SGS série 11")
        def sem_erg(t):
            i, j = t.index("## Ergodicidade"), t.index("## Veredito")
            return t[:i] + t[j:]
        self.assertEqual(sem_erg(a), sem_erg(b))
        self.assertNotEqual(a, b)
        erg = a[a.index("## Ergodicidade"):a.index("## Veredito")]
        self.assertIn("SGS série 11", erg)
        self.assertIn("excesso", erg)

    def test_menos_de_60_retornos_recusa_com_a_contagem(self):
        with self.assertRaises(ValueError) as c:
            R.relatorio_ativo("TESTE3", self.rets[:59], 0.0, None)
        self.assertIn("59", str(c.exception))
        R.relatorio_ativo("TESTE3", self.rets[:60], 0.0, None)  # 60 passa

    def test_retorno_nao_finito_recusa(self):
        ruim = self.rets[:100] + [(date(2025, 1, 1), float("nan"))]
        with self.assertRaises(ValueError):
            R.relatorio_ativo("TESTE3", ruim, 0.0, None)


class TesteCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def cotahist_sintetico(self):
        """COTAHIST de TESTE3 a partir dos retornos sintéticos (preço = exp(soma dos retornos))."""
        import math
        with open(os.path.join(FIX, "cotahist-minimo.txt"), encoding="latin-1") as f:
            modelo = f.read().split("\n")[1]
        linhas, preco = [], 30.0
        rets = retornos_sinteticos()
        pontos = [(rets[0][0], preco)]
        for d, r in rets:
            preco *= math.exp(r)
            pontos.append((d, preco))
        for d, p in pontos:
            l = modelo[:2] + d.strftime("%Y%m%d") + modelo[10:12] + "TESTE3".ljust(12) + modelo[24:108] \
                + str(int(round(p * 100))).zfill(13) + modelo[121:]
            linhas.append(l)
        caminho = os.path.join(self.tmp, "COTAHIST_TESTE.txt")
        with open(caminho, "w", encoding="latin-1", newline="\n") as f:
            f.write("\n".join(linhas) + "\n")
        return caminho, pontos[1][0], pontos[-1][0]

    def roda(self, *args, abrir=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                codigo = R.main(list(args), **({} if abrir is None else {"abrir": abrir}))
            except SystemExit as e:
                codigo = e.code
        return codigo, out.getvalue(), err.getvalue()

    def test_cli_le_cotahist_e_selic_do_cache_sem_rede(self):
        caminho, ini, fim = self.cotahist_sintetico()
        cache = os.path.join(self.tmp, "dados")
        os.makedirs(cache)
        with open(D._caminho_cache(cache, 11, ini, fim), "w", encoding="utf-8") as f:
            json.dump([["2023-01-03", 0.05], ["2023-01-04", 0.07]], f)
        def sem_rede(*a, **k):
            raise AssertionError("tocou a rede")
        codigo, out, err = self.roda("--ticker", "TESTE3", "--cotahist", caminho, "--sgs-cache", cache,
                                     abrir=sem_rede)
        self.assertEqual(codigo, 0, err)
        for s in SECOES:
            self.assertIn(s, out)
        self.assertIn("SGS série 11", out)
        self.assertIn("TESTE3", out)
        self.assertTrue(out.rstrip("\n").endswith(FECHAMENTO))

    def test_cli_status_equacoes_marca_por_rotulo(self):
        # I4: `--status-equacoes` (rótulo → status) chega ao relatório; os EQ_* são rótulos de :Equacao
        caminho, ini, fim = self.cotahist_sintetico()
        cache = os.path.join(self.tmp, "dados")
        os.makedirs(cache)
        with open(D._caminho_cache(cache, 11, ini, fim), "w", encoding="utf-8") as f:
            json.dump([["2023-01-03", 0.05], ["2023-01-04", 0.07]], f)
        status = os.path.join(self.tmp, "status.json")
        with open(status, "w", encoding="utf-8") as f:
            json.dump({R.EQ_KAPPA: "aprovado", R.EQ_HILL: "staging"}, f)
        codigo, out, err = self.roda("--ticker", "TESTE3", "--cotahist", caminho, "--sgs-cache", cache,
                                     "--status-equacoes", status)
        self.assertEqual(codigo, 0, err)
        self.assertRegex(out, r"κ\(n0=1, n=30\) = \S+ — equação `kappa` \[corpus\]")
        self.assertRegex(out, r"α̂ de Hill.*— equação `hill` \[staging\]")
        self.assertRegex(out, r"razão máximo/soma.*`razao_max_soma` \[externo\]")
        for conteudo in ("[1, 2]", "{\"kappa\": 1}", "não é json"):
            with open(status, "w", encoding="utf-8") as f:
                f.write(conteudo)
            codigo, out, err = self.roda("--ticker", "TESTE3", "--cotahist", caminho, "--sgs-cache", cache,
                                         "--status-equacoes", status)
            self.assertEqual((codigo, out), (2, ""), conteudo); self.assertIn("--status-equacoes", err)
        codigo, _, err = self.roda("--ticker", "TESTE3", "--cotahist", caminho, "--sgs-cache", cache,
                                   "--status-equacoes", os.path.join(self.tmp, "nada.json"))
        self.assertEqual(codigo, 2); self.assertIn("nada.json", err)
        for rotulo in (R.EQ_KAPPA, R.EQ_HILL, R.EQ_MAX_SOMA, R.EQ_ASSIMETRIA, R.EQ_CRESC_TEMPORAL, R.EQ_CRESC_ENSEMBLE):
            self.assertRegex(rotulo, r"^[a-z][a-z0-9_]*$")

    def test_cli_ticker_ausente_e_erro_legivel(self):
        caminho, _, _ = self.cotahist_sintetico()
        codigo, out, err = self.roda("--ticker", "NADA9", "--cotahist", caminho, "--sgs-cache", self.tmp)
        self.assertEqual(codigo, 2)
        self.assertIn("NADA9", err)

    def test_cli_amostra_pequena_recusa_com_codigo_2(self):
        codigo, out, err = self.roda("--ticker", "PETR4", "--cotahist", os.path.join(FIX, "cotahist-minimo.txt"),
                                     "--sgs-cache", self.tmp)
        self.assertEqual(codigo, 2)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
