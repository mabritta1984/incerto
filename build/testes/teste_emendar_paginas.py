# -*- coding: utf-8 -*-
"""Emenda de páginas reconvertidas ("reparo", decisão do PO de 05/10): `emendar_paginas.py` troca a nota
`[fallback] páginas A-B` do `.md` de uma onda pelo `.md` de uma onda de reparo (sub-PDF só daquelas
páginas), copia os assets com prefixo, grava o sidecar `<documento>.reparos.json` e nunca toca o
`report.json` do mineiro; o portão `conferir_onda.py` lê o sidecar. Fixtures montadas à mão no formato
dos `.report.json` reais da onda 2026-10-TALEB-1 (Dynamic_Hedging.pdf, pp. 321–340 perdidas por HTTP 429).
Nada de rede, GCS, Neo4j ou Wolfram."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from _carga import carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
sys.modules.setdefault("limite_sympy", carregar("skills/lavra/scripts/limite_sympy.py"))
sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
co = carregar("skills/lavra/scripts/conferir_onda.py")
sys.modules.setdefault("conferir_onda", co)
ep = carregar("skills/lavra/scripts/emendar_paginas.py")
rt = sys.modules["recortar_trechos"]
ee = sys.modules["extrair_equacoes"]

ONDA, REPARO = "2026-10-TALEB-1", "2026-10-TALEB-1-reparo-DH"
DOC, DOC_R = "Dynamic_Hedging.pdf", "Dynamic_Hedging_p321-340.pdf"
ERRO_429 = ("parse: páginas 321-340: gemini-3.8-flash: HTTP 429 — Resource exhausted. Please try again later. "
            "Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.")
ERRO_PIC = "pic_35: classificação falhou: gemini-3.8-flash: HTTP 429 — Resource exhausted."
NOTA = ("> ⚠️ [fallback] páginas 321-340 não convertida(s) pelo modelo; o erro está em `erros` no relatório "
        "do documento.")
FALLBACK_MERMAID = ("> ⚠️ [fallback] diagrama não convertido; abaixo, imagem original e descrição.\n\n"
                    "![](Dynamic_Hedging_p321-340.pdf.assets/fig_1.png)\n\nUma treliça binomial.")

MD_ALVO = ("# Dynamic Hedging\n\n## 18 Binaries: European and American\n\n"
           "A particularity of American double bets.\n\n"
           "![](Dynamic_Hedging.pdf.assets/fig_0.png)\n\nUm gráfico em U.\n\n"
           "$$\nV = S - K\n$$\n\nFigure 18.14 American bet.\n\n" + NOTA + "\n\n"
           "### Option Wizard: The Skew Revisited\n\n$$\nx = y + z\n$$\n")
MD_REPARO = ("## 19 Barrier Options\n\nKnock-out options die at the barrier.\n\n"
             "![](Dynamic_Hedging_p321-340.pdf.assets/fig_0.png)\n\nUma curva de payoff.\n\n"
             "$$\nw = a b\n$$\n\n" + FALLBACK_MERMAID + "\n")


def _eq(**kw):
    e = dict.fromkeys(co.CAMPOS_EQ, 0)
    e["validador"] = None
    e.update(kw)
    return e


def _item(iid, kind, route, final, approved=True, fallback=False, feedback=""):
    return {"item_id": iid, "kind": kind, "route": route, "final": final, "approved": approved,
            "fallback": fallback, "metrics": {}, "provider": None, "model": None, "model_version": None,
            "tokens": {}, "cost_usd": None,
            "attempts": [{"n": 1, "output": "", "score": None, "objective_ok": approved, "feedback": feedback,
                          "seconds": 1.0, "metrics": {}}] if route != "passthrough" else []}


def _relatorio(source, items, equacoes, paginas_falhas=0, erros=()):
    return {"source": source, "generated_at": "2026-10-05T02:48:37.697539+00:00", "items": items,
            "summary": {"itens": len(items), "aprovados": sum(i["approved"] for i in items),
                        "fallbacks": sum(i["fallback"] for i in items), "segundos": 10.0,
                        "segundos_parede": 20.0, "tokens": {"prompt": 10, "output": 5, "total": 15},
                        "model_versions": ["gemini-3.8-flash"], "equacoes": equacoes, "erros": list(erros),
                        "parse": {"engine": "gemini_pdf", "provider": "gemini", "model": "gemini-3.8-flash",
                                  "paginas_falhas": paginas_falhas, "paginas_sem_texto": 0, "avisos": []}}}


def relatorio_alvo():
    items = [_item("txt_0", "text", "passthrough", "# Dynamic Hedging"),
             _item("pic_7", "picture", "describe", "![](Dynamic_Hedging.pdf.assets/fig_0.png)\n\nUm gráfico em U."),
             _item("eq_0", "formula", "equation", "$$\nV = S - K\n$$"),
             _item("eq_1", "formula", "equation", "$$\nx = y + z\n$$")]
    return _relatorio("/mnt/corpus/originais/TALEB/Dynamic_Hedging.pdf", items,
                      _eq(equacoes_detectadas=2, via_parse=2, validador="katex"), 20, [ERRO_429, ERRO_PIC])


def relatorio_reparo():
    items = [_item("txt_0", "text", "passthrough", "## 19 Barrier Options\n\nKnock-out options die at the barrier."),
             _item("pic_0", "picture", "describe",
                   "![](Dynamic_Hedging_p321-340.pdf.assets/fig_0.png)\n\nUma curva de payoff."),
             _item("eq_0", "formula", "equation", "$$\nw = a b\n$$"),
             _item("pic_1", "picture", "mermaid", FALLBACK_MERMAID, approved=False, fallback=True,
                   feedback="gemini-2.5-pro devolveu resposta incompleta (finishReason=MAX_TOKENS)")]
    return _relatorio("/mnt/corpus/reparo/Dynamic_Hedging_p321-340.pdf", items,
                      _eq(equacoes_detectadas=1, via_parse=1, validador="katex"))


def _gravar(caminho, conteudo):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    modo = "wb" if isinstance(conteudo, bytes) else "w"
    with (open(caminho, modo) if modo == "wb" else open(caminho, modo, encoding="utf-8", newline="\n")) as f:
        f.write(conteudo)


def _json(caminho, obj):
    _gravar(caminho, json.dumps(obj, ensure_ascii=False, indent=1))


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def _sha(caminho):
    with open(caminho, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _foto(raiz):
    """{caminho relativo: sha256} de tudo sob a raiz — para provar que nada foi gravado."""
    r = {}
    for base, _, arqs in os.walk(raiz):
        for a in arqs:
            c = os.path.join(base, a)
            r[os.path.relpath(c, raiz)] = _sha(c)
    return r


class _Corpus(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="incerto-reparo-")
        self.ext = os.path.join(self.raiz, "extraidos", ONDA)
        self.rep = os.path.join(self.raiz, "extraidos", REPARO)
        self.md = os.path.join(self.ext, DOC + ".md")
        self.rel = os.path.join(self.ext, DOC + ".report.json")
        self.sidecar = os.path.join(self.ext, DOC + ".reparos.json")
        _gravar(self.md, MD_ALVO)
        _json(self.rel, relatorio_alvo())
        _gravar(os.path.join(self.ext, DOC + ".assets", "fig_0.png"), b"\x89PNG alvo")
        self.md_r = os.path.join(self.rep, DOC_R + ".md")
        self.rel_r = os.path.join(self.rep, DOC_R + ".report.json")
        _gravar(self.md_r, MD_REPARO)
        _json(self.rel_r, relatorio_reparo())
        _gravar(os.path.join(self.rep, DOC_R + ".assets", "fig_0.png"), b"\x89PNG reparo 0")
        _gravar(os.path.join(self.rep, DOC_R + ".assets", "fig_1.png"), b"\x89PNG reparo 1")

    def tearDown(self):
        shutil.rmtree(self.raiz)

    def emendar(self, paginas="321-340", documento_reparo=DOC_R):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            cod = ep.main(["--raiz", self.raiz, "--onda", ONDA, "--documento", DOC, "--onda-reparo", REPARO,
                           "--documento-reparo", documento_reparo, "--paginas", paginas])
        return cod, err.getvalue()

    def recusa(self, trecho, **kw):
        antes = _foto(self.raiz)
        cod, err = self.emendar(**kw)
        self.assertNotEqual(cod, 0)
        self.assertIn(trecho, err)
        self.assertEqual(_foto(self.raiz), antes, "a recusa gravou algo")

    def mudar_relatorio(self, caminho, fn):
        with open(caminho, encoding="utf-8") as f:
            rel = json.load(f)
        fn(rel)
        _json(caminho, rel)

    def sidecar_lido(self):
        with open(self.sidecar, encoding="utf-8") as f:
            return json.load(f)


class TesteEmendaFeliz(_Corpus):
    def setUp(self):
        super().setUp()
        self.rel_antes = _sha(self.rel)
        self.reparo_antes = _foto(self.rep)
        self.md_antes = _sha(self.md)
        self.cod, self.err = self.emendar()
        self.texto = _ler(self.md)

    def test_sai_0(self):
        self.assertEqual(self.cod, 0, self.err)

    def test_nota_trocada_pelo_reparo_entre_marcadores(self):
        self.assertNotIn("[fallback] páginas 321-340", self.texto)
        abre = "<!-- reparo: páginas 321-340, onda %s, relatório sha256 %s -->" % (REPARO, _sha(self.rel_r))
        fecha = "<!-- fim do reparo: páginas 321-340 -->"
        self.assertIn(abre, self.texto)
        self.assertIn(fecha, self.texto)
        i, j = self.texto.index(abre), self.texto.index(fecha)
        self.assertIn("Knock-out options die at the barrier.", self.texto[i:j])
        self.assertLess(self.texto.index("Figure 18.14 American bet."), i)
        self.assertLess(j, self.texto.index("### Option Wizard"))
        self.assertEqual(self.texto.count(abre), 1)

    def test_texto_fora_da_emenda_intacto(self):
        abre = self.texto.index("<!-- reparo:")
        fim = self.texto.index("-->", self.texto.index("<!-- fim do reparo")) + 3
        self.assertEqual(self.texto[:abre] + NOTA + self.texto[fim:], MD_ALVO)

    def test_assets_copiados_com_prefixo_e_referencias_reescritas(self):
        assets = os.path.join(self.ext, DOC + ".assets")
        self.assertEqual(sorted(os.listdir(assets)), ["fig_0.png", "reparo-p321-340-fig_0.png",
                                                      "reparo-p321-340-fig_1.png"])
        with open(os.path.join(assets, "reparo-p321-340-fig_1.png"), "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG reparo 1")
        with open(os.path.join(assets, "fig_0.png"), "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG alvo")
        self.assertIn("![](Dynamic_Hedging.pdf.assets/reparo-p321-340-fig_0.png)", self.texto)
        self.assertIn("![](Dynamic_Hedging.pdf.assets/reparo-p321-340-fig_1.png)", self.texto)
        self.assertNotIn(DOC_R + ".assets", self.texto)

    def test_report_do_mineiro_e_onda_de_reparo_intocados(self):
        self.assertEqual(_sha(self.rel), self.rel_antes)
        self.assertEqual(_foto(self.rep), self.reparo_antes)

    def test_sidecar(self):
        s = self.sidecar_lido()
        self.assertEqual(len(s), 1)
        r = s[0]
        self.assertEqual((r["paginas"], r["pagina_inicial"], r["pagina_final"]), ("321-340", 321, 340))
        self.assertEqual((r["onda_reparo"], r["documento_reparo"]), (REPARO, DOC_R))
        self.assertEqual(r["sha256_report_reparo"], _sha(self.rel_r))
        self.assertEqual(r["sha256_md_reparo"], _sha(self.md_r))
        self.assertEqual(r["sha256_md_antes"], self.md_antes)
        self.assertEqual(r["sha256_md_depois"], _sha(self.md))
        self.assertEqual(r["erros_resolvidos"], [ERRO_429])
        self.assertEqual(r["equacoes"], relatorio_reparo()["summary"]["equacoes"])
        self.assertEqual([i["item_id"] for i in r["items"]],
                         ["reparo-p321-340-txt_0", "reparo-p321-340-pic_0", "reparo-p321-340-eq_0",
                          "reparo-p321-340-pic_1"])
        fb = r["items"][3]
        self.assertTrue(fb["fallback"])
        self.assertIn("Dynamic_Hedging.pdf.assets/reparo-p321-340-fig_1.png", fb["final"])
        self.assertIn(fb["final"].strip(), self.texto)
        self.assertEqual(r["assets"], [
            {"origem": "fig_0.png", "destino": "reparo-p321-340-fig_0.png",
             "sha256": hashlib.sha256(b"\x89PNG reparo 0").hexdigest()},
            {"origem": "fig_1.png", "destino": "reparo-p321-340-fig_1.png",
             "sha256": hashlib.sha256(b"\x89PNG reparo 1").hexdigest()}])

    def test_sidecar_deterministico(self):
        texto = _ler(self.sidecar)
        self.assertTrue(texto.endswith("\n"))
        self.assertEqual(texto, json.dumps(json.loads(texto), sort_keys=True, ensure_ascii=False, indent=2) + "\n")
        self.assertNotIn("generated_at", texto)

    def test_reaplicacao_recusada(self):
        self.recusa("já existe reparo")


class TesteRecusas(_Corpus):
    def test_nota_ausente(self):
        _gravar(self.md, MD_ALVO.replace(NOTA + "\n\n", ""))
        self.recusa("0 notas [fallback]")

    def test_nota_duplicada(self):
        _gravar(self.md, MD_ALVO.replace(NOTA, NOTA + "\n\n" + NOTA))
        self.recusa("2 notas [fallback]")

    def test_nota_de_outra_faixa_nao_serve(self):
        self.recusa("0 notas [fallback] para páginas 321-339", paginas="321-339")

    def test_reparo_com_paginas_falhas(self):
        self.mudar_relatorio(self.rel_r, lambda r: r["summary"]["parse"].update(paginas_falhas=1))
        self.recusa("paginas_falhas")

    def test_reparo_com_perda_silenciosa(self):
        def perder(r):
            r["items"][1]["approved"] = False
        self.mudar_relatorio(self.rel_r, perder)
        self.recusa("perda silenciosa")

    def test_reparo_com_fallback_fora_do_md(self):
        _gravar(self.md_r, MD_REPARO.replace(FALLBACK_MERMAID, "texto qualquer"))
        self.recusa("perda silenciosa")

    def test_numero_de_paginas_diferente_quando_disponivel(self):
        self.mudar_relatorio(self.rel_r, lambda r: r["summary"]["parse"].update(paginas=19))
        self.recusa("19 página(s)")

    def test_numero_de_paginas_igual_passa(self):
        self.mudar_relatorio(self.rel_r, lambda r: r["summary"]["parse"].update(paginas=20))
        self.assertEqual(self.emendar()[0], 0)

    def test_colisao_de_asset(self):
        _gravar(os.path.join(self.ext, DOC + ".assets", "reparo-p321-340-fig_1.png"), b"outro")
        self.recusa("colisão")

    def test_referencia_a_asset_ausente(self):
        os.remove(os.path.join(self.rep, DOC_R + ".assets", "fig_0.png"))
        self.recusa("fig_0.png")

    def test_mais_paginas_que_as_falhas_do_alvo(self):
        self.mudar_relatorio(self.rel, lambda r: r["summary"]["parse"].update(paginas_falhas=5))
        self.recusa("paginas_falhas")

    def test_faixa_invalida(self):
        for p in ("340-321", "0-3", "a-b", "3-"):
            cod, err = self.emendar(paginas=p)
            self.assertEqual(cod, 2, p)

    def test_documento_de_reparo_inexistente(self):
        self.recusa("não encontrado", documento_reparo="Outro.pdf")


class TesteUmaPagina(_Corpus):
    def test_pagina_unica(self):
        nota7 = ("> ⚠️ [fallback] página 7 não convertida(s) pelo modelo; o erro está em `erros` no relatório "
                 "do documento.")
        _gravar(self.md, MD_ALVO.replace(NOTA, nota7))
        self.mudar_relatorio(self.rel, lambda r: r["summary"].update(
            erros=["parse: página 7: o modelo não devolveu blocos para uma página com texto", ERRO_PIC]))
        cod, err = self.emendar(paginas="7")
        self.assertEqual(cod, 0, err)
        texto = _ler(self.md)
        self.assertIn("<!-- reparo: página 7, onda %s," % REPARO, texto)
        self.assertIn("<!-- fim do reparo: página 7 -->", texto)
        self.assertIn("Dynamic_Hedging.pdf.assets/reparo-p7-fig_0.png", texto)
        r = self.sidecar_lido()[0]
        self.assertEqual((r["paginas"], r["erros_resolvidos"]),
                         ("7", ["parse: página 7: o modelo não devolveu blocos para uma página com texto"]))


class TestePortao(_Corpus):
    def docs(self):
        return co.ler_onda(self.ext)

    def doc(self):
        return self.docs()[0]

    def test_sem_sidecar_inalterado(self):
        d = self.doc()
        self.assertEqual(d["veredito"], "apto")
        self.assertEqual([p["rota"] for p in d["perdas"]], ["parse"])
        self.assertIn(ERRO_429, d["perdas"][0]["motivo"])
        r = co.resumir([d])
        self.assertEqual((r["itens"], r["fallbacks"], r["por_rota"]["parse"]["fallbacks"]), (4, 20, 20))
        md = co.relatorio_md(ONDA, [d], r)
        self.assertNotIn("## Reparos", md)
        self.assertNotIn("reparos", co.manifesto(self.raiz, ONDA, [d], r)["documentos"][0])

    def test_com_reparo_apto_e_a_perda_de_paginas_sai(self):
        self.assertEqual(self.emendar()[0], 0)
        d = self.doc()
        self.assertEqual(d["veredito"], "apto", d["motivos"])
        self.assertEqual([(p["item"], p["rota"]) for p in d["perdas"]], [("reparo-p321-340-pic_1", "mermaid")])
        self.assertEqual(d["equacoes_detectadas"], 3)

    def test_contagens_com_reparo(self):
        self.emendar()
        docs = self.docs()
        r = co.resumir(docs)
        self.assertEqual((r["itens"], r["aprovados"], r["fallbacks"]), (8, 7, 1))
        self.assertEqual(r["por_rota"]["parse"]["fallbacks"], 0)
        self.assertEqual(r["por_rota"]["mermaid"], {"itens": 1, "fallbacks": 1, "nao_aprovados": 1})
        self.assertEqual(r["por_rota"]["equation"]["itens"], 3)
        self.assertEqual((r["equacoes"]["equacoes_detectadas"], r["equacoes"]["via_parse"]), (3, 3))
        self.assertEqual((r["equacoes"]["documentos_com_equacao"], r["equacoes"]["documentos_katex"]), (1, 1))
        self.assertEqual(r["equacoes"]["parseaveis_sympy"]["total"], 3)
        md = co.relatorio_md(ONDA, docs, r)
        self.assertIn("| %s | 8 | 3 | katex | 1 | ✔ apto | — |" % DOC, md)

    def test_secao_reparos_no_relatorio_e_no_manifesto(self):
        self.emendar()
        docs = self.docs()
        r = co.resumir(docs)
        md = co.relatorio_md(ONDA, docs, r)
        self.assertIn("## Reparos", md)
        s = self.sidecar_lido()[0]
        self.assertIn("| %s | 321-340 | %s | %s | %s | %s | %s |" % (
            DOC, REPARO, DOC_R, s["sha256_report_reparo"], s["sha256_md_antes"], s["sha256_md_depois"]), md)
        m = co.manifesto(self.raiz, ONDA, docs, r)["documentos"][0]
        self.assertEqual(m["reparos"], {"sha256": _sha(self.sidecar), "paginas": ["321-340"]})

    def test_md_editado_depois_do_reparo_e_inapto(self):
        self.emendar()
        with open(self.md, "a", encoding="utf-8", newline="\n") as f:
            f.write("\nlinha acrescentada à mão\n")
        d = self.doc()
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("md alterado fora do reparo" in m for m in d["motivos"]), d["motivos"])

    def test_item_do_reparo_entra_na_perda_silenciosa(self):
        self.emendar()
        s = self.sidecar_lido()
        s[0]["items"][1]["approved"] = False
        _gravar(self.sidecar, json.dumps(s, ensure_ascii=False))
        d = self.doc()
        self.assertEqual(d["veredito"], "reprovado")
        self.assertIn("perda silenciosa: reparo-p321-340-pic_0 (describe) não aprovado e sem fallback", d["motivos"])

    def test_sidecar_ilegivel_e_inapto(self):
        self.emendar()
        _gravar(self.sidecar, "{não é json")
        d = self.doc()
        self.assertEqual(d["veredito"], "reprovado")
        self.assertTrue(any("reparos.json" in m for m in d["motivos"]), d["motivos"])

    def test_sidecar_com_mais_paginas_que_as_falhas_e_inapto(self):
        self.emendar()
        s = self.sidecar_lido()
        s[0]["pagina_final"] = 400
        _gravar(self.sidecar, json.dumps(s, ensure_ascii=False))
        d = self.doc()
        self.assertEqual(d["veredito"], "reprovado")
        self.assertIn("os reparos cobrem 60 página(s) a mais que summary.parse.paginas_falhas", d["motivos"])
        self.assertEqual(co.resumir([d])["por_rota"]["parse"]["fallbacks"], 0)

    def test_aprovar_copia_sidecar_e_assets_emendados(self):
        self.emendar()
        self.assertEqual(co.aprovar(self.raiz, ONDA, self.docs(), {}), [DOC])
        conf = os.path.join(self.raiz, "conferidos", ONDA)
        self.assertEqual(_sha(os.path.join(conf, DOC + ".reparos.json")), _sha(self.sidecar))
        self.assertEqual(_sha(os.path.join(conf, DOC + ".md")), _sha(self.md))
        self.assertEqual(sorted(os.listdir(os.path.join(conf, DOC + ".assets"))),
                         ["fig_0.png", "reparo-p321-340-fig_0.png", "reparo-p321-340-fig_1.png"])
        self.assertEqual(co.documentos(conf), [DOC])
        self.assertEqual(_sha(os.path.join(conf, DOC + ".report.json")), _sha(self.rel))


class TesteRecorteEExtracao(_Corpus):
    """Os marcadores HTML não viram tópico nem equação; as equações do reparo entram na ordem do `.md`
    emendado, com nome `<documento>#<ordem>` único (sem colidir com as do alvo)."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.emendar()[0], 0)
        self.texto = _ler(self.md)

    def test_recorte_verbatim_sem_topico_de_marcador(self):
        inf = float("inf")
        trechos, _ = rt.recortar_texto(self.texto, 2, 0, inf, inf, inf)
        topicos = [t["topico"] for t in trechos]
        self.assertEqual(topicos, ["(abertura)", "18 Binaries: European and American", "19 Barrier Options"])
        self.assertFalse(any("reparo" in t for t in topicos))
        self.assertIn("<!-- reparo: páginas 321-340", trechos[1]["texto"])
        self.assertIn("<!-- fim do reparo: páginas 321-340 -->", trechos[2]["texto"])

    def test_equacoes_na_ordem_do_md_emendado(self):
        eqs = ee.equacoes_do_documento(self.texto, DOC + ".md")
        self.assertEqual([(e["ordem"], e["latex"], e["topico"]) for e in eqs], [
            (1, "V = S - K", "18 Binaries: European and American"),
            (2, "w = a b", "19 Barrier Options"),
            (3, "x = y + z", "19 Barrier Options")])
        nomes = [ee.candidato(e, ONDA)["nome"] for e in eqs]
        self.assertEqual(len(set(nomes)), 3)


if __name__ == "__main__":
    unittest.main()
