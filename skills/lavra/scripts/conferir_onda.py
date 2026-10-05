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
`.report.json`, `.assets/`, o sidecar de reparo) e o manifesto para `conferidos/<onda>/`;
`--recusar <nome>=<motivo>` deixa um apto de fora por decisão do PO. Nunca apaga `extraidos/` e nunca
reescreve `conferidos/`.

Reparo de páginas (decisão do PO de 05/10): com o sidecar `<nome>.<ext>.reparos.json` do `emendar_paginas.py`,
o sha256 do `.md` tem de ser o de depois do último reparo (senão, "md alterado fora do reparo"); as páginas
reparadas saem de `paginas_falhas` e a mensagem resolvida sai das perdas; os itens e as equações do reparo
entram nas mesmas regras e nas contagens; o relatório ganha a seção "Reparos" e o `--aprovar` copia o sidecar.
Sem sidecar, nada muda.

Tudo vem dos `.report.json`; o `lote-<data>.md` nunca é lido (o `rerender` do mineiro não o regrava).
Parseáveis pelo SymPy: medido pela função de parse do `extrair_equacoes.py` (Task 8), por import local,
sem `sympy` neste arquivo (decisão 1b do PO, 28/09); "não medido" só se esse import (ou o do `sympy`) falhar.
Cada parse roda sob o limite de tempo de parede do `limite_sympy.py` (equação que estoura conta como não
parseável, `nao_suportado:tempo_esgotado`); `INCERTO_LIMITE_SYMPY_S` inválido derruba o portão (ValueError).
Só biblioteca padrão. Não converte nada: o conversor é o `mineiro`.

Uso:
    python3 skills/lavra/scripts/conferir_onda.py --raiz <corpus> --onda <onda> [--aprovar] [--recusar <nome>=<motivo> ...]
