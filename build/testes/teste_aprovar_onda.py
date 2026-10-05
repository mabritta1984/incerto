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
sys.modules.setdefault("limite_sympy", carregar("skills/lavra/scripts/limite_sympy.py"))
NUC = sys.modules.setdefault("nucleo", carregar("skills/lavra/scripts/nucleo.py"))
EQ = sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
FI = sys.modules.setdefault("fiscal", carregar("skills/lavra/scripts/fiscal.py"))
AO = carregar("skills/lavra/scripts/aprovar_onda.py")
RP = carregar("skills/lavra/scripts/registrar_prova.py")

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


def p4e(eq, veredito="verde", detalhe="d"):
    return {"prova": "P4", "alvo": eq, "equacao": eq, "prova_wolfram": "equacao", "veredito": veredito,
            "detalhe": detalhe}


class TesteGateEquacaoWolfram(unittest.TestCase):
    """Rodada corpus B: a P4 de equação (prova Wolfram `equacao`) pode reprovar uma equação que parseia."""
    SAIDA = "Out[1]= (2*alpha)/(-1 + alpha)"

    def eq(self, fiscal, decisoes=(), **extra):
        return AO.decidir([eq_fixa("a", **extra)], [], [], fiscal, list(decisoes))["equacoes"][0]

    def test_sem_prova_equacao_comportamento_de_hoje(self):
        e = self.eq([p1("a")])
        self.assertEqual((e["status"], e["verificado_por"]), ("aprovado", []))

    def test_vermelho_fica_em_staging_citando_a_saida_wolfram(self):
        e = self.eq([p1("a"), p4e("a", "vermelho", "equação — Wolfram vermelho: " + self.SAIDA)])
        self.assertEqual((e["status"], e["verificado_por"]), ("staging", []))
        self.assertTrue(any(self.SAIDA in p and p.startswith("P4 vermelho") for p in e["pendencias"]), e["pendencias"])
        # vermelho nunca promove, nem com aceite
        e = self.eq([p1("a"), p4e("a", "vermelho")], [aceite(prova="P4", equacao="a", prova_wolfram="equacao")])
        self.assertEqual(e["status"], "staging")

    def test_verde_ganha_wolfram_em_verificado_por(self):
        e = self.eq([p1("a"), p4e("a")])
        self.assertEqual((e["status"], e["verificado_por"], e["aceites_po"]), ("aprovado", ["wolfram"], []))
        # P1 vermelho: staging, e staging não lista via
        e = self.eq([p1("a", "vermelho"), p4e("a")])
        self.assertEqual((e["status"], e["verificado_por"]), ("staging", []))

    def test_indeterminado_so_com_aceite_exato(self):
        fis = [p1("a"), p4e("a", "indeterminado")]
        self.assertEqual(self.eq(fis)["status"], "staging")
        # o aceite da forma do momento (sem prova_wolfram) não casa com a linha da equação
        self.assertEqual(self.eq(fis, [aceite(prova="P4", equacao="a")])["status"], "staging")
        e = self.eq(fis, [aceite(prova="P4", equacao="a", prova_wolfram="equacao")])
        self.assertEqual((e["status"], e["verificado_por"], e["aceites_po"]), ("aprovado", [], ["P4"]))

    def test_do_registro_ao_gate_caso_real_scft_268(self):
        # o candidato real (P1 verde) com a prova Wolfram vermelha do gabarito: o fiscal de verdade a junta
        e = cand("SCFT#268", r"\frac{p^*}{p} = \frac{\alpha}{1 - \alpha}")
        w = {"prova": "equacao", "via": "wolfram", "equacao": "SCFT#268", "veredito": "vermelho",
             "codigo": "FullSimplify[...]", "saida": self.SAIDA}
        w["impressao"] = FI.impressao_esperada(("equacao", "SCFT#268"), [e], [])
        fis = [{k: v for k, v in l.items() if k != "ms"} for l in FI.provas([e], [], [], {("equacao", "SCFT#268"): w})]
        self.assertEqual([(l["prova"], l["veredito"]) for l in fis], [("P1", "verde"), ("P4", "vermelho")])
        eq = AO.decidir([e], [], [], fis, [])["equacoes"][0]
        self.assertEqual(eq["status"], "staging")
        self.assertTrue(any(self.SAIDA in p for p in eq["pendencias"]), eq["pendencias"])
        self.assertIn("e.verificado_por = l.verificado_por", AO.CYPHER_EQUACOES)

    def test_momento_e_equacao_se_avaliam_separados(self):
        m = {"media": "x"}
        e = self.eq([p1("a"), p4e("a")], momento_fechado=m)
        self.assertEqual(e["status"], "staging")                                   # falta a P4 do momento
        self.assertIn("sem prova P4 do momento fechado", e["pendencias"])
        e = self.eq([p1("a"), p4m("a"), p4e("a")], momento_fechado=m)
        self.assertEqual((e["status"], e["verificado_por"]), ("aprovado", ["wolfram"]))
        e = self.eq([p1("a"), p4m("a"), p4e("a", "vermelho")], momento_fechado=m)
        self.assertEqual(e["status"], "staging")


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


