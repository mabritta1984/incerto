# -*- coding: utf-8 -*-
"""Task 11: aprovar_onda.py — o único escritor que promove a `aprovado`, com o gate do fiscal.

O gate (`decidir`) é função pura e é testado aqui sem banco, regra por regra: vermelho nunca promove;
indeterminado só com aceite exato do PO; `DERIVA_DE` exige P2 e P4 verdes e as duas pontas promovíveis;
momento fechado exige a P4 do momento; item sem linha do fiscal fica em staging; decisão de tipo
desconhecido recusa a execução inteira. Os testes de banco real são `@precisa_neo4j` (CI, `neo4j:5`) e
rodam a CLI sobre uma onda cujo `fiscal-<onda>.jsonl` sai do fiscal de verdade."""
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

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
NUC = sys.modules.setdefault("nucleo", carregar("skills/lavra/scripts/nucleo.py"))
EQ = sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
FI = sys.modules.setdefault("fiscal", carregar("skills/lavra/scripts/fiscal.py"))
AO = carregar("skills/lavra/scripts/aprovar_onda.py")

ONDA = "2026-10-T11"
DOC = "Kelly.pdf.md"


def cand(nome, latex, ordem=1, **extra):
    """Candidato no formato de `extrair_equacoes.candidato`, com o `srepr` do parser real."""
    r = EQ.parsear_latex(latex)
    linha = {"nome": nome, "status": "staging", "corpus": PARTICAO, "onda": ONDA, "ordem": ordem, "latex": latex,
             "srepr": r["srepr"], "simbolos": r["simbolos"], "motivo": r["motivo"],
             "variaveis": [{"simbolo": s, "nome": s} for s in r["simbolos"]], "forma": EQ.forma(r),
             "fonte": {"documento": DOC, "topico": "Aposta binária"}}
    linha.update(extra)
    return linha


def eq_fixa(nome, simbolos=("x", "y"), **extra):
    """Candidato sem parser (para o gate puro): o `srepr` é só um texto."""
    linha = {"nome": nome, "status": "staging", "corpus": PARTICAO, "onda": ONDA, "ordem": 1, "latex": "y = x",
             "srepr": "Equality(Symbol('y'), Symbol('x'))", "simbolos": list(simbolos), "motivo": None,
             "variaveis": [{"simbolo": s, "nome": s} for s in simbolos], "forma": "algebrica",
             "fonte": {"documento": DOC, "topico": "T"}}
    linha.update(extra)
    return linha


def p1(eq, veredito="verde"):
    return {"prova": "P1", "alvo": eq, "equacao": eq, "veredito": veredito, "detalhe": "d"}


def p2(mae, filha, veredito="verde", simbolo="x", substituicao=None):
    return {"prova": "P2", "alvo": filha, "mae": mae, "filha": filha, "simbolo": simbolo,
            "substituicao": substituicao or {}, "veredito": veredito, "detalhe": "d"}


def p3(eq, condicao, veredito="verde"):
    return {"prova": "P3", "alvo": eq, "equacao": eq, "condicao": condicao, "veredito": veredito, "detalhe": "d"}


def p4d(mae, filha, veredito="verde"):
    return {"prova": "P4", "alvo": filha, "mae": mae, "filha": filha, "veredito": veredito, "detalhe": "d"}


def p4m(eq, veredito="verde"):
    return {"prova": "P4", "alvo": eq, "equacao": eq, "veredito": veredito, "detalhe": "d"}


def deriv(mae, filha, alvo="x", substituicao=None):
    return {"mae": mae, "filha": filha, "alvo": alvo, "substituicao": substituicao or {}, "passo": "isola"}


def aceite(**chaves):
    return dict({"tipo": "aceitar_indeterminado"}, **chaves)


def por_nome(linhas, chave="nome"):
    return {l[chave]: l for l in linhas}


