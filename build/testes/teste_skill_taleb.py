# -*- coding: utf-8 -*-
"""Task 16: estação `taleb` — SKILL.md (frontmatter, bloco `regras-do-incerto` injetado, rito em cinco passos
com Wolfram antes do veredito), `references/doutrina.md` (fonte em todo verbete) e `references/heuristicas.md`
(condição parseável pelo fiscal). Nenhum arquivo da estação recomenda ativo."""
import os
import re
import sys
import unittest
from _carga import RAIZ, carregar

sys.modules.setdefault("dados_br", carregar("skills/taleb/scripts/dados_br.py"))
sys.modules.setdefault("caudas", carregar("skills/taleb/scripts/caudas.py"))
sys.modules.setdefault("convexidade", carregar("skills/taleb/scripts/convexidade.py"))
R = carregar("skills/taleb/scripts/relatorio.py")
sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
sys.modules.setdefault("limite_sympy", carregar("skills/lavra/scripts/limite_sympy.py"))
FI = carregar("skills/lavra/scripts/fiscal.py")

SKILL = "skills/taleb/SKILL.md"
DOUTRINA = "skills/taleb/references/doutrina.md"
HEURISTICAS = "skills/taleb/references/heuristicas.md"
SIMBOLOS = ["kappa", "alpha", "H", "fracao_segura"]
CONCEITOS = ("antifragilidade", "caudas gordas", "convexidade", "barbell", "via negativa", "ergodicidade",
             "skin in the game", "falácia lúdica", "problema do peru", "cisne negro")
GATILHOS = ("analisar exposição", "é frágil?", "barbell", "cauda", "/taleb")
RE_FONTE = re.compile(r"^fonte:\s*(\(.+?,.+?\)|\[externo\])", re.M)
RE_BLOCO = re.compile(r"<!-- bloco:regras-do-incerto:inicio \((?P<papel>dono|gerado)[^>]*-->\n(?P<miolo>.*?)"
                      r"<!-- bloco:regras-do-incerto:fim -->", re.S)
# Imperativo/aconselhamento de compra e venda: proibido em qualquer lugar da estação.
RE_PROIBIDA = re.compile(r"\b(compre|venda|recomendo|recomendamos)\b", re.I)
# Infinitivo: só dentro de uma frase de proibição explícita (`nunca`/`jamais` antes da palavra, na mesma frase).
RE_INFINITIVO = re.compile(r"\b(comprar|vender)\b", re.I)
RE_PROIBICAO = re.compile(r"\b(nunca|jamais)\b", re.I)
# "autoriza…" a até 80 caracteres de "variância" (em qualquer ordem): licença de variância como medida de risco.
RE_AUTORIZA_VARIANCIA = re.compile(r"autoriz\w*.{0,80}?variância|variância.{0,80}?autoriz\w*", re.I | re.S)


