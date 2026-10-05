#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 plugin/mcp/busca_semantica.py (adaptado)
"""incerto-consulta — servidor MCP (stdio) de leitura do corpus APROVADO do Incerto, read-only.

Adaptado do `lastro-semantica` (Lastro@1676115): ficaram o laço do protocolo (JSON-RPC por linha), a fusão
RRF e o tratamento de erro acionável; saíram o reranker, as rotas Ollama, as tools do Lastro e a vigência.

Ferramentas (modelo do grafo: skills/lavra/references/grafo-incerto.md, dono único):
  - `buscar_equacao(pergunta, k=5)`: híbrida sobre `:Trecho` — fulltext `trecho_texto_incerto` ∪ vetor
    `trecho_embedding_incerto` (pergunta embedada pelo Vertex, `nucleo.embed_gemini`), fusão RRF (k0=60).
    LOCALIZA, não atesta: devolve `documento`, `topico` e `equacao` (nomes das `:Equacao` aprovadas cuja
    `fonte` é esse par) — nunca o texto do trecho (direito autoral) nem score. Sem Vertex, degrada para
    só o fulltext e diz (`"modo": "lexical"` + `aviso`).
  - `ler_equacao(nome)`: latex, srepr, forma, momento_fechado, variáveis (`USA`), `VALIDA_SOB`,
    `DERIVA_DE` com `verificado_por`, fonte.
  - `ler_conceito(nome)`: definição, sinônimos, heurísticas que o `SUSTENTA`m, equações que o `EXPRESSA`m,
    fonte.
  - `situacao_camada()`: contagem dos nós aprovados por rótulo, trechos, índices presentes e o corpus.

Filtro (o pior defeito deste servidor é devolver staging ou outro corpus): todo nó casado e toda aresta
percorrida exigem `corpus = $corpus` e `status = 'aprovado'` no próprio padrão do Cypher — uma aresta em
staging entre dois nós aprovados não aparece. `:Trecho` é a camada de evidência (sem `status`, entra pelo
portão do PO) e só filtra `corpus`. Não encontrado e não aprovado devolvem a MESMA resposta
(`{"erro": "não encontrada no corpus aprovado"}`), para que a existência em staging não vaze.
`$corpus` = `'incerto'`; `INCERTO_CORPUS` no ambiente troca a partição (só para os testes).

Núcleo: credencial, database e Query API vêm de `skills/lavra/scripts/nucleo.py` (mesmo repositório),
carregado por caminho a partir da raiz do plugin — sem `sys.path` e sem nada fora da árvore. Não usa
`nucleo.abrir_banco`: ele imprime no stdout, que aqui é o canal do protocolo.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import unicodedata

sys.dont_write_bytecode = True   # carregar o núcleo não pode sujar a árvore com __pycache__

PROTOCOLO = "2025-06-18"
NOME_SERVIDOR = "incerto-consulta"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_PADRAO = "incerto"
INDICE_TEXTO = "trecho_texto_incerto"
INDICE_VETORIAL = "trecho_embedding_incerto"
NAO_ENCONTRADA = "não encontrada no corpus aprovado"
POR_ROTA = 20          # candidatos (tópicos) por rota antes da fusão
INFLACAO = 5           # o índice devolve trechos (partes); a fusão trabalha com tópicos
K_PADRAO, K_TETO = 5, 20


def _carregar_nucleo():
    caminho = os.path.join(RAIZ, "skills", "lavra", "scripts", "nucleo.py")
    mod = sys.modules.get("incerto_consulta_nucleo")
    if mod is not None:
        return mod
    spec = importlib.util.spec_from_file_location("incerto_consulta_nucleo", caminho)
    if spec is None or not os.path.exists(caminho):
        raise RuntimeError("núcleo não encontrado em %s — o servidor roda de dentro da árvore do incerto" % caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["incerto_consulta_nucleo"] = mod
    return mod


# Sem núcleo ao alcance o servidor sobe mesmo assim (initialize/tools/list respondem) e cada tool devolve o erro.
try:
    NUC, _FALHA_NUCLEO = _carregar_nucleo(), None
except Exception as e:
    NUC, _FALHA_NUCLEO = None, e

CONTEXTO = None   # (cred, db, consultar) — resolvido na primeira tool e reaproveitado; os testes o preenchem


def corpus():
    return os.environ.get("INCERTO_CORPUS", "").strip() or CORPUS_PADRAO


def versao():
    try:
        with io.open(os.path.join(RAIZ, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f).get("version", "desconhecida")
    except (OSError, ValueError):
        return "desconhecida"


def _contexto():
    """Credencial + database (o home descoberto, nunca presumido) + `consultar(statement, parametros)`.
    Falha na descoberta não é cacheada: a próxima chamada tenta de novo."""
    global CONTEXTO
    if CONTEXTO is None:
        if NUC is None:
            raise RuntimeError("núcleo do incerto indisponível: %s" % _FALHA_NUCLEO)
        cred = NUC.credenciais()                    # sys.exit vira SystemExit — capturada no dispatcher
        db = NUC.database(cred, verboso=False, sair=False)
        if not db:
            raise RuntimeError("database não resolvido — declare NEO4J_DATABASE na credencial "
                               "(ambiente ou ~/.lastro/credencial.txt)")
        with contextlib.redirect_stdout(sys.stderr):   # conferir_marca imprime; o stdout é do protocolo
            try:
                NUC.conferir_marca(cred, db)
            except SystemExit:
                raise RuntimeError("database %r sem a marca exigida (LASTRO_EXIGIR_MARCA) — recusado" % db)
        CONTEXTO = (cred, db, lambda s, p=None: NUC.query_com_retentativa(cred, db, s, p or {}))
    return CONTEXTO


# ---------- Cypher (constantes; valores só em parâmetros) ----------
# Todo nó casado e toda aresta percorrida: `corpus: $corpus` e, fora do :Trecho, `status: 'aprovado'` no padrão.

_EQ = "(e:Equacao {corpus: $corpus, nome: $nome, status: 'aprovado'})"
_CONC = "(c:Conceito {corpus: $corpus, nome: $nome, status: 'aprovado'})"

CYPHER = {
    "busca_lexical": (
        "CALL db.index.fulltext.queryNodes('%s', $q, {limit: $n}) YIELD node AS t, score\n"
        "WHERE t:Trecho AND t.corpus = $corpus\n"
        "RETURN t.documento, t.topico ORDER BY score DESC" % INDICE_TEXTO),
    "busca_vetorial": (
        "CALL db.index.vector.queryNodes('%s', $n, $v) YIELD node AS t, score\n"
        "WHERE t:Trecho AND t.corpus = $corpus\n"
        "RETURN t.documento, t.topico ORDER BY score DESC" % INDICE_VETORIAL),
    "equacoes_das_fontes": (
        "MATCH (e:Equacao {corpus: $corpus, status: 'aprovado'}) WHERE e.fonte IN $fontes\n"
        "RETURN e.fonte, e.nome ORDER BY e.nome"),
    "equacao": (
        "MATCH %s\n"
        "RETURN e.latex, e.sympy_srepr, e.forma, e.momento_fechado, e.faixa_validade, e.fonte" % _EQ),
    "equacao_variaveis": (
        "MATCH %s-[r:USA {corpus: $corpus, status: 'aprovado'}]->"
        "(v:Variavel {corpus: $corpus, status: 'aprovado'})\n"
        "RETURN v.nome, v.simbolo, r.papel, r.simbolos ORDER BY v.nome" % _EQ),
    "equacao_valida_sob": (
        "MATCH %s-[r:VALIDA_SOB {corpus: $corpus, status: 'aprovado'}]->"
        "(v:Variavel {corpus: $corpus, status: 'aprovado'})\n"
        "RETURN r.condicao, v.nome, r.fonte ORDER BY r.condicao, v.nome" % _EQ),
    "equacao_deriva_de": (
        "MATCH %s-[r:DERIVA_DE {corpus: $corpus, status: 'aprovado'}]->"
        "(m:Equacao {corpus: $corpus, status: 'aprovado'})\n"
        "RETURN m.nome, r.passo, r.simbolo, r.substituicao, r.verificado_por, r.fonte ORDER BY m.nome" % _EQ),
    "conceito": (
        "MATCH %s\n"
        "RETURN c.tipo, c.definicao, c.sinonimos, c.fonte" % _CONC),
    "conceito_heuristicas": (
        "MATCH (h:Heuristica {corpus: $corpus, status: 'aprovado'})"
        "-[r:SUSTENTA {corpus: $corpus, status: 'aprovado'}]->%s\n"
        "RETURN h.nome, h.enunciado, h.condicao, h.fonte ORDER BY h.nome" % _CONC),
    "conceito_equacoes": (
        "MATCH (e:Equacao {corpus: $corpus, status: 'aprovado'})"
        "-[r:EXPRESSA {corpus: $corpus, status: 'aprovado'}]->%s\n"
        "RETURN e.nome, e.latex, e.fonte ORDER BY e.nome" % _CONC),
    "contagem_aprovados": (
        "MATCH (n {corpus: $corpus, status: 'aprovado'}) UNWIND labels(n) AS rotulo\n"
        "RETURN rotulo, count(*) ORDER BY rotulo"),
    "contagem_trechos": "MATCH (t:Trecho {corpus: $corpus}) RETURN count(t)",
    "indices": "SHOW INDEXES YIELD name, type, state RETURN name, type, state ORDER BY name",
}


# ---------- utilidades ----------

def escapar_lucene(q):
    """A pergunta é texto livre; o índice fulltext fala Lucene. Sem escapar, `:` ou parêntese viram sintaxe.
    (Mesma regra de `escapar_lucene` de Lastro@1676115 plugin/skills/curadoria/scripts/ingerir_chunks.py.)"""
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)', lambda m: "\\" + m.group(0), q)


def rrf(listas, k0=60):
    """Reciprocal Rank Fusion: funde rankings por POSIÇÃO, não por score — vetor e BM25 vivem em escalas
    incomparáveis, e normalizá-las seria inventar uma equivalência."""
    pontos = {}
    for lista in listas:
        for pos, chave in enumerate(lista, 1):
            pontos[chave] = pontos.get(chave, 0.0) + 1.0 / (k0 + pos)
    return sorted(pontos, key=pontos.get, reverse=True)


def _topicos(linhas):
    """Linhas (documento, topico) de trechos → tópicos distintos, na ordem, até POR_ROTA."""
    return list(dict.fromkeys((l[0], l[1]) for l in linhas))[:POR_ROTA]


def fonte_canonica(documento, topico):
    """O texto de `fonte` como `aprovar_onda.canonico` o grava (grafo-incerto.md)."""
    return json.dumps({"documento": documento, "topico": topico}, sort_keys=True, ensure_ascii=False)


def _json(v):
    """Propriedade composta gravada como JSON canônico (`fonte`, `momento_fechado`, `substituicao`)."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _nome(args):
    nome = (args.get("nome") or "").strip() if isinstance(args.get("nome"), str) else ""
    if not nome:
        raise RuntimeError("nome obrigatório — o nome exato do nó (de buscar_equacao, ou do relato da aprovação)")
    return unicodedata.normalize("NFC", nome)


