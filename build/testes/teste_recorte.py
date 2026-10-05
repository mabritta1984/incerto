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
        # o recorte não muda pelo aviso; `# T` sem corpo é prefixo do primeiro `##` (rodada corpus A)
        self.assertEqual([c["topico"] for c in chunks], ["O que você pode fazer?", "Curto"])
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
        # rodada corpus A: `# Clustering` e `# Sprint` não têm corpo — entram como prefixo verbatim do
        # `## Dica` seguinte, nunca no bloco de cima (antes `# Sprint` ficava no fim de "Dicas — Clustering").
        self.assertEqual([c["topico"] for c in chunks],
                         ["Dica — Clustering", "Dicas — Clustering", "Dica — Sprint", "Dicas — Sprint", "Só aqui"])
        self.assertEqual([c["ordem"] for c in chunks], [1, 2, 3, 4, 5])
        self.assertEqual(chunks[1]["texto"], "## Dicas\n\nc2")
        self.assertTrue(chunks[2]["texto"].startswith("# Sprint\n\n## Dica\n"))
        # o texto continua verbatim: a linha `## Dica` não muda, só a chave
        self.assertTrue(chunks[0]["texto"].startswith("# Clustering\n\n## Dica\n"))

    def test_repetido_sem_pai_ganha_numero(self):
        texto = "## Nota\n\na\n\n## Nota\n\nb"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["Nota (1)", "Nota (2)"])

    def test_sem_repeticao_nada_muda(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n\n## B\n\nfim"
        chunks, _ = REC.recortar_texto(texto, nivel=2, maxlen=0, alerta_chars=32000, teto_chars=120000)
        self.assertEqual([c["topico"] for c in chunks], ["T", "A", "B"])    # `# T` com corpo: tópico próprio


class TesteRecorteDaOnda(Corpus):
    def test_topico_e_fatia_verbatim_do_original(self):
        original = ler(os.path.join(FIXTURE, GUAN))
        self.escrever(GUAN, original)
        linhas = self.rodar()
        self.assertGreater(len(linhas), 2)
        for l in linhas:
            self.assertIn(l["texto"], original)
            if l["topico"] != "(abertura)":
                # o bloco abre com título de nível ≤ 2; o do tópico fecha a sequência de títulos do começo
                cabeca = [x for x in l["texto"].split("\n\n")[0].split("\n")]
                self.assertTrue(all(x.startswith(("# ", "## ")) for x in cabeca), l["topico"])
                self.assertEqual(cabeca[-1].split(" ", 1)[1], l["topico"].split(" — ")[0].split(" (")[0])

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

    def test_manifesto_declara_o_nivel_do_recorte(self):
        # I5: a extração de equações confere o `nivel` daqui para citar o mesmo tópico que o trecho
        self.escrever("A.pdf.md", "## A\n\n### B\n\ntexto\n")
        self.rodar("--nivel", "3")
        m = json.loads(ler(REC.caminho_manifesto(self.saida)))
        self.assertEqual([e["nivel"] for e in m["execucoes"]], [3])

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


# Trecho mínimo copiado de conferidos/2026-10-TALEB-1/Statistical_Consequences_of_Fat_Tails.pdf.md (linhas
# 651-801, parágrafos encurtados): a onda real, recortada com --nivel 3, deixou "# 3 …", "## 3.1 …" e todo o
# texto até o próximo `###` no tópico "2.2.31 Dynamic hedging".
SCFT = (
    "### 2.2.30 Metaprobability\n\n"
    "Comparing two probability distributions via some tricks which includes stochasticizing parameters.\n\n"
    "### 2.2.31 Dynamic hedging\n\n"
    "The payoff of a European call option C on an underlying S with expiration time indexed at T should be "
    "replicated with the following stream of dynamic hedges.\n\n"
    "We show where this replication is never possible in a fat-tailed environment, owing to presamptotics.\n\n"
    "Part I\n"
    "# FAT TAILS AND THEIR EFFECTS, AN INTRODUCTION\n\n"
    "# 3 A NON-TECHNICAL OVERVIEW - THE DARWIN COLLEGE LECTURE *,‡\n\n"
    "Abyssus abyssum invocat\nPsalms\n\n"
    "This chapter presents a nontechnical yet comprehensive presentation of of the entire statistical "
    "consequences of thick tails project.\n\n"
    "## 3.1 ON THE DIFFERENCE BETWEEN THIN AND THICK TAILS\n\n"
    "We begin with the notion of thick tails and how it relates to extremes using the two imaginary domains "
    "of Mediocristan (thin tails) and Extremistan (thick tails).\n\n"
    "## 3.2 A (MORE ADVANCED) CATEGORIZATION AND ITS CONSEQUENCES\n\n"
    "Let us now consider the degrees of thick tailedness in a casual way for now.\n\n"
    "### 3.3 THE MAIN CONSEQUENCES AND HOW THEY LINK TO THE BOOK\n\n"
    "fim\n")
T3 = "3 A NON-TECHNICAL OVERVIEW - THE DARWIN COLLEGE LECTURE *,‡"
T31 = "3.1 ON THE DIFFERENCE BETWEEN THIN AND THICK TAILS"
T32 = "3.2 A (MORE ADVANCED) CATEGORIZATION AND ITS CONSEQUENCES"
T33 = "3.3 THE MAIN CONSEQUENCES AND HOW THEY LINK TO THE BOOK"


def _sem_brancos(s):
    return "".join(s.split())


class TesteTituloAcimaDoCorte(unittest.TestCase):
    """Rodada corpus A (PO, 2026-10-05): título de nível acima do corte FECHA o bloco corrente; o texto depois
    dele é tópico próprio; título sem corpo vira prefixo verbatim do próximo bloco."""

    def recortar(self, texto, nivel):
        chunks, _ = REC.recortar_texto(texto, nivel, 0, 32000, 120000)
        return chunks

    def assertVerbatim(self, texto, chunks):
        """Cada bloco é fatia do original, na ordem, e só há espaço em branco entre eles (regra de borda)."""
        pos = 0
        for c in chunks:
            i = texto.find(c["texto"], pos)
            self.assertGreaterEqual(i, 0, c["topico"])
            self.assertEqual(texto[pos:i].strip(), "", (c["topico"], texto[pos:i]))
            pos = i + len(c["texto"])
        self.assertEqual(texto[pos:].strip(), "")
        self.assertEqual(_sem_brancos("".join(c["texto"] for c in chunks)), _sem_brancos(texto))

    def test_caso_real_scft_nivel_3(self):
        chunks = self.recortar(SCFT, 3)
        self.assertEqual([c["topico"] for c in chunks],
                         ["2.2.30 Metaprobability", "2.2.31 Dynamic hedging", T3, T31, T32, T33])
        por = {c["topico"]: c["texto"] for c in chunks}
        hedging = por["2.2.31 Dynamic hedging"]
        self.assertTrue(hedging.endswith("Part I"), hedging[-80:])          # o texto antes do título fica
        for intruso in ("# FAT TAILS", "# 3 A NON", "## 3.1", "Mediocristan", "Abyssus"):
            self.assertNotIn(intruso, hedging)
        # `# FAT TAILS…` não tem corpo: entra como prefixo verbatim do bloco do `# 3 …`
        self.assertTrue(por[T3].startswith("# FAT TAILS AND THEIR EFFECTS, AN INTRODUCTION\n\n# 3 A NON"))
        self.assertIn("Abyssus abyssum invocat", por[T3]); self.assertNotIn("## 3.1", por[T3])
        self.assertTrue(por[T31].startswith("## 3.1 ON THE DIFFERENCE")); self.assertIn("Mediocristan", por[T31])
        self.assertTrue(por[T32].startswith("## 3.2 A (MORE")); self.assertNotIn("### 3.3", por[T32])
        self.assertEqual(por[T33], "### 3.3 THE MAIN CONSEQUENCES AND HOW THEY LINK TO THE BOOK\n\nfim")
        self.assertVerbatim(SCFT, chunks)

    def test_pai_e_o_titulo_de_nivel_mais_alto_acima(self):
        blocos = []
        orig = REC.desambiguar_topicos
        REC.desambiguar_topicos = lambda bs: (blocos.extend(bs), orig(bs))[1]
        try:
            self.recortar(SCFT, 3)
        finally:
            REC.desambiguar_topicos = orig
        pais = {t: pai for t, pai, _ in blocos}
        self.assertIsNone(pais[T3])              # `# FAT TAILS` é do mesmo nível: não é pai
        self.assertEqual(pais[T31], T3)
        self.assertEqual(pais[T32], T3)
        self.assertEqual(pais[T33], T32)

    def test_caso_real_scft_nivel_2(self):
        chunks = self.recortar(SCFT, 2)
        self.assertEqual([c["topico"] for c in chunks], ["(abertura)", T3, T31, T32])
        por = {c["topico"]: c["texto"] for c in chunks}
        self.assertTrue(por["(abertura)"].endswith("Part I"))
        self.assertTrue(por[T3].startswith("# FAT TAILS AND THEIR EFFECTS"))
        self.assertIn("### 3.3 THE MAIN", por[T32])                     # mais fundo que o corte: corpo
        self.assertVerbatim(SCFT, chunks)

    def test_nivel_2_titulo_sem_corpo_vira_prefixo(self):
        texto = "intro\n\n# Parte\n\n## Cap. 1\n\nc1\n\n# Outra parte\n\n## Cap. 2\n\nc2\n"
        chunks = self.recortar(texto, 2)
        self.assertEqual([c["topico"] for c in chunks], ["(abertura)", "Cap. 1", "Cap. 2"])
        self.assertEqual([c["texto"] for c in chunks],
                         ["intro", "# Parte\n\n## Cap. 1\n\nc1", "# Outra parte\n\n## Cap. 2\n\nc2"])
        self.assertVerbatim(texto, chunks)

    def test_titulos_sem_corpo_encadeados_e_no_fim(self):
        texto = "## A\n\na\n\n# P\n# Q\n\n## B\n\nb\n\n# Fim\n"
        chunks = self.recortar(texto, 2)
        self.assertEqual([c["topico"] for c in chunks], ["A", "B", "Fim"])
        self.assertEqual(chunks[1]["texto"], "# P\n# Q\n\n## B\n\nb")
        self.assertEqual(chunks[2]["texto"], "# Fim")                    # nunca se perde
        self.assertVerbatim(texto, chunks)

    def test_cabecalho_das_partes_e_o_titulo_do_topico_nao_o_prefixo(self):
        texto = "# Parte\n\n## Tabela\n" + "".join("| %d |\n" % i for i in range(200))
        chunks, _ = REC.recortar_texto(texto, 2, 300, 32000, 120000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(chunks[0]["texto"].startswith("# Parte"))
        self.assertEqual({c["cabecalho"] for c in chunks[1:]}, {"## Tabela"})

    def test_titulo_acima_com_corpo_e_topico_proprio(self):
        texto = "# T\n\nabertura\n\n## A\n\ncurto\n"
        chunks = self.recortar(texto, 2)
        self.assertEqual([(c["topico"], c["texto"]) for c in chunks], [("T", "# T\n\nabertura"), ("A", "## A\n\ncurto")])


if __name__ == "__main__":
    unittest.main()