class TesteGateEquacao(unittest.TestCase):
    def test_p1_verde_promove(self):
        plano = AO.decidir([eq_fixa("a")], [], [], [p1("a")], [])
        eq = plano["equacoes"][0]
        self.assertEqual((eq["status"], eq["pendencias"]), ("aprovado", []))

    def test_sem_linha_do_fiscal_fica_em_staging(self):
        eq = AO.decidir([eq_fixa("a")], [], [], [], [])["equacoes"][0]
        self.assertEqual(eq["status"], "staging")
        self.assertIn("sem prova P1", eq["pendencias"][0])

    def test_perda_declarada_fica_em_staging_com_forma_perda(self):
        e = cand("a", r"\Pr(X > x) = x^{-\alpha}")
        fis = [{k: v for k, v in l.items() if k != "ms"} for l in FI.provas([e], [], [], {})]
        eq = AO.decidir([e], [], [], fis, [aceite(prova="P1", equacao="a")])["equacoes"][0]
        self.assertEqual((eq["forma"], eq["status"], eq["latex"]), ("perda", "staging", e["latex"]))

    def test_p1_vermelho_fica_em_staging(self):
        eq = AO.decidir([eq_fixa("a")], [], [], [p1("a", "vermelho")], [])["equacoes"][0]
        self.assertEqual(eq["status"], "staging")

    def test_toda_p3_da_equacao_tem_de_ser_verde(self):
        vals = [{"equacao": "a", "condicao": "x > 0"}, {"equacao": "a", "condicao": "y > 0"}]
        fis = [p1("a"), p3("a", "x > 0"), p3("a", "y > 0", "vermelho")]
        self.assertEqual(AO.decidir([eq_fixa("a")], [], vals, fis, [])["equacoes"][0]["status"], "staging")
        fis[-1] = p3("a", "y > 0")
        self.assertEqual(AO.decidir([eq_fixa("a")], [], vals, fis, [])["equacoes"][0]["status"], "aprovado")

    def test_validade_sem_p3_bloqueia_a_equacao(self):
        vals = [{"equacao": "a", "condicao": "x > 0"}]
        plano = AO.decidir([eq_fixa("a")], [], vals, [p1("a")], [])
        self.assertEqual(plano["equacoes"][0]["status"], "staging")
        self.assertEqual(plano["valida_sob"][0]["status"], "staging")

    def test_momento_fechado_exige_a_p4_do_momento(self):
        e = eq_fixa("a", momento_fechado={"media": "x"})
        self.assertEqual(AO.decidir([e], [], [], [p1("a")], [])["equacoes"][0]["status"], "staging")
        self.assertEqual(AO.decidir([e], [], [], [p1("a"), p4m("a", "vermelho")], [])["equacoes"][0]["status"],
                         "staging")
        self.assertEqual(AO.decidir([e], [], [], [p1("a"), p4m("a")], [])["equacoes"][0]["status"], "aprovado")

    def test_p4_de_momento_nao_verde_bloqueia_mesmo_sem_momento_declarado(self):
        self.assertEqual(AO.decidir([eq_fixa("a")], [], [], [p1("a"), p4m("a", "vermelho")], [])
                         ["equacoes"][0]["status"], "staging")


    def test_equacao_que_aplica_e_sem_momento_fechado_nao_e_aprovada(self):
        # C1: `\mathbb{E}[X] = αL/(α-1)` só com P1 verde saía aprovada — o momento sem prova nenhuma
        e = cand("pareto#1", r"\mathbb{E}[X] = \frac{\alpha L}{\alpha-1}")
        fis = [{k: v for k, v in l.items() if k != "ms"} for l in FI.provas([e], [], [], {})]
        eq = AO.decidir([e], [], [], fis, [])["equacoes"][0]
        self.assertEqual(eq["status"], "staging")
        self.assertTrue(any("aplica E/Var sem momento_fechado declarado" in p for p in eq["pendencias"]),
                        eq["pendencias"])
        # fiscal sem a linha (antigo ou forjado): a P4 tem de existir, como a do momento declarado
        eq = AO.decidir([e], [], [], [p1("pareto#1")], [])["equacoes"][0]
        self.assertEqual(eq["status"], "staging")
        self.assertIn("sem prova P4 do momento fechado", " ".join(eq["pendencias"]))

    def test_plano_imprime_latex_e_srepr_de_cada_item(self):
        e = cand("pareto#1", r"\mathbb{E}[X] = \frac{\alpha L}{\alpha-1}")
        m, f = eq_fixa("m"), eq_fixa("f", latex="x = y", srepr="Equality(Symbol('x'), Symbol('y'))")
        plano = AO.decidir([e, m, f], [deriv("m", "f")], [{"equacao": "m", "condicao": "x > 0"}],
                           [p1("pareto#1"), p1("m"), p1("f"), p3("m", "x > 0")], [])
        texto = "\n".join(AO.linhas_do_plano(plano))
        for linha in (e["latex"], e["srepr"], "x = y", "Equality(Symbol('x'), Symbol('y'))", "y = x",
                      "Equality(Symbol('y'), Symbol('x'))"):
            self.assertIn(linha, texto)
        blocos = texto.split("\n")
        for item in ("pareto#1", "f → m", "m / x > 0 → x"):
            i = [n for n, l in enumerate(blocos) if l.strip().endswith(item) or (" %s" % item) in l][0]
            vizinhas = "\n".join(blocos[i:i + 6])
            self.assertIn("LaTeX:", vizinhas, item); self.assertIn("srepr:", vizinhas, item)