def _k(args, avisos):
    try:
        k = int(args.get("k", K_PADRAO))
    except (TypeError, ValueError):
        avisos.append("k=%r inválido, usado %d" % (args.get("k"), K_PADRAO))
        return K_PADRAO
    if k > K_TETO:
        avisos.append("k=%d pedido, aparado para %d" % (k, K_TETO))
        return K_TETO
    return max(1, k)


def _resumo(e):
    return "%s: %s" % (type(e).__name__, str(getattr(e, "code", None) if isinstance(e, SystemExit) else e)[:200])


# ---------- ferramentas ----------

def tool_buscar_equacao(args):
    pergunta = args.get("pergunta") if isinstance(args.get("pergunta"), str) else ""
    if not pergunta.strip():
        raise RuntimeError("pergunta obrigatória — o tema ou a equação procurada, em linguagem natural")
    avisos = []
    k = _k(args, avisos)
    cred, _db, consultar = _contexto()
    par = {"corpus": corpus(), "n": POR_ROTA * INFLACAO}
    vetorial = []
    try:
        vetores, _tokens = NUC.embed_gemini(cred, [pergunta])
        if not vetores or vetores[0] is None:
            raise RuntimeError("pergunta acima do limite de tokens do modelo")
        vetorial = _topicos(consultar(CYPHER["busca_vetorial"], dict(par, v=vetores[0])))
        modo = "hibrido"
    except (Exception, SystemExit) as e:   # SystemExit: url_vertex/token_vertex saem sem Vertex
        modo = "lexical"
        avisos.append("sem rota vetorial (%s) — só o fulltext %s" % (_resumo(e), INDICE_TEXTO))
    try:
        lexical = _topicos(consultar(CYPHER["busca_lexical"], dict(par, q=escapar_lucene(pergunta))))
    except Exception as e:
        if modo == "lexical":
            raise
        lexical, modo = [], "vetorial"
        avisos.append("sem rota lexical (%s) — só o vetor %s" % (_resumo(e), INDICE_VETORIAL))
    ordem = rrf([vetorial, lexical])[:k]
    equacoes = {}
    if ordem:
        fontes = [fonte_canonica(d, t) for d, t in ordem]
        for f, nome in consultar(CYPHER["equacoes_das_fontes"], {"corpus": corpus(), "fontes": fontes}):
            equacoes.setdefault(f, []).append(nome)
    r = {"corpus": corpus(), "modo": modo,
         "resultados": [{"documento": d, "topico": t, "equacao": sorted(equacoes.get(fonte_canonica(d, t), []))}
                        for d, t in ordem],
         "regra": "localiza, não atesta: cite (documento, tópico); leia a equação com ler_equacao"}
    if avisos:
        r["aviso"] = " · ".join(avisos)
    return r


