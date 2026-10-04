#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/skills/lavra/scripts/conferir_onda.py
"""Conferência de uma onda do `mineiro` e portão do PO entre `extraidos/` e `conferidos/` (V3.3, V4.1).

Lê `<raiz>/extraidos/<onda>/` (o bucket montado em `/mnt/corpus`, ou uma cópia em disco) e confere cada
documento contra o contrato de `references/extracao-nuvem.md` (dono único): o par `<nome>.<ext>.md` +
`.report.json`, o relatório legível, `summary.equacoes.validador == "katex"` quando há equação detectada
(`null` só com `equacoes_detectadas == 0`), nenhum LaTeX inválido no fim, nenhuma perda silenciosa e
nenhuma página sem camada de texto saída vazia. Fallback com a marca `[fallback]` no ponto do `.md` é
perda declarada: não reprova, é relatado por rota.

Imprime o relatório de fidelidade ao PO (resumo, por rota, equações, perdas declaradas, veredito por
documento). Com `--aprovar`, grava `manifesto.json` em `extraidos/<onda>/` e copia os aptos (`.md`,
`.report.json`, `.assets/`) e o manifesto para `conferidos/<onda>/`; `--recusar <nome>=<motivo>` deixa
um apto de fora por decisão do PO. Nunca apaga `extraidos/` e nunca reescreve `conferidos/`.

Tudo vem dos `.report.json`; o `lote-<data>.md` nunca é lido (o `rerender` do mineiro não o regrava).
Parseáveis pelo SymPy: medido pela função de parse do `extrair_equacoes.py` (Task 8), por import local,
sem `sympy` neste arquivo (decisão 1b do PO, 28/09); "não medido" só se esse import (ou o do `sympy`) falhar.
Só biblioteca padrão. Não converte nada: o conversor é o `mineiro`.

Uso:
    python3 skills/lavra/scripts/conferir_onda.py --raiz <corpus> --onda <onda> [--aprovar] [--recusar <nome>=<motivo> ...]
Saída: 0 com todos os documentos aptos; 1 com algum reprovado ou recusado; 2 em erro de uso ou conflito
com conferidos/.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys

RE_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RE_LOTE = re.compile(r"^lote-\d{4}-\d{2}-\d{2}\.md$")
RE_EXTENSAO_DE_ORIGEM = re.compile(r"^.+\.[A-Za-z0-9]{1,8}$")
RE_NOTA_DE_PAGINA = re.compile(r"\[fallback\] páginas? \d+(-\d+)? não convertida")
SUF_MD, SUF_REL = ".md", ".report.json"
MARCA_FALLBACK = "[fallback]"
MONTAGEM = "/mnt/corpus/"          # onde o job monta o bucket; o `source` dos relatórios começa aqui
MANIFESTO = "manifesto.json"
CAMPOS_EQ = ("equacoes_detectadas", "via_parse", "via_gemini", "via_codeformula", "fallback_imagem", "texto_mantido",
             "latex_original_mantido", "descritas", "com_erro", "resgatadas_de_texto", "descartadas",
             "latex_invalido_1a_tentativa", "latex_invalido_final")


class Conflito(Exception):
    """O portão copiaria algo diferente do que já está em conferidos/<onda>/."""


def _bytes(nome):
    return nome.encode("utf-8")


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


def documentos(pasta):
    """Nomes `<nome>.<ext>` da onda (pelo `.md` ou pelo `.report.json`), ordenados por bytes; sem o lote."""
    nomes = set()
    for a in os.listdir(pasta):
        if not os.path.isfile(os.path.join(pasta, a)):
            continue
        if a.endswith(SUF_REL):
            nomes.add(a[:-len(SUF_REL)])
        elif a.endswith(SUF_MD) and not RE_LOTE.match(a):
            nomes.add(a[:-len(SUF_MD)])
    return sorted(nomes, key=_bytes)


def _ultimo_feedback(item):
    tentativas = item.get("attempts") or []
    return str((tentativas[-1] or {}).get("feedback") or "") if tentativas else ""


def _conferir_relatorio(rel, md, motivos, perdas):
    summary, items = rel["summary"], rel["items"]
    if summary.get("itens") != len(items):
        motivos.append("summary.itens = %r, mas o relatório tem %d item(ns)" % (summary.get("itens"), len(items)))

    eq = summary.get("equacoes")
    if not isinstance(eq, dict):
        motivos.append("relatório sem summary.equacoes")
        eq = {}
    else:
        detectadas = eq.get("equacoes_detectadas") or 0
        validador = eq.get("validador")
        if detectadas > 0 and validador != "katex":
            motivos.append("%d equação(ões) detectada(s) com summary.equacoes.validador = %s; o contrato exige "
                           "\"katex\"" % (detectadas, json.dumps(validador)))
        if (eq.get("latex_invalido_final") or 0) > 0:
            motivos.append("summary.equacoes.latex_invalido_final = %d" % eq["latex_invalido_final"])

    for item in items:
        iid, rota = item.get("item_id"), item.get("route")
        final = item.get("final") or ""
        if item.get("fallback"):
            if MARCA_FALLBACK not in final:
                motivos.append("perda silenciosa: %s (%s) em fallback sem a marca %s" % (iid, rota, MARCA_FALLBACK))
            elif final.strip() not in md:
                motivos.append("perda silenciosa: o fallback de %s (%s) não está no .md" % (iid, rota))
            else:
                perdas.append({"item": iid, "rota": rota, "motivo": _ultimo_feedback(item)})
        elif not item.get("approved"):
            motivos.append("perda silenciosa: %s (%s) não aprovado e sem fallback" % (iid, rota))

    parse = summary.get("parse") or {}
    if (parse.get("paginas_sem_texto") or 0) > 0:
        motivos.append("summary.parse.paginas_sem_texto = %d: página sem camada de texto saiu vazia e sem marca "
                       "(reconverter com gemini_pdf)" % parse["paginas_sem_texto"])
    falhas = parse.get("paginas_falhas") or 0
    if falhas > 0:
        if RE_NOTA_DE_PAGINA.search(md):
            erros = [str(e) for e in summary.get("erros") or [] if "página" in str(e)]
            perdas.append({"item": "%d página(s)" % falhas, "rota": "parse", "motivo": "; ".join(erros)})
        else:
            motivos.append("perda silenciosa: summary.parse.paginas_falhas = %d sem a nota [fallback] no .md" % falhas)
    return eq


def conferir_documento(pasta, nome):
    """Confere um documento `<nome>.<ext>` da onda. Devolve o registro do documento (veredito, motivos,
    perdas, hashes e o que o manifesto cita); `_relatorio` guarda o JSON lido para o relatório da onda."""
    motivos, perdas = [], []
    doc = {"documento": nome, "veredito": "reprovado", "motivos": motivos, "perdas": perdas,
           "sha256_md": None, "sha256_report": None, "original": None, "engine": None,
           "model_versions": [], "validador": None, "equacoes_detectadas": 0, "_relatorio": None, "_md": None}
    if not RE_EXTENSAO_DE_ORIGEM.match(nome):
        motivos.append("nome sem a extensão de origem (esperado <nome>.<ext>.md, ex.: Relatorio.pdf.md)")
    c_md, c_rel = os.path.join(pasta, nome + SUF_MD), os.path.join(pasta, nome + SUF_REL)
    faltam = [os.path.basename(c) for c in (c_md, c_rel) if not os.path.isfile(c)]
    if faltam:
        motivos.append("falta o par: %s" % ", ".join(faltam))
        return doc
    doc["sha256_md"], doc["sha256_report"] = _sha256(c_md), _sha256(c_rel)
    try:
        with io.open(c_md, encoding="utf-8") as f:
            md = f.read()
    except UnicodeDecodeError as e:
        motivos.append(".md fora de UTF-8: %s" % e)
        return doc
    try:
        with io.open(c_rel, encoding="utf-8") as f:
            rel = json.load(f)
        if not isinstance(rel, dict) or not all(k in rel for k in ("source", "summary", "items")) \
                or not isinstance(rel["summary"], dict) or not isinstance(rel["items"], list):
            raise ValueError("sem source, summary ou items")
    except ValueError as e:
        motivos.append("relatório ilegível: %s" % e)
        return doc
    doc["_relatorio"] = rel
    doc["_md"] = md
    doc["original"] = rel["source"]
    doc["engine"] = (rel["summary"].get("parse") or {}).get("engine")
    doc["model_versions"] = sorted(rel["summary"].get("model_versions") or [], key=_bytes)
    eq = _conferir_relatorio(rel, md, motivos, perdas)
    doc["validador"] = eq.get("validador")
    doc["equacoes_detectadas"] = eq.get("equacoes_detectadas") or 0
    if not motivos:
        doc["veredito"] = "apto"
    return doc


def ler_onda(pasta):
    """Confere todos os documentos de `extraidos/<onda>/`, em ordem de bytes do nome."""
    return [conferir_documento(pasta, nome) for nome in documentos(pasta)]


def validar_nome(nome):
    """Nome de onda ou de fonte: letras, dígitos, `.`, `_`, `-`; sem `/`, `..` nem vírgula (separador dos
    `--args` do `gcloud run jobs execute`). Mesma regra do `.github/workflows/conversao.yml`."""
    if not RE_NOME.match(nome or "") or ".." in nome:
        raise ValueError("nome inválido: %r (use letras, dígitos, '.', '_' e '-'; sem '/', '..' nem vírgula)" % nome)
    return nome


# ---------- relatório de fidelidade ----------

def _ordenado(d):
    return {k: d[k] for k in sorted(d, key=_bytes)}


def parseaveis_sympy(docs):
    """`{"parseaveis", "total"}` dos blocos `$$…$$` dos `.md` legíveis, pela definição estrita de "parseável"
    do `extrair_equacoes.py` (decisão 2 do PO, 28/09); None só se o import dele ou do `sympy` falhar."""
    try:
        from extrair_equacoes import equacoes_do_documento, parsear_latex   # vizinho; decisão 1b
        n = total = 0
        for d in docs:
            if d.get("_md") is None:
                continue
            for eq in equacoes_do_documento(d["_md"], d["documento"] + SUF_MD):
                total += 1
                n += 1 if parsear_latex(eq["latex"])["ok"] else 0
    except ImportError:
        return None
    return {"parseaveis": n, "total": total}


def resumir(docs):
    """Totais da onda somados dos `.report.json` legíveis (inclusive dos reprovados), nunca do lote."""
    r = {"documentos": len(docs), "aptos": sum(d["veredito"] == "apto" for d in docs), "itens": 0,
         "aprovados": 0, "fallbacks": 0, "tokens": {}, "segundos": 0.0, "segundos_parede": 0.0,
         "mermaid_valido": 0, "mermaid_total": 0, "model_versions": [], "custo_usd": None, "custo_parcial": False}
    r["reprovados"] = r["documentos"] - r["aptos"]
    rotas, eq, modelos, custos = {}, dict.fromkeys(CAMPOS_EQ, 0), set(), []
    eq.update(documentos_com_equacao=0, documentos_katex=0, parseaveis_sympy=parseaveis_sympy(docs))
    paginas_falhas = 0
    for d in docs:
        rel = d["_relatorio"]
        if rel is None:
            continue
        s = rel["summary"]
        for item in rel["items"]:
            rota = rotas.setdefault(str(item.get("route")), {"itens": 0, "fallbacks": 0, "nao_aprovados": 0})
            rota["itens"] += 1
            rota["fallbacks"] += 1 if item.get("fallback") else 0
            rota["nao_aprovados"] += 0 if item.get("approved") else 1
            r["itens"] += 1
            r["aprovados"] += 1 if item.get("approved") else 0
            r["fallbacks"] += 1 if item.get("fallback") else 0
            if item.get("route") == "mermaid":
                r["mermaid_total"] += 1
                r["mermaid_valido"] += 1 if ((item.get("metrics") or {}).get("mermaid_valido") or 0) >= 1 else 0
        for k, v in (s.get("tokens") or {}).items():
            r["tokens"][k] = r["tokens"].get(k, 0) + v
        r["segundos"] += s.get("segundos") or 0.0
        r["segundos_parede"] += s.get("segundos_parede") or 0.0
        modelos.update(s.get("model_versions") or [])
        e = s.get("equacoes") if isinstance(s.get("equacoes"), dict) else {}
        for k in CAMPOS_EQ:
            eq[k] += e.get(k) or 0
        if (e.get("equacoes_detectadas") or 0) > 0:
            eq["documentos_com_equacao"] += 1
            eq["documentos_katex"] += 1 if e.get("validador") == "katex" else 0
        if s.get("custo_estimado_usd") is not None:
            custos.append(s["custo_estimado_usd"])
            r["custo_parcial"] = r["custo_parcial"] or bool(s.get("custo_parcial"))
        else:
            r["custo_parcial"] = True
        paginas_falhas += (s.get("parse") or {}).get("paginas_falhas") or 0
    rotas["parse"] = {"itens": None, "fallbacks": paginas_falhas, "nao_aprovados": None}
    r["fallbacks"] += paginas_falhas
    r["por_rota"] = _ordenado(rotas)
    r["equacoes"] = eq
    r["tokens"] = _ordenado(r["tokens"]) if r["tokens"] else {}
    r["segundos"], r["segundos_parede"] = round(r["segundos"], 1), round(r["segundos_parede"], 1)
    r["model_versions"] = sorted(modelos, key=_bytes)
    if custos:
        r["custo_usd"] = round(sum(custos), 6)
    else:
        r["custo_parcial"] = False
    return r


def _horas(segundos):
    return ("%.2f h (%.1f s)" % (segundos / 3600.0, segundos)).replace(".", ",")


def _cel(texto):
    return str(texto).replace("|", "¦").replace("\n", " ")


def relatorio_md(onda, docs, r):
    """Relatório de fidelidade ao PO, em Markdown, só com o que os `.report.json` dizem."""
    tok = r["tokens"]
    custo = "não informado (`cost_usd` nulo: sem preços em `prices` na config do mineiro)" if r["custo_usd"] is None \
        else "US$ %.4f%s" % (r["custo_usd"], " (parcial: há documento sem preço)" if r["custo_parcial"] else "")
    eq = r["equacoes"]
    L = ["# Conferência da onda `%s`" % onda, "",
         "Fonte: os `.report.json` de `extraidos/%s/` (o `lote-*.md` não é lido). Conversor: `mineiro`." % onda, "",
         "## Resumo", "", "| medida | valor |", "|---|---|",
         "| documentos | %d (%d aptos, %d reprovados) |" % (r["documentos"], r["aptos"], r["reprovados"]),
         "| itens | %d (%d aprovados, %d em fallback) |" % (r["itens"], r["aprovados"], r["fallbacks"]),
         "| Mermaid válido | %d de %d |" % (r["mermaid_valido"], r["mermaid_total"]),
         "| tokens | %s |" % " · ".join("%s %d" % (k, v) for k, v in tok.items()),
         "| tempo de modelo | %s |" % _horas(r["segundos"]),
         "| tempo de parede (soma dos documentos) | %s |" % _horas(r["segundos_parede"]),
         "| custo | %s |" % custo,
         "| modelos | %s |" % (", ".join(r["model_versions"]) or "—"),
         "", "## Por rota", "", "| rota | itens | fallbacks | não aprovados |", "|---|---|---|---|"]
    for rota, c in r["por_rota"].items():
        nome = "parse (páginas)" if rota == "parse" else rota
        L.append("| %s | %s | %d | %s |" % (nome, "—" if c["itens"] is None else c["itens"], c["fallbacks"],
                                           "—" if c["nao_aprovados"] is None else c["nao_aprovados"]))
    L += ["", "## Equações", "", "| medida | valor |", "|---|---|",
          "| detectadas | %d |" % eq["equacoes_detectadas"],
          "| LaTeX via parse / Gemini / CodeFormula | %d / %d / %d |" % (eq["via_parse"], eq["via_gemini"], eq["via_codeformula"]),
          "| perdas: imagem / texto mantido / descritas / com erro | %d / %d / %d / %d |" % (
              eq["fallback_imagem"], eq["texto_mantido"], eq["descritas"], eq["com_erro"]),
          "| LaTeX inválido na 1ª tentativa / no fim | %d / %d |" % (eq["latex_invalido_1a_tentativa"], eq["latex_invalido_final"]),
          "| documentos com equação validados pelo KaTeX | %d de %d |" % (eq["documentos_katex"], eq["documentos_com_equacao"]),
          "| parseáveis pelo SymPy | %s |" % ("não medido: `extrair_equacoes.py` ou `sympy` indisponível (decisão 1b do PO)"
                                               if eq["parseaveis_sympy"] is None else
                                               "%d/%d" % (eq["parseaveis_sympy"]["parseaveis"], eq["parseaveis_sympy"]["total"])),
          "", "## Perdas declaradas", ""]
    perdas = [(d["documento"], p) for d in docs for p in d["perdas"]]
    if perdas:
        L += ["| documento | item | rota | motivo |", "|---|---|---|---|"]
        L += ["| %s | %s | %s | %s |" % (_cel(doc), _cel(p["item"]), _cel(p["rota"]), _cel(p["motivo"] or "—"))
              for doc, p in perdas]
    else:
        L.append("Nenhuma.")
    L += ["", "## Veredito por documento", "",
          "| documento | itens | equações | validador | fallbacks | veredito | motivos |", "|---|---|---|---|---|---|---|"]
    for d in docs:
        rel = d["_relatorio"]
        itens = len(rel["items"]) if rel else "—"
        L.append("| %s | %s | %d | %s | %d | %s | %s |" % (
            _cel(d["documento"]), itens, d["equacoes_detectadas"], d["validador"] or "—", len(d["perdas"]),
            "✔ apto" if d["veredito"] == "apto" else "✘ " + d["veredito"], _cel("; ".join(d["motivos"]) or "—")))
    return "\n".join(L) + "\n"


# ---------- manifesto e portão ----------

def _sha256_original(raiz, original):
    if not original or not str(original).startswith(MONTAGEM):
        return None
    caminho = os.path.join(raiz, *str(original)[len(MONTAGEM):].split("/"))
    return _sha256(caminho) if os.path.isfile(caminho) else None


def manifesto(raiz, onda, docs, resumo):
    """Manifesto da onda: o que foi conferido, com hashes e motivos; sem timestamp (determinismo)."""
    campos = ("documento", "veredito", "motivos", "perdas", "sha256_md", "sha256_report", "original", "engine",
              "model_versions", "validador", "equacoes_detectadas")
    documentos_ = []
    for d in docs:
        x = {k: d[k] for k in campos}
        x["sha256_original"] = _sha256_original(raiz, d["original"])
        documentos_.append(x)
    return {"onda": onda, "ferramenta": "mineiro", "resumo": resumo, "documentos": documentos_}


def json_manifesto(m):
    return json.dumps(m, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _arquivos_do_documento(pasta, nome):
    """Caminhos relativos (separador `/`) do que o portão copia de um documento."""
    rels = [nome + SUF_MD, nome + SUF_REL]
    assets = os.path.join(pasta, nome + ".assets")
    if os.path.isdir(assets):
        for base, subpastas, arquivos in os.walk(assets):
            subpastas.sort(key=_bytes)
            for a in sorted(arquivos, key=_bytes):
                rels.append(os.path.relpath(os.path.join(base, a), pasta).replace(os.sep, "/"))
    return rels


def _mesmo_conteudo(a, b):
    return _sha256(a) == _sha256(b)


def aprovar(raiz, onda, docs, recusas):
    """Portão do PO. Aplica as recusas, confere conflito com `conferidos/<onda>/` antes de escrever
    qualquer coisa, grava o manifesto em `extraidos/<onda>/` e copia os aptos e o manifesto para
    `conferidos/<onda>/`. Arquivo de documento já copiado nunca é reescrito (diferença é `Conflito`); o
    manifesto é o registro da conferência e é regravado. Devolve os aptos (copiados ou já idênticos lá)."""
    validar_nome(onda)
    nomes = {d["documento"] for d in docs}
    desconhecidos = sorted(set(recusas) - nomes, key=_bytes)
    if desconhecidos:
        raise ValueError("recusa de documento que não está na onda: %s" % ", ".join(desconhecidos))
    for d in docs:
        if d["documento"] in recusas:
            motivo = "PO: %s" % recusas[d["documento"]]
            if d["veredito"] == "apto":
                d["veredito"], d["motivos"][:] = "recusado_pelo_po", [motivo]
            else:
                d["motivos"].append(motivo)
    ext = os.path.join(raiz, "extraidos", onda)
    conf = os.path.join(raiz, "conferidos", onda)
    aptos = [d["documento"] for d in docs if d["veredito"] == "apto"]
    texto = json_manifesto(manifesto(raiz, onda, docs, resumir(docs)))

    conflitos, copiar = [], []
    for nome in aptos:
        for rel in _arquivos_do_documento(ext, nome):
            origem, destino = os.path.join(ext, *rel.split("/")), os.path.join(conf, *rel.split("/"))
            if os.path.exists(destino):
                if not _mesmo_conteudo(origem, destino):
                    conflitos.append("%s difere do que o portão copiaria" % rel)
            else:
                copiar.append((origem, destino))
    if os.path.isdir(conf):
        for nome in documentos(conf):
            if nome not in aptos:
                conflitos.append("%s já está em conferidos e agora ficaria de fora" % nome)
    if conflitos:
        raise Conflito("conferidos/%s não se reescreve: %s" % (onda, "; ".join(conflitos)))

    with io.open(os.path.join(ext, MANIFESTO), "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    if aptos:
        for origem, destino in copiar:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copyfile(origem, destino)
        with io.open(os.path.join(conf, MANIFESTO), "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
    return aptos


# ---------- execução ----------

def _recusa(texto):
    nome, sep, motivo = texto.partition("=")
    if not sep or not nome or not motivo.strip():
        raise argparse.ArgumentTypeError("use --recusar <nome>=<motivo>")
    return nome, motivo.strip()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", required=True, help="raiz do corpus (com extraidos/ e conferidos/), ex.: /mnt/corpus")
    ap.add_argument("--onda", required=True, help="nome da onda (pasta em extraidos/)")
    ap.add_argument("--aprovar", action="store_true", help="grava o manifesto e copia os aptos para conferidos/<onda>/")
    ap.add_argument("--recusar", action="append", type=_recusa, default=[], metavar="NOME=MOTIVO",
                    help="deixa um documento apto de fora, por decisão do PO (repetível; só com --aprovar)")
    args = ap.parse_args(argv)
    try:
        validar_nome(args.onda)
    except ValueError as e:
        print("ERRO: %s" % e, file=sys.stderr)
        return 2
    pasta = os.path.join(os.path.abspath(args.raiz), "extraidos", args.onda)
    if not os.path.isdir(pasta):
        print("ERRO: onda não encontrada: %s" % pasta, file=sys.stderr)
        return 2
    if args.recusar and not args.aprovar:
        print("ERRO: --recusar só vale com --aprovar", file=sys.stderr)
        return 2
    docs = ler_onda(pasta)
    if args.aprovar:
        try:
            aprovados = aprovar(os.path.abspath(args.raiz), args.onda, docs, dict(args.recusar))
        except (Conflito, ValueError) as e:
            print("ERRO: %s" % e, file=sys.stderr)
            return 2
    print(relatorio_md(args.onda, docs, resumir(docs)), end="")
    if args.aprovar:
        print("\nPortão: manifesto gravado em extraidos/%s/%s; %d documento(s) em conferidos/%s/." % (
            args.onda, MANIFESTO, len(aprovados), args.onda))
    return 0 if all(d["veredito"] == "apto" for d in docs) else 1


if __name__ == "__main__":
    sys.exit(main())