class TesteDeclararFuncoes(unittest.TestCase):
    """Decisão do PO de 05/10: `declarar_funcoes` diz, por documento, que símbolos são funções (o
    `extrair_equacoes.py --decisoes` os lê); validada com as outras, documento desconhecido recusado no gate."""

    def dec(self, funcoes=("f", "F", "gamma", "H"), documento=DOC, **extra):
        return dict({"tipo": "declarar_funcoes", "documento": documento,
                     "funcoes": list(funcoes) if isinstance(funcoes, tuple) else funcoes}, **extra)

    def test_linha_valida_passa(self):
        for funcoes in (["f", "F", "gamma", "H"], ["f_1", "I_x", "n_F", "T_max"]):
            por_tipo = AO.validar_decisoes([self.dec(funcoes)])
            self.assertEqual(por_tipo["declarar_funcoes"], [self.dec(funcoes)])
        self.assertIn("declarar_funcoes", AO.TIPOS_DECISAO)
        plano = AO.decidir([eq_fixa("a", funcoes_declaradas=["F", "H", "f", "gamma"])], [], [], [p1("a")], [self.dec()])
        self.assertEqual(plano["equacoes"][0]["status"], "aprovado")

    def test_malformada_e_recusada(self):
        for d in (self.dec([]), self.dec(["f", "f"]), self.dec(["f'"]), self.dec(["S^N"]), self.dec(["1f"]),
                  self.dec(["f_"]), self.dec([""]), self.dec([3]), self.dec("f"), self.dec(documento=""),
                  self.dec(documento="  "), self.dec(documento=None), self.dec(extra=1),
                  {"tipo": "declarar_funcoes", "documento": DOC},
                  # nome de função de marcação explícita (`\mathbb{E}`, `E[…]`, `\operatorname{Var}`): fundiria
                  # o operador com a função do PO
                  self.dec(["E"]), self.dec(["f", "Var"])):
            with self.subTest(d=d), self.assertRaises(ValueError):
                AO.validar_decisoes([d])

    def test_duas_declaracoes_do_mesmo_documento_sao_recusadas(self):
        with self.assertRaises(ValueError) as c:
            AO.validar_decisoes([self.dec(["f"]), self.dec(["F"])])
        self.assertIn("declarar_funcoes", str(c.exception))
        AO.validar_decisoes([self.dec(["f"]), self.dec(["f"], documento="Outro.pdf.md")])   # outro documento: ok

    def test_documento_desconhecido_e_recusado_no_gate(self):
        with self.assertRaises(ValueError) as c:
            AO.decidir([eq_fixa("a")], [], [], [p1("a")], [self.dec(documento="Fantasma.pdf.md")])
        self.assertIn("Fantasma.pdf.md", str(c.exception))

    def test_plano_lista_as_funcoes_declaradas_por_documento(self):
        outro = eq_fixa("b", fonte={"documento": "Outro.pdf.md", "topico": "T"})
        a = eq_fixa("a", funcoes_declaradas=["F", "f", "gamma"])
        plano = AO.decidir([a, outro], [], [], [p1("a"), p1("b")], [self.dec(["gamma", "F", "f"])])
        funcoes = {d["nome"]: d["funcoes_declaradas"] for d in plano["documentos"]}
        self.assertEqual(funcoes, {DOC: ["F", "f", "gamma"], "Outro.pdf.md": []})
        texto = "\n".join(AO.linhas_do_plano(plano))
        self.assertIn("%s: F, f, gamma" % DOC, texto)
        self.assertIn("Outro.pdf.md: nenhuma", texto)

    def test_declaracao_nao_aplicada_ao_candidato_recusa(self):
        # o PO declara (ou retira) e esquece de reextrair: o gate não aprova o que foi extraído com outra lista
        c_e_f = dict(EQ.candidato({"documento": DOC, "topico": "T", "ordem": 1, "latex": r"x = C(n + 1)"},
                                  ONDA, frozenset({"C", "F"})), nome="a", corpus=PARTICAO)
        self.assertIn("Function('C')", c_e_f["srepr"])
        casos = ((c_e_f, [self.dec(["F"])], "['C', 'F']", "['F']"),         # C retirada, não reextraída
                 (c_e_f, [], "['C', 'F']", "[]"),                            # decisão inteira retirada
                 (eq_fixa("a"), [self.dec(["F"])], "[]", "['F']"),           # declarada, não reextraída
                 (eq_fixa("a", funcoes_declaradas=["F"]), [self.dec(["F", "f"])], "['F']", "['F', 'f']"))
        for e, decs, candidato, decisao in casos:
            with self.subTest(decs=decs, candidato=candidato), self.assertRaises(ValueError) as c:
                AO.decidir([e], [], [], [p1("a")], decs)
            msg = str(c.exception)
            self.assertIn("declaração de funções não aplicada em %s" % DOC, msg)
            self.assertIn("candidato %s, decisão %s" % (candidato, decisao), msg)
            self.assertIn("extrair_equacoes.py --decisoes", msg)

    def test_declaracao_aplicada_passa(self):
        for e, decs in ((eq_fixa("a"), []), (eq_fixa("a", funcoes_declaradas=[]), []),
                        (eq_fixa("a", funcoes_declaradas=["F", "f"]), [self.dec(["f", "F"])])):
            with self.subTest(e=e.get("funcoes_declaradas"), decs=decs):
                self.assertEqual(AO.decidir([e], [], [], [p1("a")], decs)["equacoes"][0]["status"], "aprovado")

    def test_plano_mostra_a_funcao_declarada_aplicada_em_cada_equacao(self):
        # tirado do srepr do candidato: o PO vê onde a declaração virou aplicação (o `C` constante da eq. 13)
        latex13 = r"x^* = C\left(\frac{n - 1}{n + 1}\right)^{1/n}"
        e13 = dict(EQ.candidato({"documento": DOC, "topico": "T", "ordem": 13, "latex": latex13}, ONDA,
                                frozenset({"C", "F"})), nome="a", corpus=PARTICAO)
        b = eq_fixa("b", funcoes_declaradas=["C", "F"])
        plano = AO.decidir([e13, b], [], [], [p1("a"), p1("b")], [self.dec(["C", "F"])])
        self.assertEqual({e["nome"]: e["funcoes_aplicadas"] for e in plano["equacoes"]}, {"a": ["C"], "b": []})
        linhas = AO.linhas_do_plano(plano)
        i = linhas.index("  aprovado a")
        self.assertIn("função declarada aplicada: C", "\n".join(linhas[i:i + 4]))
        j = linhas.index("  aprovado b")
        self.assertNotIn("função declarada aplicada", "\n".join(linhas[j:j + 3]))


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


