# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 build/testes/teste_recorte.py
"""Incerto: recortar_trechos.py — recorte verbatim por onda, equações display nunca partidas."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unicodedata
import unittest
from _carga import RAIZ, carregar

REC = carregar("skills/lavra/scripts/recortar_trechos.py")
FIXTURE = os.path.join(RAIZ, "build", "testes", "fixtures", "extraidos", "2026-09-PSX-1")
GUAN = "2009-Guan-086d27f4-659c-4719-34ef-27e3e9abd50f.pdf.md"
ONDA = "2026-09-PSX-1"


def ler(caminho):
    with io.open(caminho, encoding="utf-8", newline="") as f:
        return f.read()


class Corpus(unittest.TestCase):
    """<tmp>/conferidos/<onda>/ montado em temp; `rodar` chama o main() e devolve as linhas do JSONL."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir = os.path.join(self.tmp, "conferidos", ONDA)
        os.makedirs(self.dir)
        self.saida = os.path.join(self.tmp, "_esteira", "incerto", "trechos-%s.jsonl" % ONDA)

    def escrever(self, rel, texto):
        p = os.path.join(self.dir, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texto)

    def rodar(self, *extra, onda=ONDA):
        argv = ["--raiz", self.tmp, "--onda", onda, "--saida", self.saida] + list(extra)
        with contextlib.redirect_stdout(io.StringIO()):
            REC.main(argv)
        with io.open(self.saida, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]


class TesteTopicoGrandeComSubtitulos(unittest.TestCase):
    """Q6 (0.20.17): `painel-grafico.md` › "O que você pode fazer?" era UM trecho de 24 mil chars — o recorte em
    `##` diluía "Cadastrar Operação" (`####`, 941 chars) e a busca o punha em 8º; recortado no nível 4, em 1º.
    O recorte não muda: o inventário AVISA e sugere o nível do primeiro subtítulo."""
    TEXTO = ("# T\n\n## O que você pode fazer?\n\n### Criar\n\n" + "a" * 5000 + "\n\n#### Cadastrar Operação\n\n"
             + "b" * 5000 + "\n\n## Curto\n\n" + "c" * 9000)

    def test_avisa_e_sugere_o_nivel_do_primeiro_subtitulo(self):
        chunks, alertas = REC.recortar_texto(self.TEXTO, 2, 0, 32000, 120000)
        self.assertEqual(len(chunks), 3)                                   # o recorte não muda
        grandes = [a for a in alertas if "O que você pode fazer?" in a]
        self.assertEqual(len(grandes), 1, alertas)
        self.assertIn("--nivel 3", grandes[0])

    def test_topico_grande_sem_subtitulo_nao_avisa(self):
        _, alertas = REC.recortar_texto(self.TEXTO, 2, 0, 32000, 120000)
        self.assertFalse([a for a in alertas if "Curto" in a], alertas)   # 9 mil chars, sem subtítulo

    def test_limiar_configuravel(self):
        _, alertas = REC.recortar_texto(self.TEXTO, 2, 0, 32000, 120000, subtitulo_chars=20000)
        self.assertEqual(alertas, [])

    def test_acima_do_alerta_longo_leva_a_sugestao_na_mesma_linha(self):
        _, alertas = REC.recortar_texto(self.TEXTO, 2, 0, 8000, 120000)
        grandes = [a for a in alertas if "O que você pode fazer?" in a]
        self.assertEqual(len(grandes), 1, alertas)
        self.assertIn("tópico longo", grandes[0]); self.assertIn("--nivel 3", grandes[0])