class TesteGateDerivacao(unittest.TestCase):
    def setUp(self):
        self.eqs = [eq_fixa("m"), eq_fixa("f")]
        self.base = [p1("m"), p1("f")]

    def aresta(self, fiscal, decisoes=(), derivs=None):
        plano = AO.decidir(self.eqs, derivs or [deriv("m", "f")], [], self.base + fiscal, list(decisoes))
        self.assertEqual(len(plano["deriva_de"]), 1)
        return plano["deriva_de"][0]

    def test_p2_e_p4_verdes_promovem_com_as_duas_vias(self):
        d = self.aresta([p2("m", "f"), p4d("m", "f")])
        self.assertEqual(d["status"], "aprovado")
        self.assertEqual(d["verificado_por"], ["sympy@1.14.0", "wolfram"])

    def test_sem_p4_nao_promove(self):
        d = self.aresta([p2("m", "f")])
        self.assertEqual(d["status"], "staging")
        self.assertEqual(d["verificado_por"], [])
        self.assertTrue(any("sem prova P4" in p for p in d["pendencias"]))

    def test_sem_p2_nao_promove(self):
        self.assertEqual(self.aresta([p4d("m", "f")])["status"], "staging")

    def test_p2_de_outra_substituicao_nao_conta(self):
        d = self.aresta([p2("m", "f", substituicao={"b": "1"}), p4d("m", "f")])
        self.assertEqual(d["status"], "staging")

    def test_vermelho_nunca_promove_nem_com_aceite(self):
        dec = [aceite(prova="P2", mae="m", filha="f", simbolo="x", substituicao={}),
               aceite(prova="P4", mae="m", filha="f")]
        d = self.aresta([p2("m", "f", "vermelho"), p4d("m", "f", "vermelho")], dec)
        self.assertEqual(d["status"], "staging")

    def test_indeterminado_so_com_aceite_exato_de_cada_linha(self):
        fis = [p2("m", "f", "indeterminado"), p4d("m", "f", "indeterminado")]
        self.assertEqual(self.aresta(fis)["status"], "staging")
        so_p2 = [aceite(prova="P2", mae="m", filha="f", simbolo="x", substituicao={})]
        self.assertEqual(self.aresta(fis, so_p2)["status"], "staging")
        outra_subst = [aceite(prova="P2", mae="m", filha="f", simbolo="x", substituicao={"b": "1"}),
                       aceite(prova="P4", mae="m", filha="f")]
        self.assertEqual(self.aresta(fis, outra_subst)["status"], "staging")
        os_dois = so_p2 + [aceite(prova="P4", mae="m", filha="f")]
        d = self.aresta(fis, os_dois)
        self.assertEqual((d["status"], d["aceites_po"]), ("aprovado", ["P2", "P4"]))

    def test_verificado_por_so_lista_as_vias_verdes(self):
        # I3: aceite do PO não é verificação — a via aceita vai em `aceites_po`, nunca em `verificado_por`
        fis = [p2("m", "f", "indeterminado"), p4d("m", "f", "indeterminado")]
        os_dois = [aceite(prova="P2", mae="m", filha="f", simbolo="x", substituicao={}),
                   aceite(prova="P4", mae="m", filha="f")]
        d = self.aresta(fis, os_dois)
        self.assertEqual((d["status"], d["verificado_por"], d["aceites_po"]), ("aprovado", [], ["P2", "P4"]))
        d = self.aresta([p2("m", "f"), p4d("m", "f", "indeterminado")], os_dois[1:])
        self.assertEqual((d["status"], d["verificado_por"], d["aceites_po"]), ("aprovado", ["sympy@1.14.0"], ["P4"]))
        d = self.aresta([p2("m", "f", "indeterminado"), p4d("m", "f")], os_dois[:1])
        self.assertEqual((d["status"], d["verificado_por"], d["aceites_po"]), ("aprovado", ["wolfram"], ["P2"]))
        d = self.aresta([p2("m", "f"), p4d("m", "f")])
        self.assertEqual((d["verificado_por"], d["aceites_po"]), (["sympy@1.14.0", "wolfram"], []))

    def test_aceite_sem_todas_as_chaves_ou_com_curinga_e_recusado(self):
        for dec in (aceite(prova="P2", mae="m", filha="f"),                       # sem simbolo/substituicao
                    aceite(prova="P2", mae="m", filha="f", simbolo=None, substituicao={}),
                    aceite(prova="P2", mae="m", filha="f", simbolo="*", substituicao={}),
                    aceite(prova="P2", mae="m", filha="f", simbolo="x", substituicao={}, extra=1),
                    aceite(prova="P9", equacao="m"),
                    aceite(mae="m", filha="f")):
            with self.assertRaises(ValueError, msg=dec):
                AO.decidir(self.eqs, [deriv("m", "f")], [], self.base, [dec])

    def test_ponta_em_staging_segura_a_aresta(self):
        self.base = [p1("m", "vermelho"), p1("f")]
        d = self.aresta([p2("m", "f"), p4d("m", "f")])
        self.assertEqual(d["status"], "staging")
        self.assertTrue(any("m" in p and "staging" in p for p in d["pendencias"]))

    def test_derivacao_de_equacao_desconhecida_ou_repetida_e_recusada(self):
        with self.assertRaises(ValueError):
            AO.decidir(self.eqs, [deriv("m", "zz")], [], self.base, [])
        with self.assertRaises(ValueError):
            AO.decidir(self.eqs, [deriv("m", "f"), deriv("m", "f", substituicao={"b": "1"})], [], self.base, [])