def ler(rel):
    with open(os.path.join(RAIZ, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def verbetes(texto):
    """[(título, corpo)] de cada `### ` até o próximo cabeçalho `## `/`### `."""
    partes = re.split(r"^(###? .*)$", texto, flags=re.M)
    return [(partes[i][4:].strip(), partes[i + 1]) for i in range(1, len(partes), 2)
            if partes[i].startswith("### ")]


def campo(corpo, nome):
    m = re.search(rf"^{nome}:\s*(.+)$", corpo, re.M)
    return m.group(1).strip().strip("`") if m else None


def frase_em(texto, pos):
    """A frase que contém `pos`: do último `.`/`!`/`?`/linha em branco antes até a posição."""
    inicio = max(texto.rfind(s, 0, pos) for s in (". ", "! ", "? ", ".\n", "\n\n"))
    return texto[inicio + 1:pos]


class TesteSkillTaleb(unittest.TestCase):
    def test_frontmatter_e_bloco_injetado(self):
        texto = ler(SKILL)
        m = re.match(r"---\n(.*?)\n---\n", texto, re.S)
        self.assertIsNotNone(m, "SKILL.md sem frontmatter")
        fm = m.group(1)
        self.assertRegex(fm, r"(?m)^name: taleb$")
        self.assertIn("description:", fm)
        for g in GATILHOS:
            self.assertIn(g, fm, f"gatilho ausente da description: {g}")
        dono = RE_BLOCO.search(ler("regras-do-incerto.md"))
        consumidor = RE_BLOCO.search(texto)
        self.assertIsNotNone(consumidor, "SKILL.md não declara o bloco regras-do-incerto")
        self.assertEqual(consumidor.group("papel"), "gerado")
        self.assertIn("gerado de regras-do-incerto.md", consumidor.group(0))
        self.assertEqual(consumidor.group("miolo"), dono.group("miolo"), "bloco divergente do dono")

    def test_rito_exige_wolfram_antes_de_afirmar(self):
        texto = ler(SKILL)
        m = re.search(r"^## Rito\b.*?(?=^## )", texto, re.S | re.M)
        self.assertIsNotNone(m, "SKILL.md sem seção ## Rito")
        rito = m.group(0)
        passos = re.findall(r"^(\d)\. ", rito, re.M)
        self.assertEqual(passos, ["1", "2", "3", "4", "5"])
        passo5 = re.search(r"^5\. .*?(?=^\S|\Z)", rito, re.S | re.M).group(0)
        self.assertIn("Wolfram", passo5)
        self.assertIn("Veredito", rito)
        self.assertLess(rito.index(passo5), rito.index("Veredito"), "Wolfram tem de vir antes do Veredito")
        for ferramenta in ("buscar_equacao", "ler_conceito", "dados_br.py", "caudas.py", "convexidade.py",
                           "relatorio.py"):
            self.assertIn(ferramenta, rito)
        self.assertIn(R.FECHAMENTO, texto)
        for ferramenta in ("buscar_equacao", "ler_equacao", "ler_conceito", "situacao_camada"):
            self.assertIn(f"`{ferramenta}`", texto)
        self.assertIn("skills/lavra/references/fiscal.md", texto)

    def test_doutrina_marca_fonte_em_todo_verbete(self):
        vs = verbetes(ler(DOUTRINA))
        self.assertEqual(sorted(t for t, _ in vs), sorted(CONCEITOS))
        for titulo, corpo in vs:
            self.assertRegex(corpo, RE_FONTE, f"verbete sem fonte: {titulo}")

    def test_heuristicas_tem_condicao_parseavel(self):
        vs = verbetes(ler(HEURISTICAS))
        self.assertGreaterEqual(len(vs), 4)
        conceitos = set(CONCEITOS)
        for titulo, corpo in vs:
            for nome in ("enunciado", "condicao", "sustenta"):
                self.assertTrue(campo(corpo, nome), f"{titulo}: falta {nome}:")
            self.assertRegex(corpo, RE_FONTE, f"heurística sem fonte: {titulo}")
            cond = campo(corpo, "condicao")
            self.assertTrue(FI.relacional_parseia(cond, SIMBOLOS), f"{titulo}: condição não parseia: {cond}")
            citados = {c.strip() for c in campo(corpo, "sustenta").split(",")}
            self.assertLessEqual(citados, conceitos, f"{titulo}: sustenta conceito fora da doutrina")
        # O limiar do Extremistão é o mesmo do relatorio.py.
        conds = [campo(c, "condicao") for _, c in vs]
        self.assertIn(f"kappa > {R.LIMIAR_KAPPA} or alpha < {R.LIMIAR_ALFA:g}", conds)
        # rodada corpus C: o limiar de κ é o do corpus (SCFT 8.3.2), sobre κ_1 = κ(1, 2)
        self.assertIn("kappa > 0.15 or alpha < 2", conds)
        texto = ler(HEURISTICAS)
        self.assertIn("8.3.2", texto); self.assertIn("κ(n0=1, n=2)", texto)
        # fix 1: κ_1 exato julgado pelo intervalo bootstrap inteiro, como H; fronteira não dispara heurística
        self.assertIn("kappa_1_exato", texto); self.assertIn("fronteira", texto)
        self.assertIn("eq. 8.8", texto); self.assertIn("Table 8.3", texto)
        self.assertNotIn("0,3", texto); self.assertNotIn("0.3 ", texto)

    def test_heuristicas_nao_autorizam_variancia(self):
        # Com 2 <= alpha < 4 a variância existe mas sua estimativa é instável: nenhuma heurística a licencia.
        texto = ler(HEURISTICAS)
        self.assertIsNone(RE_AUTORIZA_VARIANCIA.search(texto), RE_AUTORIZA_VARIANCIA.search(texto))
        vs = dict(verbetes(texto))
        mediocristao = campo(vs["Mediocristão não é atestado de segurança"], "enunciado")
        self.assertIn("instável", mediocristao)
        self.assertIn("2 ≤ α̂ < 4", mediocristao)

    def test_barbell_declara_limiar_autoral_e_lado_seguro_nulo(self):
        barbell = campo(dict(verbetes(ler(HEURISTICAS)))["perda máxima delimitada por construção"], "enunciado")
        self.assertIn("limiar autoral do Incerto", barbell)
        self.assertIn("perda nula", barbell)
        self.assertIn("nula", dict(verbetes(ler(DOUTRINA)))["barbell"])

    def test_skill_nunca_recomenda(self):
        for rel in (SKILL, DOUTRINA, HEURISTICAS):
            texto = ler(rel)
            self.assertIsNone(RE_PROIBIDA.search(texto), f"{rel}: {RE_PROIBIDA.search(texto)}")
            for m in RE_INFINITIVO.finditer(texto):
                self.assertRegex(frase_em(texto, m.start()), RE_PROIBICAO,
                                 f"{rel}: '{m.group(0)}' fora de frase de proibição explícita")

    def test_frase_em_isola_a_proibicao(self):
        # A guarda do teste acima não pode ser vazia: `nunca` de outra frase não autoriza o infinitivo.
        texto = "Nunca diga isso. Convém comprar já."
        pos = RE_INFINITIVO.search(texto).start()
        self.assertNotRegex(frase_em(texto, pos), RE_PROIBICAO)
        texto = "O veredito jamais manda comprar."
        self.assertRegex(frase_em(texto, RE_INFINITIVO.search(texto).start()), RE_PROIBICAO)


if __name__ == "__main__":
    unittest.main()