Saída: 0 com todos os documentos aptos; 1 com algum reprovado ou recusado; 2 em erro de uso ou conflito
com conferidos/.
"""
import argparse
import copy
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
SUF_REPAROS = ".reparos.json"         # sidecar do emendar_paginas.py (reparo de páginas, decisão do PO de 05/10)
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


def _conferir_equacoes(eq, motivos, onde=""):
    detectadas = eq.get("equacoes_detectadas") or 0
    validador = eq.get("validador")
    if detectadas > 0 and validador != "katex":
        motivos.append("%d equação(ões) detectada(s)%s com summary.equacoes.validador = %s; o contrato exige "
                       "\"katex\"" % (detectadas, onde, json.dumps(validador)))
    if (eq.get("latex_invalido_final") or 0) > 0:
        motivos.append("summary.equacoes.latex_invalido_final = %d%s" % (eq["latex_invalido_final"], onde))


def _conferir_relatorio(rel, md, motivos, perdas, reparos=()):
    """Regras do contrato de consumo. Com `reparos` (o sidecar do `emendar_paginas.py`), os itens e as
    equações do reparo entram nas mesmas regras e as páginas reparadas saem das `paginas_falhas`."""
    summary, items = rel["summary"], rel["items"]
    if summary.get("itens") != len(items):
        motivos.append("summary.itens = %r, mas o relatório tem %d item(ns)" % (summary.get("itens"), len(items)))

    eq = summary.get("equacoes")
    if not isinstance(eq, dict):
        motivos.append("relatório sem summary.equacoes")
        eq = {}
    else:
        _conferir_equacoes(eq, motivos)
    for r in reparos:
        if isinstance(r["equacoes"], dict):
            _conferir_equacoes(r["equacoes"], motivos, " no reparo das páginas %s" % r["paginas"])
        else:
            motivos.append("reparo das páginas %s sem equacoes" % r["paginas"])

    for item in itens_do_documento(rel, reparos):
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
    falhas = paginas_falhas(rel, reparos)
    if falhas < 0:
        motivos.append("os reparos cobrem %d página(s) a mais que summary.parse.paginas_falhas" % -falhas)
    if falhas > 0:
        if RE_NOTA_DE_PAGINA.search(md):
            resolvidos = {str(e) for r in reparos for e in r["erros_resolvidos"]}
            erros = [str(e) for e in summary.get("erros") or [] if "página" in str(e) and str(e) not in resolvidos]
            perdas.append({"item": "%d página(s)" % falhas, "rota": "parse", "motivo": "; ".join(erros)})
        else:
            motivos.append("perda silenciosa: summary.parse.paginas_falhas = %d sem a nota [fallback] no .md" % falhas)
    return eq


def itens_do_documento(rel, reparos=()):
    """Os itens do relatório do `mineiro` seguidos dos itens dos reparos (ids já prefixados pelo sidecar)."""
    return list(rel["items"]) + [i for r in reparos for i in r["items"]]


def paginas_falhas(rel, reparos=()):
    """`summary.parse.paginas_falhas` menos as páginas que os reparos cobrem."""
    falhas = (rel["summary"].get("parse") or {}).get("paginas_falhas") or 0
    return falhas - sum(paginas_da_faixa(r) for r in reparos)


RELATORIO_CONFERIDO = "conferido"


def _conferir_registro(pasta, nome, md, r, motivos):
    """Um registro do sidecar contra o que está no disco (o sidecar não se abona sozinho). Sempre: um só par
    de marcadores com a onda e o sha256 do registro, nenhuma nota `[fallback]` da faixa e os assets com o
    sha256 registrado. Se o relatório do reparo está em `<raiz>/extraidos/<onda-reparo>/`: o sha256 dele e
    os campos rederivados (`CAMPOS_DERIVADOS`), e, com o `.md` do reparo, o sha256 dele e o trecho emendado.
    Devolve o estado da conferência com o relatório (para a seção "Reparos")."""
    a, b = r["pagina_inicial"], r["pagina_final"]
    onde = "reparo das páginas %s" % r["paginas"]
    abre, fecha = marcadores_do_reparo(a, b, r["onda_reparo"], r["sha256_report_reparo"])
    padrao_abre = re.compile(r"<!-- reparo: %s, " % re.escape(rotulo_faixa(a, b)))
    i, j = md.find(abre), md.find(fecha)
    if len(padrao_abre.findall(md)) != 1 or md.count(abre) != 1 or md.count(fecha) != 1 or j < i:
        motivos.append("%s: o .md não tem exatamente um par de marcadores com a onda e o sha256 do registro" % onde)
        i = j = -1
    if re_nota_da_faixa(a, b).search(md):
        motivos.append("%s: a nota [fallback] de %s continua no .md" % (onde, rotulo_faixa(a, b)))
    for x in r["assets"]:
        c = os.path.join(pasta, nome + ".assets", *x["destino"].split("/"))
        if not os.path.isfile(c) or _sha256(c) != x["sha256"]:
            motivos.append("%s: asset %s.assets/%s ausente ou diferente do registrado" % (onde, nome, x["destino"]))

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(pasta)))
    pasta_r = os.path.join(raiz, "extraidos", r["onda_reparo"])
    c_rel_r = os.path.join(pasta_r, r["documento_reparo"] + SUF_REL)
    if not os.path.isfile(c_rel_r):
        return "não encontrado em extraidos/%s/: conferência com o relatório pulada" % r["onda_reparo"]
    if _sha256(c_rel_r) != r["sha256_report_reparo"]:
        motivos.append("%s: o sha256 do relatório do reparo em extraidos/%s/ não é o do registro"
                       % (onde, r["onda_reparo"]))
        return "divergente"
    mapa = {x["origem"]: x["destino"] for x in r["assets"]}
    try:
        with io.open(c_rel_r, encoding="utf-8") as f:
            derivado = derivar_registro(json.load(f), r["documento_reparo"], nome, a, b, mapa)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        motivos.append("%s: relatório do reparo ilegível: %s" % (onde, e))
        return "divergente"
    divergentes = [k for k in CAMPOS_DERIVADOS if derivado[k] != r[k]]
    if "items" in divergentes:
        motivos.append("%s: os items do sidecar não são os do relatório do reparo" % onde)
    outros = [k for k in divergentes if k != "items"]
    if outros:
        motivos.append("%s: %s do sidecar não batem com o relatório do reparo" % (onde, ", ".join(outros)))
    c_md_r = os.path.join(pasta_r, r["documento_reparo"] + SUF_MD)
    if os.path.isfile(c_md_r):
        if _sha256(c_md_r) != r["sha256_md_reparo"]:
            motivos.append("%s: o sha256 do .md do reparo não é o do registro" % onde)
            divergentes.append("md")
        elif i >= 0:
            with io.open(c_md_r, encoding="utf-8", newline="") as f:
                try:
                    esperado = reescritor(r["documento_reparo"], nome, mapa)(f.read()).strip("\r\n")
                except ValueError as e:
                    esperado = None
                    motivos.append("%s: %s" % (onde, e))
            if esperado is not None and md[i + len(abre):j].strip("\r\n") != esperado:
                motivos.append("%s: o trecho entre os marcadores não é o .md do reparo" % onde)
                divergentes.append("trecho")
    return "divergente" if divergentes else RELATORIO_CONFERIDO


def _conferir_reparos(sha_md, reparos, motivos):
    """O `.md` atual tem de ser o de depois do último reparo, e cada reparo parte do de depois do anterior."""
    for anterior, r in zip(reparos, reparos[1:]):
        if r["sha256_md_antes"] != anterior["sha256_md_depois"]:
            motivos.append("md alterado fora do reparo: o reparo das páginas %s não parte do .md de depois do "
                           "reparo das páginas %s" % (r["paginas"], anterior["paginas"]))
    if reparos and reparos[-1]["sha256_md_depois"] != sha_md:
        motivos.append("md alterado fora do reparo: o sha256 do .md não é o de depois do último reparo "
                       "(páginas %s)" % reparos[-1]["paginas"])


def conferir_documento(pasta, nome):
    """Confere um documento `<nome>.<ext>` da onda. Devolve o registro do documento (veredito, motivos,
    perdas, hashes e o que o manifesto cita); `_relatorio` guarda o JSON lido para o relatório da onda."""
    motivos, perdas = [], []
    doc = {"documento": nome, "veredito": "reprovado", "motivos": motivos, "perdas": perdas,
           "sha256_md": None, "sha256_report": None, "original": None, "engine": None,
           "model_versions": [], "validador": None, "equacoes_detectadas": 0, "_relatorio": None, "_md": None,
           "_reparos": [], "_reparos_relatorio": [], "reparos": None}
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
    try:
        reparos = ler_reparos(pasta, nome)
    except ValueError as e:
        motivos.append(str(e))           # sidecar ilegível: confere sem ele, e o documento já não é apto
        reparos = None
    if reparos:
        doc["_reparos"] = reparos
        doc["reparos"] = {"sha256": _sha256(os.path.join(pasta, nome + SUF_REPAROS)),
                          "paginas": [r["paginas"] for r in reparos]}
        _conferir_reparos(doc["sha256_md"], reparos, motivos)
        doc["_reparos_relatorio"] = [_conferir_registro(pasta, nome, md, r, motivos) for r in reparos]
    doc["original"] = rel["source"]
    doc["engine"] = (rel["summary"].get("parse") or {}).get("engine")
    doc["model_versions"] = sorted(rel["summary"].get("model_versions") or [], key=_bytes)
    eq = _conferir_relatorio(rel, md, motivos, perdas, doc["_reparos"])
    doc["validador"] = eq.get("validador")
    if not eq.get("equacoes_detectadas"):          # alvo sem equação: o validador é o do reparo que as tem
        doc["validador"] = next((r["equacoes"].get("validador") for r in doc["_reparos"]
                                 if isinstance(r["equacoes"], dict) and r["equacoes"].get("equacoes_detectadas")),
                                doc["validador"])
    doc["equacoes_detectadas"] = (eq.get("equacoes_detectadas") or 0) + sum(
        (r["equacoes"] or {}).get("equacoes_detectadas") or 0 for r in doc["_reparos"])
    if not motivos:
        doc["veredito"] = "apto"
    return doc


CAMPOS_REPARO = ("paginas", "pagina_inicial", "pagina_final", "onda_reparo", "documento_reparo", "sha256_report_reparo",
                 "sha256_md_reparo", "sha256_md_antes", "sha256_md_depois", "items", "equacoes", "erros_resolvidos",
                 "assets", "source", "sha256_original", "tokens", "segundos", "segundos_parede", "custo_estimado_usd")
# campos do registro que o portão rederiva do relatório do reparo quando ele está em extraidos/<onda-reparo>/
CAMPOS_DERIVADOS = ("items", "equacoes", "source", "tokens", "segundos", "segundos_parede", "custo_estimado_usd")


def codigo_faixa(a, b):
    return "%d" % a if a == b else "%d-%d" % (a, b)


def rotulo_faixa(a, b):
    """Como o `mineiro` escreve a faixa na nota `[fallback]`: `páginas A-B`, ou `página A`."""
    return "página %d" % a if a == b else "páginas %d-%d" % (a, b)


def prefixo_reparo(a, b):
    return "reparo-p%s-" % codigo_faixa(a, b)


def re_nota_da_faixa(a, b):
    return re.compile(r"^>\s*⚠️\s*\[fallback\] %s não convertida" % re.escape(rotulo_faixa(a, b)), re.M)


def marcadores_do_reparo(a, b, onda_reparo, sha256_report):
    rot = rotulo_faixa(a, b)
    return ("<!-- reparo: %s, onda %s, relatório sha256 %s -->" % (rot, onda_reparo, sha256_report),
            "<!-- fim do reparo: %s -->" % rot)


def reescritor(documento_reparo, documento, mapa):
    """Função que troca `<documento_reparo>.assets/<rel>` por `<documento>.assets/<mapa[rel]>`; referência
    a asset fora de `mapa` é ValueError."""
    padrao = re.compile(re.escape(documento_reparo + ".assets/") + r"([^\s)\"'<>\]]+)")

    def trocar(texto):
        def um(m):
            if m.group(1) not in mapa:
                raise ValueError("o reparo cita %s.assets/%s, que não existe na onda de reparo"
                                 % (documento_reparo, m.group(1)))
            return documento + ".assets/" + mapa[m.group(1)]
        return padrao.sub(um, texto)
    return trocar


def derivar_registro(rel_r, documento_reparo, documento, a, b, mapa):
    """Os campos do registro que vêm do relatório do reparo (`CAMPOS_DERIVADOS`): os items com id prefixado
    e `final` com as referências de asset reescritas, `summary.equacoes`, `source`, tokens, tempos e custo.
    Fonte única para o `emendar_paginas.py` (que grava) e para o portão (que confere)."""
    pre, trocar = prefixo_reparo(a, b), reescritor(documento_reparo, documento, mapa)
    items = []
    for item in rel_r["items"]:
        x = copy.deepcopy(item)
        x["item_id"] = pre + str(item.get("item_id"))
        if isinstance(x.get("final"), str):
            x["final"] = trocar(x["final"])
        items.append(x)
    s = rel_r["summary"]
    return {"items": items, "equacoes": s.get("equacoes"), "source": rel_r.get("source"),
            "tokens": s.get("tokens") or {}, "segundos": s.get("segundos"), "segundos_parede": s.get("segundos_parede"),
            "custo_estimado_usd": s.get("custo_estimado_usd")}


def _asset_valido(a, pre):
    return isinstance(a, dict) and all(isinstance(a.get(k), str) for k in ("origem", "destino", "sha256")) \
        and a["destino"] == pre + a["origem"] and not a["origem"].startswith("/") \
        and ".." not in a["origem"].split("/")


def ler_reparos(pasta, nome):
    """Os registros do sidecar `<nome>.reparos.json` (gravado só pelo `emendar_paginas.py`), em ordem de
    aplicação; None sem sidecar. Sidecar ilegível ou fora do formato é ValueError."""
    caminho = os.path.join(pasta, nome + SUF_REPAROS)
    if not os.path.isfile(caminho):
        return None
    try:
        with io.open(caminho, encoding="utf-8") as f:
            reparos = json.load(f)
        if not isinstance(reparos, list) or not reparos:
            raise ValueError("esperada uma lista não vazia de registros")
        for r in reparos:
            if not isinstance(r, dict) or any(k not in r for k in CAMPOS_REPARO) \
                    or not isinstance(r["items"], list) or not all(isinstance(i, dict) for i in r["items"]) \
                    or not isinstance(r["erros_resolvidos"], list) or not isinstance(r["assets"], list) \
                    or not isinstance(r["pagina_inicial"], int) or not isinstance(r["pagina_final"], int) \
                    or not 1 <= r["pagina_inicial"] <= r["pagina_final"] \
                    or r["paginas"] != codigo_faixa(r["pagina_inicial"], r["pagina_final"]) \
                    or not all(_asset_valido(a, prefixo_reparo(r["pagina_inicial"], r["pagina_final"]))
                               for a in r["assets"]):
                raise ValueError("registro fora do formato (campos %s)" % ", ".join(CAMPOS_REPARO))
    except ValueError as e:
        raise ValueError("%s%s ilegível: %s" % (nome, SUF_REPAROS, e))
    return reparos


def paginas_da_faixa(reparo):
    return reparo["pagina_final"] - reparo["pagina_inicial"] + 1


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
    do `extrair_equacoes.py` (decisão 2 do PO, 28/09); None só se o import dele ou do `sympy` falhar.
    Chama `parsear_latex` SEM funções declaradas: o portão mede antes da rodada do PO, e as decisões
    `declarar_funcoes` (que mudam o que parseia) só entram depois, na extração (`extrair_equacoes.py --decisoes`)."""
    try:
        from extrair_equacoes import equacoes_do_documento, parsear_latex   # vizinho; decisão 1b
        n = total = 0
        for d in docs:
            if d.get("_md") is None:
                continue
            for eq in equacoes_do_documento(d["_md"], d["documento"] + SUF_MD):
                total += 1
                try:
                    n += 1 if parsear_latex(eq["latex"])["ok"] else 0
                except (ImportError, ValueError):
                    raise                   # ValueError: `INCERTO_LIMITE_SYMPY_S` inválido — falha alto
                except Exception:
                    pass                    # erro inesperado do parse: conta como não parseável, nunca derruba o portão
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
    falhas = 0
    for d in docs:
        rel = d["_relatorio"]
        if rel is None:
            continue
        s, reparos = rel["summary"], d.get("_reparos") or []
        for item in itens_do_documento(rel, reparos):
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
        partes = [s.get("equacoes")] + [r["equacoes"] for r in reparos]
        partes = [e for e in partes if isinstance(e, dict)]
        for e in partes:
            for k in CAMPOS_EQ:
                eq[k] += e.get(k) or 0
        com_equacao = [e for e in partes if (e.get("equacoes_detectadas") or 0) > 0]
        if com_equacao:
            eq["documentos_com_equacao"] += 1
            eq["documentos_katex"] += 1 if all(e.get("validador") == "katex" for e in com_equacao) else 0
        if s.get("custo_estimado_usd") is not None:
            custos.append(s["custo_estimado_usd"])
            r["custo_parcial"] = r["custo_parcial"] or bool(s.get("custo_parcial"))
        else:
            r["custo_parcial"] = True
        falhas += max(0, paginas_falhas(rel, reparos))
    rotas["parse"] = {"itens": None, "fallbacks": falhas, "nao_aprovados": None}
    r["fallbacks"] += falhas
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