class TesteDecisoes(unittest.TestCase):
    def test_tipo_desconhecido_recusa_tudo(self):
        with self.assertRaises(ValueError) as c:
            AO.decidir([eq_fixa("a")], [], [], [p1("a")], [{"tipo": "promover_tudo"}])
        self.assertIn("promover_tudo", str(c.exception))

    def test_renomear_variavel(self):
        dec = [{"tipo": "renomear_variavel", "equacao": "a", "simbolo": "x", "nome": "fracao_apostada"}]
        plano = AO.decidir([eq_fixa("a")], [], [], [p1("a")], dec)
        self.assertEqual(sorted(v["nome"] for v in plano["variaveis"]), ["fracao_apostada", "y"])
        usa = por_nome(plano["usa"], "variavel")
        self.assertEqual(usa["fracao_apostada"]["simbolos"], ["x"])
        self.assertEqual(usa["y"]["papel"], "definida")          # `Equality(Symbol('y'), …)`: y é o lado esquerdo
        self.assertEqual([(d["variavel"], d["equacao"]) for d in plano["definida_por"]], [("y", "a")])
        with self.assertRaises(ValueError):
            AO.decidir([eq_fixa("a")], [], [], [p1("a")],
                       [{"tipo": "renomear_variavel", "equacao": "a", "simbolo": "z", "nome": "n"}])

    FONTE = {"documento": DOC, "topico": "T"}

    def conceito(self, **extra):
        return dict({"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno",
                     "definicao": "perda irreversível", "sinonimos": ["absorção"], "fonte": self.FONTE}, **extra)

    def heuristica(self, sustenta):
        return {"tipo": "heuristica", "nome": "nunca arriscar a ruína", "enunciado": "e", "condicao": "c",
                "fonte": self.FONTE, "sustenta": sustenta}

    def test_conceito_e_heuristica_sustentam_com_o_status_do_alvo(self):
        eqs = [eq_fixa("a"), eq_fixa("b")]
        plano = AO.decidir(eqs, [], [], [p1("a")], [self.conceito(), self.heuristica(["ruina", "a", "b"])])
        c = plano["conceitos"][0]
        self.assertEqual((c["nome"], c["tipo"], c["status"]), ("ruina", "fenomeno", "aprovado"))
        self.assertEqual(plano["heuristicas"][0]["status"], "aprovado")
        sus = {(s["alvo"], s["rotulo"]): s["status"] for s in plano["sustenta"]}
        self.assertEqual(sus, {("ruina", "Conceito"): "aprovado", ("a", "Equacao"): "aprovado",
                               ("b", "Equacao"): "staging"})

    def test_conceito_ou_heuristica_malformados_sao_recusados(self):
        for dec in (self.conceito(tipo_conceito="opiniao"), self.conceito(fonte={"documento": DOC}),
                    self.conceito(sinonimos="absorção"), self.conceito(extra=1),
                    self.heuristica(["inexistente"]), self.heuristica("a")):
            with self.assertRaises(ValueError, msg=dec):
                AO.decidir([eq_fixa("a")], [], [], [p1("a")], [dec])

    def test_momento_decidido_tem_de_estar_aplicado(self):
        dec = [{"tipo": "momento_fechado", "equacao": "a", "momento_fechado": {"media": "x"}}]
        with self.assertRaises(ValueError) as c:
            AO.decidir([eq_fixa("a")], [], [], [p1("a")], dec)
        self.assertIn("--aplicar-momentos", str(c.exception))
        e = eq_fixa("a", momento_fechado={"media": "x"})
        self.assertEqual(AO.decidir([e], [], [], [p1("a"), p4m("a")], dec)["equacoes"][0]["status"], "aprovado")


class TesteRotular(unittest.TestCase):
    """I4: `rotular_equacao` dá à equação o rótulo estável (`kappa`, `hill`, …) com que o relatório e o MCP a
    acham; rótulo repetido no plano ou já em outra :Equacao do corpus recusa antes de qualquer escrita."""

    def rot(self, equacao, rotulo, **extra):
        return dict({"tipo": "rotular_equacao", "equacao": equacao, "rotulo": rotulo}, **extra)

    def test_rotulo_vai_para_a_equacao_do_plano(self):
        plano = AO.decidir([eq_fixa("a"), eq_fixa("b")], [], [], [p1("a"), p1("b")], [self.rot("a", "kappa")])
        rotulos = {e["nome"]: e["rotulo"] for e in plano["equacoes"]}
        self.assertEqual(rotulos, {"a": "kappa", "b": None})
        self.assertIn("e.rotulo = l.rotulo", AO.CYPHER_EQUACOES)
        self.assertIn("rotular_equacao", AO.TIPOS_DECISAO)

    def test_rotulo_malformado_ou_repetido_e_recusado(self):
        eqs, fis = [eq_fixa("a"), eq_fixa("b")], [p1("a"), p1("b")]
        for decs in ([self.rot("a", "Kappa")], [self.rot("a", "1kappa")], [self.rot("a", "ka-ppa")],
                     [self.rot("a", "")], [self.rot("a", "kappa", extra=1)], [{"tipo": "rotular_equacao", "equacao": "a"}],
                     [self.rot("zz", "kappa")],                                         # equação fora da onda
                     [self.rot("a", "kappa"), self.rot("b", "kappa")],                  # um rótulo, duas equações
                     [self.rot("a", "kappa"), self.rot("a", "hill")]):                  # uma equação, dois rótulos
            with self.assertRaises(ValueError, msg=decs):
                AO.decidir(eqs, [], [], fis, decs)

    def test_rotulo_ja_em_outra_equacao_do_corpus_recusa_antes_de_escrever(self):
        plano = AO.decidir([eq_fixa("a"), eq_fixa("b")], [], [], [p1("a"), p1("b")], [self.rot("a", "kappa")])
        chamadas = []

        def falso(cred, db, cypher, par):
            chamadas.append(cypher)
            if cypher == AO.CYPHER_ROTULOS_EM_USO:
                self.assertEqual(sorted(par["nomes"]), ["a", "b"])
                self.assertEqual(par["linhas"], [{"rotulo": "kappa", "nome": "a"}])
                return [["kappa", "Outro.pdf.md#4"]]
            return []
        with mock.patch.object(AO.nucleo, "query_com_retentativa", side_effect=falso):
            with self.assertRaises(ValueError) as c:
                AO.gravar({}, "db", plano, PARTICAO, ONDA, saida=lambda *_: None)
        self.assertIn("kappa", str(c.exception)); self.assertIn("Outro.pdf.md#4", str(c.exception))
        escritas = [q for q in chamadas if any(w in q for w in ("MERGE", "SET", "DELETE"))]
        self.assertEqual(escritas, [])