def tool_ler_equacao(args):
    nome = _nome(args)
    _cred, _db, consultar = _contexto()
    par = {"corpus": corpus(), "nome": nome}
    linhas = consultar(CYPHER["equacao"], par)
    if not linhas:
        return {"erro": NAO_ENCONTRADA}
    latex, srepr, forma, momento, faixa, fonte = linhas[0]
    return {
        "nome": nome, "status": "aprovado", "latex": latex, "srepr": srepr, "forma": forma,
        "momento_fechado": _json(momento), "faixa_validade": faixa or [],
        "variaveis": [{"nome": n, "simbolo": s, "papel": p, "simbolos": ss}
                      for n, s, p, ss in consultar(CYPHER["equacao_variaveis"], par)],
        "valida_sob": [{"condicao": c, "variavel": v, "fonte": _json(f)}
                       for c, v, f in consultar(CYPHER["equacao_valida_sob"], par)],
        "deriva_de": [{"mae": m, "passo": p, "simbolo": s, "substituicao": _json(sub), "verificado_por": vp or [],
                       "fonte": _json(f)}
                      for m, p, s, sub, vp, f in consultar(CYPHER["equacao_deriva_de"], par)],
        "fonte": _json(fonte),
    }


def tool_ler_conceito(args):
    nome = _nome(args)
    _cred, _db, consultar = _contexto()
    par = {"corpus": corpus(), "nome": nome}
    linhas = consultar(CYPHER["conceito"], par)
    if not linhas:
        return {"erro": NAO_ENCONTRADA}
    tipo, definicao, sinonimos, fonte = linhas[0]
    return {
        "nome": nome, "status": "aprovado", "tipo": tipo, "definicao": definicao, "sinonimos": sinonimos or [],
        "heuristicas": [{"nome": n, "enunciado": e, "condicao": c, "fonte": _json(f)}
                        for n, e, c, f in consultar(CYPHER["conceito_heuristicas"], par)],
        "equacoes": [{"nome": n, "latex": l, "fonte": _json(f)}
                     for n, l, f in consultar(CYPHER["conceito_equacoes"], par)],
        "fonte": _json(fonte),
    }