def _tokens(tok):
    return " · ".join("%s %d" % (k, tok[k]) for k in sorted(tok, key=_bytes)) or "—"


def _linha_custo_com_reparos(docs, r):
    """A linha "custo total incluindo reparos", só quando há reparo (os números da onda não mudam)."""
    custos = [x["custo_estimado_usd"] for d in docs for x in d.get("_reparos") or []]
    if not custos:
        return []
    conhecidos = [c for c in custos if c is not None] + ([r["custo_usd"]] if r["custo_usd"] is not None else [])
    if not conhecidos:
        return ["| custo total incluindo reparos | não informado |"]
    parcial = r["custo_usd"] is None or r["custo_parcial"] or None in custos
    return ["| custo total incluindo reparos | US$ %.4f%s |" % (
        sum(conhecidos), " (parcial: há documento ou reparo sem preço)" if parcial else "")]


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
         "| custo | %s |" % custo] + _linha_custo_com_reparos(docs, r) + [
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
    reparos = [(d["documento"], r, estado) for d in docs
               for r, estado in zip(d.get("_reparos") or [], d.get("_reparos_relatorio") or [])]
    if reparos:
        L += ["", "## Reparos", "",
              "Páginas reconvertidas numa onda de reparo e emendadas no `.md` pelo `emendar_paginas.py` "
              "(sidecar `<documento>%s`; o `.report.json` do `mineiro` não muda). Tokens e tempo são os do "
              "relatório do reparo; os números da onda acima não os incluem." % SUF_REPAROS, "",
              "| documento | páginas | onda de origem | documento do reparo | sha256 do relatório do reparo | "
              "sha256 do .md antes | sha256 do .md depois | relatório do reparo | tokens | tempo de parede |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        L += ["| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(_cel(x) for x in (
            doc, r["paginas"], r["onda_reparo"], r["documento_reparo"], r["sha256_report_reparo"],
            r["sha256_md_antes"], r["sha256_md_depois"], estado, _tokens(r["tokens"]),
            _horas(r["segundos_parede"] or 0.0))) for doc, r, estado in reparos]
    L += ["", "## Veredito por documento", "",
          "| documento | itens | equações | validador | fallbacks | veredito | motivos |", "|---|---|---|---|---|---|---|"]
    for d in docs:
        rel = d["_relatorio"]
        itens = len(itens_do_documento(rel, d.get("_reparos") or [])) if rel else "—"
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
        if d.get("reparos"):
            x["reparos"] = d["reparos"]
        documentos_.append(x)
    return {"onda": onda, "ferramenta": "mineiro", "resumo": resumo, "documentos": documentos_}


def json_manifesto(m):
    return json.dumps(m, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _arquivos_do_documento(pasta, nome):
    """Caminhos relativos (separador `/`) do que o portão copia de um documento."""
    rels = [nome + SUF_MD, nome + SUF_REL]
    if os.path.isfile(os.path.join(pasta, nome + SUF_REPAROS)):
        rels.append(nome + SUF_REPAROS)
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
