# -*- coding: utf-8 -*-
"""Task 19 (passo 1): estação `lavra` — SKILL.md (frontmatter, bloco `regras-do-incerto` injetado, o rito por
onda em oito passos na ordem, cada um com comando e condição de parada, e só scripts e flags que existem) e
`references/devolucao.md` (o bloco de decisão único da rodada: os cinco tipos de decisão na ordem, cada
linha JSONL aceita pelo validador de `aprovar_onda.py`, e vermelho que nunca promove). Nada aqui toca rede."""
import json
import os
import re
import sys
import unittest
from _carga import RAIZ, carregar

sys.modules.setdefault("recortar_trechos", carregar("skills/lavra/scripts/recortar_trechos.py"))
sys.modules.setdefault("nucleo", carregar("skills/lavra/scripts/nucleo.py"))
sys.modules.setdefault("extrair_equacoes", carregar("skills/lavra/scripts/extrair_equacoes.py"))
sys.modules.setdefault("fiscal", carregar("skills/lavra/scripts/fiscal.py"))
AO = carregar("skills/lavra/scripts/aprovar_onda.py")

SKILL = "skills/lavra/SKILL.md"
DEVOLUCAO = "skills/lavra/references/devolucao.md"
SCRIPTS = "skills/lavra/scripts"
GATILHOS = ("rodar uma onda", "converter os PDFs do Taleb", "/lavra")
# Os oito passos do rito, na ordem do plano (Task 19, passos 2–7): o título de cada `### N. ` começa assim.
PASSOS = ("Copiar os originais", "Disparar a conversão", "Portão", "Recortar, ingerir e extrair",
          "Aplicar os momentos", "Rodada do fiscal", "Bloco de decisão", "Aprovar")
# Passos que gastam dinheiro (modelo, Vertex) ou escrevem no Aura: o texto exige a decisão do PO antes.
CUSTOSOS = (1, 2, 4, 8)
RITO_SCRIPTS = ("conferir_onda.py", "recortar_trechos.py", "ingerir_trechos.py", "extrair_equacoes.py",
                "aprovar_onda.py", "fiscal.py", "registrar_prova.py")
# Ordem do bloco de decisão: renomeações, conceitos, heurísticas, momentos, indeterminados, vermelhos.
DECISOES = ("renomear_variavel", "conceito", "heuristica", "momento_fechado", "aceitar_indeterminado")
RE_BLOCO = re.compile(r"<!-- bloco:regras-do-incerto:inicio \((?P<papel>dono|gerado)[^>]*-->\n(?P<miolo>.*?)"
                      r"<!-- bloco:regras-do-incerto:fim -->", re.S)
RE_SCRIPT = re.compile(r"\b([a-z_]+\.py)\b")
RE_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
RE_ARG = re.compile(r"\.add_argument\(\s*\"(--[a-z][a-z-]*)\"")