class TesteCypher(unittest.TestCase):
    def test_conceito_e_heuristica_promovidos_limpam_a_pendencia_do_rebaixamento(self):
        # M3: rebaixado ("fora da rodada atual") e depois decidido de novo voltava `aprovado` com a pendência velha
        for cypher, var in ((AO.CYPHER_CONCEITOS, "c"), (AO.CYPHER_HEURISTICAS, "h")):
            self.assertIn("%s.pendencias = []" % var, cypher)

    def test_documento_e_sempre_aprovado(self):
        dec = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d", "sinonimos": [],
                "fonte": {"documento": "Outro.pdf.md", "topico": "T"}}]
        plano = AO.decidir([eq_fixa("a")], [], [], [p1("a", "vermelho")], dec)
        self.assertEqual({d["status"] for d in plano["documentos"]}, {"aprovado"})
        self.assertEqual(plano["equacoes"][0]["status"], "staging")


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


class TesteFimAFim(unittest.TestCase):
    """Extração real → fiscal → registrar_prova → fiscal → gate, sem banco: a média da Pareto só sai aprovada
    com o momento declarado e provado na via Wolfram; a derivação de Kelly, com as duas vias verdes; e a
    eq. (1) de Convex_Responses só parseia (e sai aprovada) depois que o PO declara `F` e `f` funções."""
    ONDA_E2E = "2026-10-E2E"
    DOC_MD = ("## Pareto\n\n$$\\mathbb{E}[X] = \\frac{\\alpha L}{\\alpha - 1}$$\n\n"
              "## Kelly\n\n$$\\frac{p b}{1 + b f} - \\frac{1 - p}{1 - f} = 0$$\n\n$$f = p - \\frac{1 - p}{b}$$\n")
    # outro documento: no de Kelly `f` é variável, e declará-la função lá seria `uso_misto:f`
    DOC_CONVEXO = ("## Convexidade\n\n"
                   "$$F(x, \\lambda) = \\frac{f(x + \\lambda) + f(x - \\lambda)}{2} - f(x) \\tag{1}$$\n")
    # gabaritos de references/fiscal.md, verbatim
    CODIGO_MEDIA = ("FullSimplify[Expectation[x, x \\[Distributed] ParetoDistribution[L, alpha], Assumptions -> "
                    "alpha > 1 && L > 0] - (alpha L/(alpha - 1)), Assumptions -> alpha > 1 && L > 0]\n")
    SAIDA_MEDIA = ("Symbol::undefined2: Warning: Global symbols \"L, L, L, L\" are undefined.\n"
                   "General::messages: Messages were generated which may indicate errors.\n\nOut[1]= 0\n")
    CODIGO_KELLY = "Simplify[(p - (1 - p)/b) - (f /. First@Solve[p b/(1 + b f) - (1 - p)/(1 - f) == 0, f])]\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.esteira = os.path.join(self.tmp, "_esteira", "incerto")
        conf = os.path.join(self.tmp, "conferidos", self.ONDA_E2E)
        os.makedirs(conf)
        for nome, conteudo in (("Taleb.pdf.md", self.DOC_MD), ("Convex_Responses.pdf.md", self.DOC_CONVEXO)):
            with io.open(os.path.join(conf, nome), "w", encoding="utf-8", newline="\n") as f:
                f.write(conteudo)

    def arq(self, prefixo):
        return os.path.join(self.esteira, "%s-%s.jsonl" % (prefixo, self.ONDA_E2E))

    def texto(self, nome, conteudo):
        caminho = os.path.join(self.tmp, nome)
        with io.open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)
        return caminho

    def cli(self, modulo, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return modulo.main(list(args))

    def fiscal(self):
        self.assertEqual(self.cli(FI, "--onda", self.ONDA_E2E, "--raiz-esteira", self.esteira), 0)

    def registrar(self, *args):
        self.assertEqual(self.cli(RP, "--onda", self.ONDA_E2E, "--raiz-esteira", self.esteira, *args), 0)

    def plano(self):
        dados = AO.carregar_onda(self.esteira, self.ONDA_E2E, AO.CORPUS)
        AO.conferir_fiscal_atual(dados)                    # o fiscal gravado é o desta onda, agora
        return AO.decidir(dados["equacoes"], dados["derivacoes"], dados["validades"], dados["fiscal"],
                          dados["decisoes"])

    def test_pareto_e_kelly_da_extracao_ao_gate(self):
        self.assertEqual(self.cli(EQ, "--raiz", self.tmp, "--onda", self.ONDA_E2E, "--saida", self.arq("equacoes")), 0)
        media, mae, filha = "Taleb.pdf.md#1", "Taleb.pdf.md#2", "Taleb.pdf.md#3"
        escrever_jsonl(self.arq("derivacoes"), [deriv(mae, filha, "f")])

        # 1. sem momento_fechado: a média só tem P1 verde, mas aplica E — não pode sair aprovada
        self.fiscal()
        self.registrar("--prova", "P2", "--mae", mae, "--filha", filha, "--codigo", self.texto("k.wl", self.CODIGO_KELLY),
                       "--saida", self.texto("k.txt", "Out[1]= 0\n"), "--veredito", "verde")
        self.fiscal()
        plano = self.plano()
        eqs = {e["nome"]: e for e in plano["equacoes"]}
        self.assertEqual(eqs[media]["status"], "staging")
        self.assertIn("aplica E/Var sem momento_fechado declarado", " ".join(eqs[media]["pendencias"]))
        d = plano["deriva_de"][0]
        self.assertEqual((d["filha"], d["mae"], d["status"], d["verificado_por"], d["aceites_po"]),
                         (filha, mae, "aprovado", ["sympy@1.14.0", "wolfram"], []))

        # 2. o PO declara o momento: aplicado ao candidato, a P4 exige a prova Wolfram dele
        escrever_jsonl(self.arq("decisoes"), [{"tipo": "momento_fechado", "equacao": media,
                                               "momento_fechado": {"media": "alpha*L/(alpha - 1)"}}])
        self.assertEqual(self.cli(AO, "--onda", self.ONDA_E2E, "--raiz-esteira", self.esteira, "--aplicar-momentos"), 0)
        self.fiscal()
        self.assertEqual({e["nome"]: e["status"] for e in self.plano()["equacoes"]}[media], "staging")
        # verde com a saída que não é zero é recusado pelo registrador
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.registrar("--prova", "momento", "--equacao", media, "--codigo", self.texto("m.wl", self.CODIGO_MEDIA),
                           "--saida", self.texto("m.txt", "Out[1]= (alpha*L)/(-1 + alpha)\n"), "--veredito", "verde")
        self.registrar("--prova", "momento", "--equacao", media, "--codigo", self.texto("m.wl", self.CODIGO_MEDIA),
                       "--saida", self.texto("m.txt", self.SAIDA_MEDIA), "--veredito", "verde")
        self.fiscal()
        plano = self.plano()
        eqs = {e["nome"]: e for e in plano["equacoes"]}
        self.assertEqual((eqs[media]["status"], eqs[media]["pendencias"]), ("aprovado", []))
        self.assertEqual(json.loads(eqs[media]["momento_fechado"]), {"media": "alpha*L/(alpha - 1)"})
        self.assertEqual(plano["deriva_de"][0]["status"], "aprovado")

        # 3. Convex_Responses (1): sem declaração é perda (`F(` ambíguo) e P1 vermelho; o PO declara `F` e `f`
        convexa = "Convex_Responses.pdf.md#1"
        self.assertEqual(eqs[convexa]["status"], "staging")
        self.assertIn("nao_suportado:F(", " ".join(eqs[convexa]["pendencias"]))
        with io.open(self.arq("decisoes"), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"tipo": "declarar_funcoes", "documento": "Convex_Responses.pdf.md", "funcoes": ["f", "F"]},
                               sort_keys=True, ensure_ascii=False) + "\n")
        # a extração recusa sobrescrever o candidato antigo (com o momento aplicado): o rito o tira do caminho,
        # reextrai com --decisoes, reaplica os momentos e refaz o fiscal
        with self.assertRaises(SystemExit):
            self.cli(EQ, "--raiz", self.tmp, "--onda", self.ONDA_E2E, "--saida", self.arq("equacoes"))
        os.replace(self.arq("equacoes"), self.arq("equacoes") + ".antes-de-declarar-funcoes")
        self.assertEqual(self.cli(EQ, "--raiz", self.tmp, "--onda", self.ONDA_E2E, "--saida", self.arq("equacoes"),
                                  "--decisoes", self.arq("decisoes")), 0)
        self.assertEqual(self.cli(AO, "--onda", self.ONDA_E2E, "--raiz-esteira", self.esteira, "--aplicar-momentos"), 0)
        self.fiscal()
        p1_convexa = [l for l in ler_jsonl(self.arq("fiscal")) if l["prova"] == "P1" and l["equacao"] == convexa]
        self.assertEqual([l["veredito"] for l in p1_convexa], ["verde"])
        plano = self.plano()
        eqs = {e["nome"]: e for e in plano["equacoes"]}
        self.assertEqual((eqs[convexa]["status"], eqs[convexa]["forma"], eqs[convexa]["pendencias"]),
                         ("aprovado", "algebrica", []))
        self.assertIn("Function('F')", eqs[convexa]["sympy_srepr"])
        self.assertEqual({d["nome"]: d["funcoes_declaradas"] for d in plano["documentos"]},
                         {"Convex_Responses.pdf.md": ["F", "f"], "Taleb.pdf.md": []})
        self.assertEqual({e["fonte"]["documento"]: e["funcoes_declaradas"] for e in ler_jsonl(self.arq("equacoes"))},
                         {"Convex_Responses.pdf.md": ["F", "f"], "Taleb.pdf.md": []})
        # as provas Wolfram da média e de Kelly seguem válidas: o srepr delas não mudou
        self.assertEqual((eqs[media]["status"], plano["deriva_de"][0]["status"]), ("aprovado", "aprovado"))


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
        # decidido de novo, volta aprovado sem a pendência do rebaixamento
        self.onda.decisoes = [{"tipo": "conceito", "nome": "ruina", "tipo_conceito": "fenomeno", "definicao": "d",
                               "sinonimos": [], "fonte": {"documento": DOC, "topico": "T"}}]
        self.onda.gravar()
        self.executar()
        self.assertEqual(self.q(st % ("Conceito", "ruina")), [["aprovado", []]])
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