class TestePlano(unittest.TestCase):
    def test_tudo_no_plano_leva_status_e_fonte(self):
        fonte = {"documento": "Outro.pdf.md", "topico": "T"}
        dec = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d", "sinonimos": [],
                "fonte": fonte},
               {"tipo": "heuristica", "nome": "h", "enunciado": "e", "condicao": "c", "fonte": fonte,
                "sustenta": ["ruina", "f"]}]
        plano = AO.decidir([eq_fixa("m"), eq_fixa("f")], [deriv("m", "f")], [{"equacao": "m", "condicao": "x > 0"}],
                           [p1("m"), p1("f"), p3("m", "x > 0")], dec)
        self.assertEqual(sorted(d["nome"] for d in plano["documentos"]), ["Kelly.pdf.md", "Outro.pdf.md"])
        for tipo, linhas in plano.items():
            if tipo == "avisos":
                continue
            self.assertTrue(linhas, tipo)
            for l in linhas:
                self.assertIn(l["status"], ("aprovado", "staging"), (tipo, l))
                self.assertEqual(sorted(json.loads(l["fonte"])), ["documento", "topico"], (tipo, l))

    def test_valida_sob_aponta_as_variaveis_da_condicao(self):
        dec = [{"tipo": "renomear_variavel", "equacao": "m", "simbolo": "x", "nome": "alfa"}]
        plano = AO.decidir([eq_fixa("m")], [], [{"equacao": "m", "condicao": "x > 0 and y < 1"}],
                           [p1("m"), p3("m", "x > 0 and y < 1")], dec)
        self.assertEqual(sorted(v["variavel"] for v in plano["valida_sob"]), ["alfa", "y"])
        self.assertEqual({v["status"] for v in plano["valida_sob"]}, {"aprovado"})
        self.assertEqual(plano["equacoes"][0]["faixa_validade"], ["x > 0 and y < 1"])


