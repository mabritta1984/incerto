#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/verificar_jazida.py
"""Verificador frio do Incerto — um comando, todas as provas baratas, sai 1 se qualquer uma reprovar.

Adaptado do `verificar_jazida.py` (Lastro@1676115): mesma forma de prova registrada, tabela e código de
saída; aqui a raiz do plugin é a raiz do repositório e nada fora dela é consultado.

Uso, a partir da raiz do repositório:
    python3 -B build/verificar_incerto.py [--raiz .]

Provas: versão (aceita `-dev`), sintaxe por `ast.parse` (sem `py_compile`, que escreve __pycache__),
ausência de import cruzado (prefixo de nome e caminho em carregadores), dependência fora da biblioteca
padrão só dentro de função e só nos arquivos permitidos (decisão A6), nenhuma chave de conta de serviço
nem rota de chave da API generativa, e blocos de dono único em sincronia (o injetor deste repositório,
por subprocesso). Só biblioteca padrão.
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
PROVAS = []

RE_VERSAO = re.compile(r"^\d+\.\d+\.\d+(-dev)?$")
# Dependências fora da biblioteca padrão (pinadas em build/requisitos.txt) → arquivos que podem importá-las,
# relativos à raiz. Sempre dentro de função. Os testes (build/testes/) podem importar as declaradas.
PERMITIDOS = ("skills/lavra/scripts/extrair_equacoes.py", "skills/lavra/scripts/fiscal.py")
DEPENDENCIAS_PERMITIDAS = {"sympy": PERMITIDOS, "antlr4": PERMITIDOS, "mpmath": PERMITIDOS}
PREFIXO_TESTES = "build/testes/"
CARREGADORES = {"spec_from_file_location", "SourceFileLoader", "run_path", "load_source", "import_module"}
FORA_DA_ARVORE = ("plugin", "jazida", "lastro", "mineiro", "..")
PREFIXOS_PROIBIDOS = ("plugin", "jazida", "lastro", "mineiro")
# Os planos e especificações citam as agulhas como texto; não são código nem configuração.
PASTAS_DE_PROSA = ("docs/superpowers",)
IGNORADAS = ("__pycache__", ".git", ".superpowers", "worktrees")
# Montadas por concatenação: o grep não pode achar o próprio verificador.
AGULHAS = ("private" + "_key", "BEGIN " + "PRIVATE KEY",
           "generative" + "language.googleapis.com", "GEMINI_EMBEDDING" + "_KEY")


def prova(nome):
    def dec(fn):
        PROVAS.append((nome, fn))
        return fn
    return dec


def _rel(caminho, base):
    return os.path.relpath(caminho, base).replace(os.sep, "/")


def _pys(raiz):
    saida = []
    for pasta, subpastas, arquivos in os.walk(raiz):
        subpastas[:] = sorted(s for s in subpastas if s not in IGNORADAS)
        saida += [os.path.join(pasta, a) for a in sorted(arquivos) if a.endswith(".py")]
    return saida


def _arvore(caminho):
    with io.open(caminho, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=caminho)


def _ler_json(*partes):
    with io.open(os.path.join(*partes), encoding="utf-8") as f:
        return json.load(f)


# ---------- provas ----------

@prova("versão: plugin.json = marketplace = README = regras (X.Y.Z ou X.Y.Z-dev)")
def prova_versao(raiz):
    v = _ler_json(raiz, ".claude-plugin", "plugin.json").get("version", "")
    problemas = [] if RE_VERSAO.match(v) else ["versão %r fora do formato X.Y.Z[-dev]" % v]
    plugins = _ler_json(raiz, ".claude-plugin", "marketplace.json").get("plugins", [])
    if len(plugins) != 1:
        problemas.append("marketplace: %d entrada(s), esperada 1" % len(plugins))
    elif plugins[0].get("version") != v:
        problemas.append("marketplace: %s" % plugins[0].get("version"))
    with io.open(os.path.join(raiz, "README.md"), encoding="utf-8") as f:
        m = re.search(r"\*\*Versão:\*\*\s*`([^`]+)`", f.read())
    if not m or m.group(1) != v:
        problemas.append("README.md: %s" % (m.group(1) if m else "sem **Versão:**"))
    with io.open(os.path.join(raiz, "regras-do-incerto.md"), encoding="utf-8") as f:
        m = re.search(r"fonte única \(v([^)]+)\)", f.read())
    if not m or m.group(1) != v:
        problemas.append("regras-do-incerto.md: %s" % (m.group(1) if m else "sem cabeçalho de versão"))
    return not problemas, ("v%s" % v) if not problemas else "; ".join(problemas)


@prova("sintaxe de todos os .py do incerto (ast.parse)")
def prova_sintaxe(raiz):
    erros, n = [], 0
    for c in _pys(raiz):
        n += 1
        try:
            _arvore(c)
        except SyntaxError as e:
            erros.append("%s: %s" % (_rel(c, raiz), e.msg))
    return not erros, "; ".join(erros) or "%d arquivo(s)" % n


def _textos(no):
    """Constantes de texto e nomes dentro de uma expressão (argumentos de um carregador)."""
    for x in ast.walk(no):
        if isinstance(x, ast.Constant) and isinstance(x.value, str):
            yield x.value
        elif isinstance(x, ast.Attribute) and x.attr == "pardir":
            yield ".."


def _nome_chamado(no):
    f = no.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


@prova("sem import cruzado: nada de plugin/jazida/lastro/mineiro; sem carregador ou sys.path para fora")
def prova_import_cruzado(raiz):
    locais = {os.path.splitext(os.path.basename(c))[0] for c in _pys(raiz)}
    proibidos = set(PREFIXOS_PROIBIDOS) - locais
    achados = []
    for c in _pys(raiz):
        rel = _rel(c, raiz)
        for no in ast.walk(_arvore(c)):
            if isinstance(no, ast.Import):
                achados += ["%s:%d import %s" % (rel, no.lineno, a.name) for a in no.names if a.name.split(".")[0] in proibidos]
            elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0 and no.module.split(".")[0] in proibidos:
                achados.append("%s:%d from %s" % (rel, no.lineno, no.module))
            elif isinstance(no, ast.Call) and _nome_chamado(no) in CARREGADORES:
                alvo = [t for a in list(no.args) + [k.value for k in no.keywords] for t in _textos(a)]
                if any(p in t.replace("\\", "/").split("/") or t == p for t in alvo for p in FORA_DA_ARVORE):
                    achados.append("%s:%d %s para fora do incerto" % (rel, no.lineno, _nome_chamado(no)))
            elif isinstance(no, ast.Attribute) and no.attr == "path" and isinstance(no.value, ast.Name) \
                    and no.value.id == "sys":
                achados.append("%s:%d sys.path" % (rel, no.lineno))
    return not achados, "; ".join(achados[:8]) or "nenhum import cruzado"


def _pais(arvore):
    pai = {}
    for no in ast.walk(arvore):
        for filho in ast.iter_child_nodes(no):
            pai[filho] = no
    return pai


def _dentro_de_funcao(no, pai):
    while no in pai:
        no = pai[no]
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
    return False


@prova("dependências fora da biblioteca padrão: só dentro de função e só nos arquivos permitidos (A6)")
def prova_dependencias(raiz):
    locais = {os.path.splitext(os.path.basename(c))[0] for c in _pys(raiz)}
    padrao = set(sys.stdlib_module_names) | {"__future__"}
    achados = []
    for c in _pys(raiz):
        rel = _rel(c, raiz)
        arvore = _arvore(c)
        pai = _pais(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                mods = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                mods = [no.module]
            else:
                continue
            for mod in mods:
                topo = mod.split(".")[0]
                if topo in padrao or topo in locais:
                    continue
                if topo not in DEPENDENCIAS_PERMITIDAS:
                    achados.append("%s:%d %s não declarada" % (rel, no.lineno, mod))
                elif rel not in DEPENDENCIAS_PERMITIDAS[topo] and not rel.startswith(PREFIXO_TESTES):
                    achados.append("%s:%d %s fora dos arquivos permitidos" % (rel, no.lineno, mod))
                elif not _dentro_de_funcao(no, pai):
                    achados.append("%s:%d %s no topo do módulo (importe dentro de função)" % (rel, no.lineno, mod))
    return not achados, "; ".join(achados[:8]) or "só biblioteca padrão fora das exceções declaradas"


def _arquivos_de_texto(raiz):
    for pasta, subpastas, arquivos in os.walk(raiz):
        subpastas[:] = sorted(s for s in subpastas if s not in IGNORADAS)
        if _rel(pasta, raiz) in PASTAS_DE_PROSA:
            subpastas[:] = []
            continue
        for a in sorted(arquivos):
            caminho = os.path.join(pasta, a)
            try:
                with io.open(caminho, encoding="utf-8") as f:
                    yield caminho, f.read()
            except (UnicodeDecodeError, OSError):
                continue


@prova("sem chave de conta de serviço e sem rota de chave da API generativa")
def prova_segredos(raiz):
    achados, n = [], 0
    for caminho, texto in _arquivos_de_texto(raiz):
        n += 1
        achados += ["%s (%s)" % (_rel(caminho, raiz), a) for a in AGULHAS if a in texto]
    return not achados, "; ".join(achados[:8]) or "%d arquivo(s) de texto limpos" % n


@prova("blocos de dono único em sincronia (build/injetar_regras.py --check --bloco-obrigatorio regras-do-incerto)")
def prova_blocos(raiz):
    injetor = os.path.join(raiz, "build", "injetar_regras.py")
    r = subprocess.run([sys.executable, "-B", injetor, "--check", "--raiz", raiz, "--bloco-obrigatorio", "regras-do-incerto"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    linhas = [l for l in (r.stdout or r.stderr).splitlines() if l.strip()]
    return r.returncode == 0, linhas[-1] if linhas else "(sem saída)"


# ---------- execução ----------

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=".", help="raiz do incerto (default: .)")
    args = ap.parse_args()
    raiz = os.path.abspath(args.raiz)
    if not os.path.isfile(os.path.join(raiz, ".claude-plugin", "plugin.json")):
        sys.exit("ERRO: %s não parece a raiz do incerto (falta .claude-plugin/plugin.json)" % raiz)
    reprovadas = 0
    print("| prova | resultado | detalhe |\n|---|---|---|")
    for nome, fn in PROVAS:
        try:
            ok, detalhe = fn(raiz)
        except Exception as e:
            ok, detalhe = False, "exceção: %s: %s" % (type(e).__name__, e)
        reprovadas += 0 if ok else 1
        print("| %s | %s | %s |" % (nome, "✔" if ok else "✘", str(detalhe).replace("|", "¦")))
    print("\n%s" % ("INCERTO APROVADO" if not reprovadas else "INCERTO REPROVADO — %d prova(s)" % reprovadas))
    return 1 if reprovadas else 0


if __name__ == "__main__":
    sys.exit(main())