def ler(rel):
    with open(os.path.join(RAIZ, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def sem_bloco(texto):
    return RE_BLOCO.sub("", texto)


def rito(texto):
    m = re.search(r"^## Rito\b.*?(?=^## |\Z)", sem_bloco(texto), re.S | re.M)
    return m.group(0) if m else None


def passos(texto):
    """[(número, título, corpo)] de cada `### N. Título` da seção ## Rito."""
    partes = re.split(r"^### (\d+)\. (.*)$", rito(texto), flags=re.M)
    return [(int(partes[i]), partes[i + 1].strip(), partes[i + 2]) for i in range(1, len(partes), 3)]


def flags_do_script(nome):
    return set(RE_ARG.findall(ler("%s/%s" % (SCRIPTS, nome))))


def comandos(corpo):
    """Cada span de código inline e cada linha de bloco de código: o texto de um comando."""
    spans = re.findall(r"`([^`\n]+)`", re.sub(r"```.*?```", "", corpo, flags=re.S))
    for bloco in re.findall(r"```[^\n]*\n(.*?)```", corpo, re.S):
        spans.extend(bloco.replace("\\\n", " ").splitlines())
    return spans


class TesteSkillLavra(unittest.TestCase):
    def test_frontmatter_e_bloco_injetado(self):
        texto = ler(SKILL)
        m = re.match(r"---\n(.*?)\n---\n", texto, re.S)
        self.assertIsNotNone(m, "SKILL.md sem frontmatter")
        fm = m.group(1)
        self.assertRegex(fm, r"(?m)^name: lavra$")
        self.assertIn("description:", fm)
        for g in GATILHOS:
            self.assertIn(g, fm, f"gatilho ausente da description: {g}")
        dono = RE_BLOCO.search(ler("regras-do-incerto.md"))
        consumidor = RE_BLOCO.search(texto)
        self.assertIsNotNone(consumidor, "SKILL.md não declara o bloco regras-do-incerto")
        self.assertEqual(consumidor.group("papel"), "gerado")
        self.assertIn("gerado de regras-do-incerto.md", consumidor.group(0))
        self.assertEqual(consumidor.group("miolo"), dono.group("miolo"), "bloco divergente do dono")

    def test_oito_passos_na_ordem(self):
        self.assertIsNotNone(rito(ler(SKILL)), "SKILL.md sem seção ## Rito")
        ps = passos(ler(SKILL))
        self.assertEqual([n for n, _, _ in ps], list(range(1, 9)))
        for (n, titulo, _), esperado in zip(ps, PASSOS):
            self.assertTrue(titulo.startswith(esperado), f"passo {n}: {titulo!r} (esperado {esperado!r}…)")

    def test_cada_passo_tem_comando_e_parada(self):
        for n, titulo, corpo in passos(ler(SKILL)):
            self.assertTrue(comandos(corpo), f"passo {n} ({titulo}) sem comando")
            self.assertIn("**Pare", corpo, f"passo {n} ({titulo}) sem condição de parada")

    def test_passos_custosos_exigem_decisao_do_po(self):
        ps = {n: corpo for n, _, corpo in passos(ler(SKILL))}
        for n in CUSTOSOS:
            self.assertIn("decisão do po antes", ps[n].lower(), f"passo {n} gasta dinheiro ou escreve no Aura")
        self.assertIn("nunca move", ps[1])
        self.assertIn("conversao.yml", ps[2])

    def test_scripts_do_rito_existem(self):
        citados = set(RE_SCRIPT.findall(rito(ler(SKILL))))
        self.assertLessEqual(set(RITO_SCRIPTS), citados, "o rito não nomeia todos os scripts da onda")
        for nome in sorted(citados):
            self.assertTrue(os.path.isfile(os.path.join(RAIZ, SCRIPTS, nome)), f"script inexistente: {nome}")

    def test_flags_existem_no_argparse(self):
        texto = ler(SKILL)
        # Comando a comando: toda flag depois do script tem de ser dele.
        for cmd in comandos(sem_bloco(texto)):
            nomes = RE_SCRIPT.findall(cmd)
            if len(nomes) != 1 or not os.path.isfile(os.path.join(RAIZ, SCRIPTS, nomes[0])):
                continue
            depois = cmd.split(nomes[0], 1)[1]
            for flag in RE_FLAG.findall(depois):
                self.assertIn(flag, flags_do_script(nomes[0]), f"{nomes[0]} não tem {flag}: {cmd!r}")
        # Passo a passo: toda flag citada no passo é de algum script do passo.
        for n, titulo, corpo in passos(texto):
            nomes = {s for s in RE_SCRIPT.findall(corpo) if os.path.isfile(os.path.join(RAIZ, SCRIPTS, s))}
            if not nomes:
                continue
            conhecidas = set().union(*(flags_do_script(s) for s in nomes))
            for flag in RE_FLAG.findall(corpo):
                self.assertIn(flag, conhecidas, f"passo {n} ({titulo}): {flag} não é de {sorted(nomes)}")

    def test_guarda_das_flags_nao_e_vazia(self):
        self.assertIn("--aplicar-momentos", flags_do_script("aprovar_onda.py"))
        self.assertIn("--provas-wolfram", flags_do_script("fiscal.py"))
        self.assertNotIn("--executar", flags_do_script("fiscal.py"))
        self.assertEqual(comandos("`a.py --x`\n```\nb.py \\\n  --y\n```"), ["a.py --x", "b.py    --y"])

    def test_devolucao_lista_os_tipos_na_ordem(self):
        texto = ler(DEVOLUCAO)
        titulos = re.findall(r"^### (.*)$", texto, re.M)
        self.assertEqual(len(titulos), 6, titulos)
        for titulo, tipo in zip(titulos, DECISOES):
            self.assertIn(f"`{tipo}`", titulo)
        self.assertIn("Vermelhos", titulos[5])
        self.assertRegex(texto, r"[Vv]ermelho nunca promove")
        self.assertIn("grafo-incerto.md", texto)

    def test_linhas_jsonl_da_devolucao_passam_no_validador(self):
        texto = ler(DEVOLUCAO)
        linhas = [json.loads(l) for bloco in re.findall(r"```jsonl\n(.*?)```", texto, re.S)
                  for l in bloco.splitlines() if l.strip()]
        self.assertEqual({d["tipo"] for d in linhas}, set(DECISOES))
        por_tipo = AO.validar_decisoes(linhas)      # ValueError se alguma linha sair do esquema do dono
        for tipo in DECISOES:
            self.assertTrue(por_tipo[tipo], tipo)
        provas = {d["prova"] for d in por_tipo["aceitar_indeterminado"]}
        self.assertEqual(provas, {"P1", "P2", "P3", "P4"}, "um aceite por forma de linha do fiscal")


if __name__ == "__main__":
    unittest.main()