def escrever_jsonl(caminho, linhas):
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        for l in linhas:
            f.write(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n")


def ler_jsonl(caminho):
    with io.open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


MAE_KELLY = r"\frac{p b}{1 + b f} - \frac{1 - p}{1 - f} = 0"
FILHA_KELLY = r"f = p - \frac{1 - p}{b}"
FILHA_ERRADA = r"f = p - (1 - p) b"


class Onda:
    """Uma onda de verdade numa pasta temporária: candidatos do parser, fiscal do `fiscal.py`, provas
    Wolfram com a `impressao` que o registrador gravaria."""
    def __init__(self, raiz):
        self.raiz = raiz
        self.equacoes = [cand("Kelly.pdf.md#1", MAE_KELLY, 1), cand("Kelly.pdf.md#2", FILHA_KELLY, 2),
                         cand("Kelly.pdf.md#3", FILHA_ERRADA, 3),
                         cand("Ramo.pdf.md#1", "y = x^{2}", 1, fonte={"documento": "Ramo.pdf.md", "topico": "R"}),
                         cand("Ramo.pdf.md#2", r"x = \sqrt{y}", 2, fonte={"documento": "Ramo.pdf.md", "topico": "R"})]
        self.derivacoes = [deriv("Kelly.pdf.md#1", "Kelly.pdf.md#2", "f"), deriv("Kelly.pdf.md#1", "Kelly.pdf.md#3", "f"),
                           deriv("Ramo.pdf.md#1", "Ramo.pdf.md#2", "x")]
        self.validades = [{"equacao": "Kelly.pdf.md#2", "condicao": "b > 0"}]
        self.wolfram = [("Kelly.pdf.md#1", "Kelly.pdf.md#2", "verde"), ("Kelly.pdf.md#1", "Kelly.pdf.md#3", "vermelho"),
                        ("Ramo.pdf.md#1", "Ramo.pdf.md#2", "indeterminado")]
        self.decisoes = []

    def arquivo(self, prefixo):
        return os.path.join(self.raiz, "%s-%s.jsonl" % (prefixo, ONDA))

    def gravar(self, fiscal=True):
        escrever_jsonl(self.arquivo("equacoes"), self.equacoes)
        escrever_jsonl(self.arquivo("derivacoes"), self.derivacoes)
        escrever_jsonl(self.arquivo("validades"), self.validades)
        escrever_jsonl(self.arquivo("decisoes"), self.decisoes)
        provas = []
        for mae, filha, veredito in self.wolfram:
            l = {"prova": "P2", "via": "wolfram", "mae": mae, "filha": filha, "veredito": veredito,
                 "codigo": "Simplify[...]", "saida": "Out[1]= 0"}
            l["impressao"] = FI.impressao_esperada(FI.chave_wolfram(l), self.equacoes, self.derivacoes)
            provas.append(l)
        escrever_jsonl(self.arquivo("provas"), provas)
        if fiscal:
            with contextlib.redirect_stdout(io.StringIO()):
                FI.main(["--onda", ONDA, "--raiz-esteira", self.raiz])

    def aprovar(self, *extra, banco=None):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = AO.main(["--onda", ONDA, "--raiz-esteira", self.raiz, "--corpus", PARTICAO] + list(extra),
                             banco=banco)
        return codigo, saida.getvalue()


class BaseOnda(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.onda = Onda(self.tmp)


class TesteCli(BaseOnda):
    def test_sem_executar_imprime_o_plano_e_nao_abre_o_banco(self):
        self.onda.gravar()
        with mock.patch.object(AO.nucleo, "abrir_banco", side_effect=AssertionError("abriu o banco")):
            codigo, saida = self.onda.aprovar()
        self.assertEqual(codigo, 0)
        self.assertIn("nada gravado", saida)
        self.assertIn("Kelly.pdf.md#3", saida)

    def test_decisao_desconhecida_recusa_antes_de_abrir_o_banco(self):
        self.onda.decisoes = [{"tipo": "promover_tudo"}]
        self.onda.gravar()
        with mock.patch.object(AO.nucleo, "abrir_banco", side_effect=AssertionError("abriu o banco")):
            with self.assertRaises(SystemExit) as c:
                self.onda.aprovar("--executar")
        self.assertIn("promover_tudo", str(c.exception.code))

    def test_fiscal_desatualizado_recusa(self):
        self.onda.gravar()
        self.onda.equacoes[2] = cand("Kelly.pdf.md#3", FILHA_KELLY, 3)    # a filha errada foi "consertada" depois
        self.onda.gravar(fiscal=False)
        with self.assertRaises(SystemExit) as c:
            self.onda.aprovar()
        self.assertIn("fiscal.py", str(c.exception.code))

    def test_sem_fiscal_recusa(self):
        self.onda.gravar(fiscal=False)
        with self.assertRaises(SystemExit):
            self.onda.aprovar()

    def test_corpus_divergente_recusa(self):
        self.onda.equacoes[0]["corpus"] = "incerto"
        self.onda.gravar()
        with self.assertRaises(SystemExit) as c:
            self.onda.aprovar()
        self.assertIn("corpus", str(c.exception.code))

    def test_candidato_de_outra_onda_recusa_antes_do_banco(self):
        self.onda.equacoes[1]["onda"] = "2026-10-OUTRA"
        self.onda.gravar(fiscal=False)
        escrever_jsonl(self.onda.arquivo("fiscal"), [])
        with self.assertRaises(ValueError) as c:
            AO.carregar_onda(self.tmp, ONDA, PARTICAO)
        self.assertIn("2026-10-OUTRA", str(c.exception))
        with mock.patch.object(AO.nucleo, "abrir_banco", side_effect=AssertionError("abriu o banco")):
            with self.assertRaises(SystemExit):
                self.onda.aprovar("--executar")

    def test_plano_da_onda_de_verdade(self):
        self.onda.gravar()
        dados = AO.carregar_onda(self.tmp, ONDA, PARTICAO)
        plano = AO.decidir(dados["equacoes"], dados["derivacoes"], dados["validades"], dados["fiscal"],
                           dados["decisoes"])
        deriva = {(d["mae"], d["filha"]): d["status"] for d in plano["deriva_de"]}
        self.assertEqual(deriva, {("Kelly.pdf.md#1", "Kelly.pdf.md#2"): "aprovado",
                                  ("Kelly.pdf.md#1", "Kelly.pdf.md#3"): "staging",
                                  ("Ramo.pdf.md#1", "Ramo.pdf.md#2"): "staging"})


class TesteRebaixar(unittest.TestCase):
    def test_no_da_onda_fora_do_plano_e_rebaixado(self):
        dec = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d", "sinonimos": [],
                "fonte": {"documento": DOC, "topico": "T"}}]
        plano = AO.decidir([eq_fixa("a")], [], [], [p1("a")], dec)
        existentes = [("Equacao", "a"), ("Equacao", "velha"), ("Conceito", "ruina"), ("Conceito", "antigo"),
                      ("Heuristica", "h"), ("Conceito", "a")]
        self.assertEqual(AO.a_rebaixar(existentes, plano),
                         [("Conceito", "a"), ("Conceito", "antigo"), ("Equacao", "velha"), ("Heuristica", "h")])
        self.assertEqual(AO.a_rebaixar([("Equacao", "a"), ("Conceito", "ruina")], plano), [])