def tool_situacao_camada(args):
    """Nunca lança por banco fora: diz o que falhou, para a estação declarar a degradação."""
    r = {"corpus": corpus(), "servidor": NOME_SERVIDOR, "versao": versao()}
    try:
        _cred, db, consultar = _contexto()
        r["database"] = db
        r["aprovados"] = {rot: n for rot, n in consultar(CYPHER["contagem_aprovados"], {"corpus": corpus()})}
        r["trechos"] = consultar(CYPHER["contagem_trechos"], {"corpus": corpus()})[0][0]
        presentes = {n: "%s %s" % (t, s) for n, t, s in consultar(CYPHER["indices"], {})}
        r["indices"] = {n: presentes.get(n, "ausente") for n in (INDICE_TEXTO, INDICE_VETORIAL)}
        r["neo4j"] = "ok"
    except (Exception, SystemExit) as e:
        r["neo4j"] = "falha — %s" % _erro_acionavel(getattr(e, "code", None) if isinstance(e, SystemExit) else e)
    return r


_SO_LEITURA = {"readOnlyHint": True, "openWorldHint": False, "idempotentHint": True}

TOOLS = [
    {
        "name": "buscar_equacao",
        "description": "Localiza no corpus aprovado do Incerto os tópicos que tratam do tema (híbrida: fulltext + "
                       "vetor Gemini, fusão RRF). Devolve `documento`, `topico` e `equacao` (lista de nomes das "
                       "equações aprovadas daquela fonte) — nunca o texto do trecho nem score. `modo`: `hibrido`, "
                       "`lexical` quando o Vertex não respondeu, ou `vetorial` quando o fulltext falhou (sempre com "
                       "`aviso`). LOCALIZA, não atesta: leia a "
                       "equação com ler_equacao.",
        "inputSchema": {"type": "object", "properties": {
            "pergunta": {"type": "string", "description": "o tema ou a equação procurada, em linguagem natural"},
            "k": {"type": "integer", "default": K_PADRAO, "minimum": 1, "maximum": K_TETO}},
            "required": ["pergunta"]},
        "annotations": _SO_LEITURA,
    },
    {
        "name": "ler_equacao",
        "description": "Lê uma :Equacao aprovada por nome exato: latex, srepr (SymPy), forma, momento_fechado, "
                       "variáveis (USA), VALIDA_SOB, DERIVA_DE (com verificado_por) e fonte (documento, tópico). "
                       "Só arestas aprovadas entre nós aprovados. Fora do corpus aprovado: "
                       "{\"erro\": \"não encontrada no corpus aprovado\"}.",
        "inputSchema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]},
        "annotations": _SO_LEITURA,
    },
    {
        "name": "ler_conceito",
        "description": "Lê um :Conceito aprovado por nome exato: tipo, definição, sinônimos, heurísticas que o "
                       "SUSTENTAm, equações que o EXPRESSAm e fonte. Só arestas aprovadas entre nós aprovados. "
                       "Fora do corpus aprovado: {\"erro\": \"não encontrada no corpus aprovado\"}.",
        "inputSchema": {"type": "object", "properties": {"nome": {"type": "string"}}, "required": ["nome"]},
        "annotations": _SO_LEITURA,
    },
    {
        "name": "situacao_camada",
        "description": "Saúde da camada: corpus, database, nós aprovados por rótulo, trechos e índices "
                       "(trecho_texto_incerto, trecho_embedding_incerto). Nunca lança — com o Neo4j fora, diz "
                       "o que falhou. Chame primeiro, para declarar degradação.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": _SO_LEITURA,
    },
]