class TesteSemDivisao(unittest.TestCase):
    def test_maxlen_zero_nao_parte(self):
        self.assertEqual([p for _, p in REC.split_topic("p1\n\np2\n\n" + "x" * 50000, 0)], ["p1\n\np2\n\n" + "x" * 50000])
    def test_maxlen_positivo_continua_partindo(self):
        self.assertEqual(len(REC.split_topic("a" * 10 + "\n\n" + "b" * 10, 12)), 2)
    def test_ordem_e_alertas(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\n" + "y" * 40000
        chunks, alertas = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["ordem"] for c in chunks], [1, 2, 3])
        self.assertEqual([c["parte"] for c in chunks], [1, 1, 1])
        self.assertEqual(len(alertas), 1); self.assertIn("B", alertas[0])
    def test_teto_aborta(self):
        with self.assertRaises(SystemExit):
            REC.recortar_texto("## A\n\n" + "z" * 130000, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
    def test_titulo_permanece_no_texto(self):
        chunks, _ = REC.recortar_texto("# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\nfim", 2, 0, 32000, 120000)
        self.assertEqual([c["texto"] for c in chunks], ["# T\n\nabertura", "## A\n\ncurto", "## B\n\nfim"])

class TesteDesambiguacao(unittest.TestCase):
    def test_topico_repetido_ganha_o_titulo_pai(self):
        # Book.md do Shield: `### Dica` sob "# Clustering" e sob "# Sprint" colidiam na chave.
        texto = "# Clustering\n\n## Dica\n\nc1\n\n## Dicas\n\nc2\n\n# Sprint\n\n## Dica\n\ns1\n\n## Dicas\n\ns2\n\n## Só aqui\n\nx"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        # o segundo `# Sprint` NÃO abre novo "(abertura)": o preâmbulo só existe antes do
        # primeiro título de nível N; a linha `# Sprint` fica anexada ao bloco anterior, como hoje.
        self.assertEqual([c["topico"] for c in chunks],
                         ["(abertura)", "Dica — Clustering", "Dicas — Clustering", "Dica — Sprint", "Dicas — Sprint", "Só aqui"])
        self.assertEqual([c["ordem"] for c in chunks], [1, 2, 3, 4, 5, 6])
        # o texto continua verbatim: a linha `## Dica` não muda, só a chave
        self.assertTrue(chunks[1]["texto"].startswith("## Dica\n"))

    def test_repetido_sem_pai_ganha_numero(self):
        texto = "## Nota\n\na\n\n## Nota\n\nb"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["Nota (1)", "Nota (2)"])

    def test_sem_repeticao_nada_muda(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\nfim"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["(abertura)", "A", "B"])


class TesteSemDivisao(unittest.TestCase):
    def test_maxlen_zero_nao_parte(self):
        self.assertEqual([p for _, p in REC.split_topic("p1\n\np2\n\n" + "x" * 50000, 0)], ["p1\n\np2\n\n" + "x" * 50000])
    def test_maxlen_positivo_continua_partindo(self):
        self.assertEqual(len(REC.split_topic("a" * 10 + "\n\n" + "b" * 10, 12)), 2)
    def test_ordem_e_alertas(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\n" + "y" * 40000
        chunks, alertas = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["ordem"] for c in chunks], [1, 2, 3])
        self.assertEqual([c["parte"] for c in chunks], [1, 1, 1])
        self.assertEqual(len(alertas), 1); self.assertIn("B", alertas[0])
    def test_teto_aborta(self):
        with self.assertRaises(SystemExit):
            REC.recortar_texto("## A\n\n" + "z" * 130000, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
    def test_titulo_permanece_no_texto(self):
        chunks, _ = REC.recortar_texto("# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\nfim", 2, 0, 32000, 120000)
        self.assertEqual([c["texto"] for c in chunks], ["# T\n\nabertura", "## A\n\ncurto", "## B\n\nfim"])

class TesteDesambiguacao(unittest.TestCase):
    def test_topico_repetido_ganha_o_titulo_pai(self):
        # Book.md do Shield: `### Dica` sob "# Clustering" e sob "# Sprint" colidiam na chave.
        texto = "# Clustering\n\n## Dica\n\nc1\n\n## Dicas\n\nc2\n\n# Sprint\n\n## Dica\n\ns1\n\n## Dicas\n\ns2\n\n## Só aqui\n\nx"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        # o segundo `# Sprint` NÃO abre novo "(abertura)": o preâmbulo só existe antes do
        # primeiro título de nível N; a linha `# Sprint` fica anexada ao bloco anterior, como hoje.
        self.assertEqual([c["topico"] for c in chunks],
                         ["(abertura)", "Dica — Clustering", "Dicas — Clustering", "Dica — Sprint", "Dicas — Sprint", "Só aqui"])
        self.assertEqual([c["ordem"] for c in chunks], [1, 2, 3, 4, 5, 6])
        # o texto continua verbatim: a linha `## Dica` não muda, só a chave
        self.assertTrue(chunks[1]["texto"].startswith("## Dica\n"))

    def test_repetido_sem_pai_ganha_numero(self):
        texto = "## Nota\n\na\n\n## Nota\n\nb"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["Nota (1)", "Nota (2)"])

    def test_sem_repeticao_nada_muda(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\nfim"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["(abertura)", "A", "B"])


class TesteRecorteDaOnda(Corpus):
    def test_topico_e_fatia_verbatim_do_original(self):
        original = ler(os.path.join(FIXTURE, GUAN))
        self.escrever(GUAN, original)
        linhas = self.rodar()
        self.assertGreater(len(linhas), 2)
        for l in linhas:
            self.assertIn(l["texto"], original)
            if l["topico"] != "(abertura)":
                self.assertTrue(l["texto"].startswith("## "), l["topico"])
                self.assertEqual(l["texto"].split("\n", 1)[0], "## " + l["topico"].split(" — ")[0].split(" (")[0])

    def test_chave_posix_e_corpus_incerto(self):
        self.escrever("sub/dir/Livro.pdf.md", "## A\n\ntexto\n")
        self.escrever("Raiz.pdf.md", "## B\n\ntexto\n")
        linhas = self.rodar()
        self.assertEqual([l["documento"] for l in linhas], ["Raiz.pdf.md", "sub/dir/Livro.pdf.md"])
        for l in linhas:
            self.assertEqual(l["corpus"], "incerto"); self.assertEqual(l["onda"], ONDA)
            self.assertNotIn("\\", l["documento"])
        for chave in ("documento", "topico", "parte", "ordem", "texto"):
            self.assertIn(chave, linhas[0])

    def test_recusa_md_sem_extensao_de_origem(self):
        self.escrever("Relatorio.md", "## A\n\ntexto\n")
        with self.assertRaises(SystemExit) as e:
            self.rodar()
        self.assertIn("Relatorio.md", str(e.exception))
        self.assertFalse(os.path.exists(self.saida))
        os.remove(os.path.join(self.dir, "Relatorio.md"))
        self.escrever("Relatorio.pdf.md", "## A\n\ntexto\n")
        self.assertEqual(len(self.rodar()), 1)

    def test_pula_manifesto_relatorio_lote_e_assets(self):
        self.escrever("X.pdf.md", "## A\n\ntexto\n")
        self.escrever("X.pdf.report.json", "{}")
        self.escrever("manifesto.json", "{}")
        self.escrever("lote-2026-09-27.md", "# lote\n")
        self.escrever("X.pdf.assets/nota.md", "## ignorada\n")
        self.assertEqual({l["documento"] for l in self.rodar()}, {"X.pdf.md"})

    def test_onda_inexistente_ou_invalida(self):
        for onda in ("nao-existe", "../x"):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                self.rodar(onda=onda)

    def test_determinismo_e_manifesto_sem_timestamp(self):
        self.escrever("B.pdf.md", ler(os.path.join(FIXTURE, GUAN)))
        self.escrever("A.pdf.md", "## A\n\ntexto\n")
        self.rodar()
        primeiro = ler(self.saida)
        man = ler(REC.caminho_manifesto(self.saida))
        os.remove(self.saida); os.remove(REC.caminho_manifesto(self.saida))
        self.rodar()
        self.assertEqual(primeiro, ler(self.saida)); self.assertEqual(man, ler(REC.caminho_manifesto(self.saida)))
        self.assertNotIn("\r", primeiro)
        m = json.loads(man)
        self.assertEqual(m["execucoes"][0]["versao_plugin"], REC.versao_plugin())
        self.assertNotIn("data", m["execucoes"][0])
        self.assertEqual(man, json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))
        docs = [json.loads(l)["documento"] for l in primeiro.splitlines()]
        self.assertEqual(docs, sorted(docs, key=lambda d: d.encode("utf-8")))

    def test_versao_vem_do_plugin_json(self):
        with io.open(os.path.join(RAIZ, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            self.assertEqual(REC.versao_plugin(), json.load(f)["version"])

    def test_documento_repetido_aborta_e_anexa_outro(self):
        self.escrever("A.pdf.md", "## A\n\ntexto\n")
        self.rodar()
        with self.assertRaises(SystemExit) as e:
            self.rodar()
        self.assertIn("A.pdf.md", str(e.exception))


class TesteEquacaoDisplay(unittest.TestCase):
    CORPO = ("## Eq\n\nantes do bloco, texto corrido.\n\n$$\n\\sigma = a + b\n\n"
             "\\frac{x}{y} = z\n$$\n\ndepois do bloco\n\nfim")

    def test_equacao_display_nao_e_partida(self):
        ini = self.CORPO.index("$$")
        fim = self.CORPO.index("$$", ini + 2) + 2
        for maxlen in range(30, len(self.CORPO)):
            pares = REC.split_topic(self.CORPO, maxlen)
            self.assertEqual("".join(j + p for j, p in pares), self.CORPO)
            for _, p in pares:
                self.assertEqual(p.count("$$") % 2, 0, (maxlen, p))
        # o corte cai dentro do bloco (maxlen=45 limita na linha em branco interna): o bloco fica inteiro
        pares = REC.split_topic(self.CORPO, 45)
        self.assertTrue(any(p.count("$$") == 2 and "\\frac{x}{y} = z" in p and "\\sigma" in p for _, p in pares))
        self.assertGreater(len(pares), 1)

    def test_pela_via_do_recorte_e_do_main(self):
        chunks, _ = REC.recortar_texto(self.CORPO, 2, 45, 32000, 120000)
        self.assertTrue(any("\\sigma" in c["texto"] and "\\frac{x}{y}" in c["texto"] for c in chunks))
        self.assertEqual("".join(c["junta"] + c["texto"] for c in chunks), self.CORPO)

    def test_bloco_sem_fechamento_fica_numa_parte_so(self):
        corpo = "abc\n\n$$\nx = 1\n\n" + "y\n" * 50
        pares = REC.split_topic(corpo, 20)          # sem fechamento: prefere uma parte longa a cortar a equação
        self.assertEqual(pares, [("", corpo)])

    def test_fixture_real_com_maxlen_pequeno_nunca_parte_display(self):
        original = ler(os.path.join(FIXTURE, GUAN))
        chunks, _ = REC.recortar_texto(original, 2, 400, 32000, 120000)
        for c in chunks:
            self.assertEqual(c["texto"].count("$$") % 2, 0, c["texto"][:80])


class TesteChaveNFC(unittest.TestCase):
    def test_topico_em_nfc_texto_verbatim(self):
        txt = "## Especificação\ncorpo\n"
        chunks, _ = REC.recortar_texto(txt, 2, 0, 32000, 120000)
        self.assertEqual(chunks[0]["topico"], "Especificação")
        self.assertIn("Especificação", chunks[0]["texto"])

    def test_aviso_de_nfc_confere_so_o_caminho_relativo(self):
        self.assertIsNone(REC.aviso_nome_fora_nfc("docs/Especificação.pdf.md", "docs/Especificação.pdf.md"))
        nfd = unicodedata.normalize("NFD", "Relatório.pdf.md")
        aviso = REC.aviso_nome_fora_nfc(nfd, nfd)
        self.assertIn("fora de NFC", aviso)

    def test_chave_local_nfc_e_posix(self):
        self.assertEqual(REC.chave_local("a\\Especificação.md"), "a/Especificação.md")


class TestePartesVerbatim(unittest.TestCase):
    """P-AK: corte só em fronteira de linha (na falta, espaço; na falta, duro), separador gravado,
    e juntar as partes reproduz o corpo — inclusive tabela sem linha em branco."""

    def _junta(self, pares):
        return "".join(j + p for j, p in pares)

    def test_sem_divisao_devolve_um_par(self):
        self.assertEqual(REC.split_topic("abc", 0), [("", "abc")])

    def test_tabela_sem_linha_em_branco_reconstroi(self):
        corpo = "## EParameters\n" + "".join("| P%03d | valor %d |\n" % (i, i) for i in range(500))
        pares = REC.split_topic(corpo, 800)
        self.assertGreater(len(pares), 1)
        self.assertEqual(self._junta(pares), corpo)
        for j, p in pares[1:]:
            self.assertEqual(j, "\n"); self.assertTrue(p.startswith("| P"))    # nunca no meio da linha

    def test_paragrafo_prefere_linha_em_branco(self):
        corpo = "A" * 50 + "\n\n" + "B" * 50 + "\nC" * 10
        pares = REC.split_topic(corpo, 70)
        self.assertEqual(pares[1][0], "\n\n"); self.assertEqual(self._junta(pares), corpo)

    def test_linha_gigante_corta_em_espaco_e_depois_duro(self):
        corpo = ("palavra " * 30).strip() + "\n" + "x" * 90
        pares = REC.split_topic(corpo, 40)
        self.assertEqual(self._junta(pares), corpo)
        self.assertIn(" ", [j for j, _ in pares])
        self.assertIn("", [j for j, _ in pares[1:]])                         # 90 x sem espaço: duro
        self.assertTrue(all(len(p) <= 40 for _, p in pares))

    def test_espacos_nas_pontas_nao_somem(self):
        corpo = "  inicio\n" + "linha\n" * 30 + "fim  "
        self.assertEqual(self._junta(REC.split_topic(corpo, 50)), corpo)

    def test_chunk_grava_junta_e_cabecalho_so_nas_partes_seguintes(self):
        texto = "## Tabela\n" + "".join("| %d |\n" % i for i in range(200))
        chunks, _ = REC.recortar_texto(texto, 2, 300, 32000, 120000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["junta"], ""); self.assertNotIn("cabecalho", chunks[0])
        self.assertEqual(chunks[1]["cabecalho"], "## Tabela")
        self.assertTrue(chunks[0]["texto"].startswith("## Tabela"))
        self.assertFalse(chunks[1]["texto"].startswith("## Tabela"))           # título só no embedding
        corpo = texto.strip()
        self.assertEqual("".join(c["junta"] + c["texto"] for c in chunks), corpo)


class TesteAlertaPeloContexto(unittest.TestCase):
    def test_alerta_sai_do_contexto_declarado(self):
        texto = "## Grande\n" + "x\n" * 13000        # ~26 mil chars
        _, alertas = REC.recortar_texto(texto, 2, 0, REC.alerta_do_contexto(8192), 120000)
        self.assertEqual(len(alertas), 1); self.assertIn("Grande", alertas[0])
        # 20/09/2026: o alerta recua pelo PISO medido (1,8), não pela média (3) — a média não
        # protege texto denso. Ver teste_contexto_tokens.py.
        self.assertEqual(REC.alerta_do_contexto(8192), 14745)



class TesteManifesto(Corpus):
    def test_caminho_ao_lado_do_jsonl(self):
        self.assertEqual(REC.caminho_manifesto(self.saida), os.path.join(os.path.dirname(self.saida), "trechos-%s.manifesto.json" % ONDA))

    def test_hash_independe_da_ordem_das_chaves_e_depende_do_texto(self):
        a = [{"documento": "d.md", "texto": "x", "ordem": 1}]
        b = [{"ordem": 1, "texto": "x", "documento": "d.md"}]
        self.assertEqual(REC.sha256_trechos(a), REC.sha256_trechos(b))
        self.assertNotEqual(REC.sha256_trechos(a), REC.sha256_trechos([{"documento": "d.md", "texto": "y", "ordem": 1}]))

    def test_segunda_execucao_anexa(self):
        os.makedirs(os.path.dirname(self.saida))
        self.assertEqual(REC.registrar_execucao(REC.caminho_manifesto(self.saida), {"nivel": 2}), 1)
        self.assertEqual(REC.registrar_execucao(REC.caminho_manifesto(self.saida), {"nivel": 3}), 2)
        m = json.loads(ler(REC.caminho_manifesto(self.saida)))
        self.assertEqual([e["execucao"] for e in m["execucoes"]], [1, 2])

    def test_saida_com_linha_invalida_aborta_com_mensagem_util(self):
        self.escrever("A.pdf.md", "## A\n\ntexto\n")
        os.makedirs(os.path.dirname(self.saida))
        with io.open(self.saida, "w", encoding="utf-8") as f:
            f.write('{"documento": "outro.md", "topico": "X", "texto": "y"}\n{"documento": "truncado')
        with self.assertRaises(SystemExit) as e:
            self.rodar()
        self.assertIn("linha 2", str(e.exception)); self.assertIn(self.saida, str(e.exception))

    def test_repetidos_acima_de_vinte_diz_o_total_e_a_truncagem(self):
        for i in range(25):
            self.escrever("d%02d.pdf.md" % i, "## T\ntexto\n")
        self.rodar()
        with self.assertRaises(SystemExit) as e:
            self.rodar()
        self.assertIn("25", str(e.exception)); self.assertIn("truncad", str(e.exception))


if __name__ == "__main__":
    unittest.main()