class TesteGravarJsonl(unittest.TestCase):
    def test_falha_nao_deixa_temporario(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        caminho = os.path.join(tmp, "equacoes-x.jsonl")
        with self.assertRaises(TypeError):
            AO._gravar_jsonl(caminho, [{"ok": 1}, {"ruim": object()}])
        self.assertEqual(os.listdir(tmp), [])


class TesteAplicarMomentos(BaseOnda):
    def test_grava_o_momento_no_candidato_de_forma_deterministica(self):
        self.onda.decisoes = [{"tipo": "momento_fechado", "equacao": "Kelly.pdf.md#2",
                               "momento_fechado": {"media": "p - (1 - p)/b"}}]
        self.onda.gravar(fiscal=False)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(AO.main(["--onda", ONDA, "--raiz-esteira", self.tmp, "--corpus", PARTICAO,
                                      "--aplicar-momentos"]), 0)
        with io.open(self.onda.arquivo("equacoes"), encoding="utf-8", newline="") as f:
            texto = f.read()
        self.assertNotIn("\r", texto)
        linhas = [json.loads(l) for l in texto.splitlines()]
        self.assertEqual(linhas[1]["momento_fechado"], {"media": "p - (1 - p)/b"})
        self.assertNotIn("momento_fechado", linhas[0])
        self.assertEqual(texto, "".join(json.dumps(l, sort_keys=True, ensure_ascii=False) + "\n" for l in linhas))

    def test_momento_de_equacao_desconhecida_ou_vazio_e_recusado(self):
        eqs = [eq_fixa("a")]
        for dec in ({"tipo": "momento_fechado", "equacao": "zz", "momento_fechado": {"media": "x"}},
                    {"tipo": "momento_fechado", "equacao": "a", "momento_fechado": {}},
                    {"tipo": "momento_fechado", "equacao": "a", "momento_fechado": {"media": ""}}):
            with self.assertRaises(ValueError, msg=dec):
                AO.aplicar_momentos(eqs, [dec])


@precisa_neo4j
class TesteBancoReal(BaseOnda):
    def setUp(self):
        super().setUp()
        self.cred, self.db = banco_de_teste()
        self.addCleanup(limpar_banco_de_teste, self.cred, self.db)

    def q(self, cypher):
        return NUC.query_api(self.cred, self.db, cypher, {"c": PARTICAO})

    def status_deriva(self, filha):
        return self.q("MATCH (f:Equacao {corpus: $c, nome: '%s'})-[r:DERIVA_DE]->() RETURN r.status" % filha)

    def executar(self):
        codigo, _ = self.onda.aprovar("--executar", banco=(self.cred, self.db))
        self.assertEqual(codigo, 0)

    def test_vermelho_nunca_promove(self):
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.status_deriva("Kelly.pdf.md#3"), [["staging"]])
        self.assertEqual(self.status_deriva("Kelly.pdf.md#2"), [["aprovado"]])
        # o aceite do PO não vale para vermelho
        self.onda.decisoes = [aceite(prova="P2", mae="Kelly.pdf.md#1", filha="Kelly.pdf.md#3", simbolo="f",
                                     substituicao={}),
                              aceite(prova="P4", mae="Kelly.pdf.md#1", filha="Kelly.pdf.md#3")]
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.status_deriva("Kelly.pdf.md#3"), [["staging"]])

    def test_indeterminado_so_com_aceite_do_po(self):
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.status_deriva("Ramo.pdf.md#2"), [["staging"]])
        self.onda.decisoes = [aceite(prova="P2", mae="Ramo.pdf.md#1", filha="Ramo.pdf.md#2", simbolo="x",
                                     substituicao={}),
                              aceite(prova="P4", mae="Ramo.pdf.md#1", filha="Ramo.pdf.md#2")]
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.status_deriva("Ramo.pdf.md#2"), [["aprovado"]])
        # aceite não é verificação: nenhuma via em `verificado_por`, as duas provas em `aceites_po`
        self.assertEqual(self.q("MATCH (:Equacao {corpus: $c, nome: 'Ramo.pdf.md#2'})-[r:DERIVA_DE]->() "
                                "RETURN r.verificado_por, r.aceites_po"), [[[], ["P2", "P4"]]])

    def test_deriva_de_grava_as_duas_vias_em_verificado_por(self):
        self.onda.gravar()
        self.executar()
        r = self.q("MATCH (:Equacao {corpus: $c, nome: 'Kelly.pdf.md#2'})-[r:DERIVA_DE]->"
                   "(:Equacao {nome: 'Kelly.pdf.md#1'}) RETURN r.verificado_por, r.status, r.substituicao")
        self.assertEqual(r, [[["sympy@1.14.0", "wolfram"], "aprovado", "{}"]])

    def test_sem_executar_nao_escreve(self):
        self.onda.gravar()
        antes = self.q("MATCH (n {corpus: $c}) RETURN count(n)")
        codigo, _ = self.onda.aprovar(banco=(self.cred, self.db))
        self.assertEqual(codigo, 0)
        self.assertEqual(self.q("MATCH (n {corpus: $c}) RETURN count(n)"), antes)

    def test_tudo_leva_corpus_e_fonte(self):
        fonte = {"documento": DOC, "topico": "Aposta binária"}
        self.onda.decisoes = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d",
                               "sinonimos": [], "fonte": fonte},
                              {"tipo": "heuristica", "nome": "h", "enunciado": "e", "condicao": "c", "fonte": fonte,
                               "sustenta": ["ruina", "Kelly.pdf.md#2"]}]
        self.onda.gravar()
        self.executar()
        self.assertGreater(self.q("MATCH (n {corpus: $c}) RETURN count(n)")[0][0], 0)
        self.assertEqual(self.q("MATCH (n {corpus: $c}) WHERE n.fonte IS NULL OR n.status IS NULL "
                                "RETURN count(n)"), [[0]])
        self.assertGreater(self.q("MATCH ()-[r {corpus: $c}]->() RETURN count(r)")[0][0], 0)
        self.assertEqual(self.q("MATCH ()-[r {corpus: $c}]->() WHERE r.fonte IS NULL OR r.status IS NULL "
                                "RETURN count(r)"), [[0]])
        self.assertEqual(self.q("MATCH (n)-[r]-(m) WHERE n.corpus = $c AND r.corpus IS NULL RETURN count(r)"), [[0]])
        self.assertEqual(sorted(r[0] for r in self.q("MATCH (h:Heuristica {corpus: $c})-[r:SUSTENTA]->(x) "
                                                      "RETURN x.nome")), ["Kelly.pdf.md#2", "ruina"])

    def test_reaprovar_e_idempotente_e_renomear_nao_deixa_aresta_velha(self):
        self.onda.gravar()
        self.executar()
        contar = "MATCH (n {corpus: $c}) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n), count(r)"
        antes = self.q(contar)
        self.executar()
        self.assertEqual(self.q(contar), antes)
        self.onda.decisoes = [{"tipo": "renomear_variavel", "equacao": "Kelly.pdf.md#2", "simbolo": "b",
                               "nome": "odds"}]
        self.onda.gravar()
        self.executar()
        usadas = self.q("MATCH (:Equacao {corpus: $c, nome: 'Kelly.pdf.md#2'})-[:USA]->(v) RETURN v.nome ORDER BY v.nome")
        self.assertEqual([u[0] for u in usadas], ["f", "odds", "p"])
        self.assertEqual(self.q("MATCH (:Equacao {corpus: $c, nome: 'Kelly.pdf.md#2'})-[:VALIDA_SOB]->(v) "
                                "RETURN v.nome"), [["odds"]])

    def test_reaprovar_sem_a_equacao_ou_o_conceito_rebaixa_nunca_apaga(self):
        self.onda.decisoes = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d",
                               "sinonimos": [], "fonte": {"documento": DOC, "topico": "T"}}]
        self.onda.gravar()
        self.executar()
        st = "MATCH (n:%s {corpus: $c, nome: '%s'}) RETURN n.status, n.pendencias"
        self.assertEqual(self.q(st % ("Equacao", "Ramo.pdf.md#1"))[0][0], "aprovado")
        self.assertEqual(self.q(st % ("Conceito", "ruina"))[0][0], "aprovado")
        self.onda.equacoes = [e for e in self.onda.equacoes if not e["nome"].startswith("Ramo")]
        self.onda.derivacoes = [d for d in self.onda.derivacoes if not d["mae"].startswith("Ramo")]
        self.onda.wolfram = [w for w in self.onda.wolfram if not w[0].startswith("Ramo")]
        self.onda.decisoes = []
        self.onda.gravar()
        self.executar()
        for rotulo, nome in (("Equacao", "Ramo.pdf.md#1"), ("Equacao", "Ramo.pdf.md#2"), ("Conceito", "ruina")):
            self.assertEqual(self.q(st % (rotulo, nome)), [["staging", ["fora da rodada atual"]]], nome)
        self.assertEqual(self.q(st % ("Equacao", "Kelly.pdf.md#2"))[0][0], "aprovado")
        self.assertEqual(self.q("MATCH (:Equacao {corpus: $c, nome: 'Ramo.pdf.md#2'})-[r]->() RETURN count(r)"), [[0]])

    def test_rotulo_gravado_e_colisao_com_outra_equacao_recusa_sem_gravar(self):
        self.onda.decisoes = [{"tipo": "rotular_equacao", "equacao": "Kelly.pdf.md#2", "rotulo": "kelly"}]
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.q("MATCH (e:Equacao {corpus: $c, rotulo: 'kelly'}) RETURN e.nome"), [["Kelly.pdf.md#2"]])
        limpar_banco_de_teste(self.cred, self.db)
        NUC.query_api(self.cred, self.db, "CREATE (:Equacao {corpus: $c, nome: 'Outro.pdf.md#1', onda: 'outra', "
                      "rotulo: 'kelly', status: 'aprovado', fonte: '{}'})", {"c": PARTICAO})
        with self.assertRaises(SystemExit) as c:
            self.onda.aprovar("--executar", banco=(self.cred, self.db))
        self.assertIn("Outro.pdf.md#1", str(c.exception.code))
        self.assertEqual(self.q("MATCH (n {corpus: $c}) RETURN count(n)"), [[1]])

    def test_nome_de_equacao_de_outra_onda_recusa_sem_gravar(self):
        NUC.query_api(self.cred, self.db, "CREATE (:Equacao {corpus: $c, nome: 'Kelly.pdf.md#2', onda: 'outra', "
                      "status: 'aprovado', fonte: '{}'})", {"c": PARTICAO})
        self.onda.gravar()
        with self.assertRaises(SystemExit) as c:
            self.onda.aprovar("--executar", banco=(self.cred, self.db))
        self.assertIn("Kelly.pdf.md#2 (onda outra)", str(c.exception.code))
        self.assertEqual(self.q("MATCH (n {corpus: $c}) RETURN count(n)"), [[1]])
        self.assertEqual(self.q("MATCH (n {corpus: $c}) RETURN n.onda, n.status"), [["outra", "aprovado"]])


if __name__ == "__main__":
    unittest.main()