HANDLERS = {"buscar_equacao": tool_buscar_equacao, "ler_equacao": tool_ler_equacao,
            "ler_conceito": tool_ler_conceito, "situacao_camada": tool_situacao_camada}


# ---------- protocolo MCP (stdio, JSON-RPC por linha) ----------

def _resp(id_, resultado=None, erro=None):
    m = {"jsonrpc": "2.0", "id": id_}
    if erro is not None:
        m["error"] = erro
    else:
        m["result"] = resultado
    sys.stdout.write(json.dumps(m, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _erro_acionavel(e):
    """Mensagem que orienta o próximo passo, nunca só 'falhou'."""
    txt = str(e)
    dicas = []
    if "Connection refused" in txt or "getaddrinfo" in txt or "URLError" in type(e).__name__:
        dicas.append("o Neo4j responde? (NEO4J_URI / NEO4J_QUERY_URL na credencial; situacao_camada diagnostica)")
    if "Credencial incompleta" in txt:
        dicas.append("exporte NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD ou preencha ~/.lastro/credencial.txt")
    if "Unauthorized" in txt or "401" in txt:
        dicas.append("NEO4J_USERNAME/NEO4J_PASSWORD conferem com a instância?")
    return txt + ((" · próximo passo: " + "; ".join(dicas)) if dicas else "")


def main():
    # Windows: stdin/stdout nascem em cp1252, e o protocolo MCP é UTF-8.
    for fluxo in (sys.stdin, sys.stdout):
        if hasattr(fluxo, "reconfigure"):
            try:
                fluxo.reconfigure(encoding="utf-8")
            except Exception:
                pass
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            msg = json.loads(linha)
        except ValueError:
            continue
        metodo, id_ = msg.get("method"), msg.get("id")
        if metodo == "initialize":
            _resp(id_, {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", PROTOCOLO),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": NOME_SERVIDOR, "version": versao()}})
        elif metodo == "tools/list":
            _resp(id_, {"tools": TOOLS})
        elif metodo == "tools/call":
            nome = (msg.get("params") or {}).get("name")
            args = (msg.get("params") or {}).get("arguments") or {}
            if nome not in HANDLERS:
                _resp(id_, erro={"code": -32602, "message": "tool desconhecida: %r" % nome})
                continue
            try:
                r = HANDLERS[nome](args)
                _resp(id_, {"content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False, indent=1)}],
                            "isError": False})
            except (Exception, SystemExit) as e:   # SystemExit: credenciais() usa sys.exit
                detalhe = getattr(e, "code", None) if isinstance(e, SystemExit) else e
                _resp(id_, {"content": [{"type": "text", "text": _erro_acionavel(detalhe)}], "isError": True})
        elif metodo == "ping":
            _resp(id_, {})
        elif id_ is not None:
            _resp(id_, erro={"code": -32601, "message": "método não suportado: %r" % metodo})
        # notificações (sem id) são aceitas em silêncio


if __name__ == "__main__":
    main()
