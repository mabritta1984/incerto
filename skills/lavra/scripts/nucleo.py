# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/skills/lavra/scripts/nucleo.py — arquivo próprio do incerto, sem sincronização
"""Núcleo do Incerto: credencial, sonda, Query API, chave NFC e embedding Gemini pelo Vertex AI.

Arquivo próprio do Incerto, copiado do núcleo da Jazida; evolui aqui, sem cópia automática.
Vieram do ingestor do Lastro: CHAVES, TENTATIVAS, ORIGEM_CRED, _ler_arquivo_cred, host_da_uri, sem_localhost, base_query, url_ollama, eh_falha_de_transporte, eh_recusa_de_credencial, database, CYPHER_MARCA, conferir_marca, abrir_banco, chave, plano_nfc, normalizar, _eh_local, _erro_legivel, _abrir, _via_proxy_connect, registrar_ocorrencia, _tabela_bloqueio, sonda, linhas_sonda, verificar_ollama, modelo_baixado, query_api, query_com_retentativa, GEMINI_MODELO, GEMINI_DIM, GEMINI_LIMITE_TOKENS.
Ajustada: credenciais.
Rota Vertex no lugar de: GEMINI_URL, _chamar_gemini, embed_gemini (D5: endpoint global, Bearer, sem chave).
"""
import base64
import concurrent.futures
import glob as globmod
import io
import json
import os
import re
import socket
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


CHAVES = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")


TENTATIVAS = 4


ORIGEM_CRED = {}   # P-AB: chave → "ambiente" | "arquivo <caminho>" — de onde veio, nunca o valor


def _ler_arquivo_cred(caminho, dados):
    with io.open(caminho, encoding="utf-8-sig") as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k not in dados:
                    dados[k] = v
                    ORIGEM_CRED[k] = "arquivo %s" % caminho
                elif k in CHAVES and ORIGEM_CRED.get(k) == "ambiente" and dados[k] != v:
                    # P-AB: foi a precedência do ambiente que mascarou a credencial boa do ~/.lastro.
                    print("⚠️ %s do ambiente difere da declarada em %s — vale a do ambiente"
                          % (k, caminho), file=sys.stderr)


def credenciais():
    # Incerto: do ambiente também a trava da base de testes e o projeto Google Cloud
    # (INCERTO_*); a rota de embedding é o Vertex com o token do ambiente, sem chave de API (D5)
    dados = {k: v for k, v in os.environ.items()
             if k.startswith(("NEO4J_", "VERTEX_", "EMBED_", "OLLAMA_", "INCERTO_")) or k in ("LASTRO_EXIGIR_MARCA",)}
    ORIGEM_CRED.clear()
    ORIGEM_CRED.update({k: "ambiente" for k in dados})
    tentados = ["variáveis de ambiente (NEO4J_URI...)"]
    candidatos = []
    if os.environ.get("LASTRO_CRED"):
        candidatos.append(os.environ["LASTRO_CRED"])
    candidatos += sorted(globmod.glob("/sessions/*/mnt/.lastro/credencial.txt"))
    candidatos += sorted(globmod.glob("/sessions/*/mnt/*/.lastro/credencial.txt"))
    candidatos.append(os.path.join(os.path.expanduser("~"), ".lastro", "credencial.txt"))
    if os.environ.get("USERPROFILE"):
        candidatos.append(os.path.join(os.environ["USERPROFILE"], ".lastro", "credencial.txt"))
    for c in dict.fromkeys(candidatos):
        tentados.append(c)
        if os.path.exists(c):
            _ler_arquivo_cred(c, dados)
    faltando = [k for k in CHAVES if not dados.get(k)]
    if faltando:
        sys.exit("Credencial incompleta (faltam: %s). Caminhos tentados, em ordem:\n  - %s\n"
                 "Conecte a pasta .lastro à sessão ou exporte as variáveis."
                 % (", ".join(faltando), "\n  - ".join(tentados)))
    return dados


def host_da_uri(uri):
    m = re.match(r"^[a-z0-9+]+://([^/:]+)", uri.strip())
    return m.group(1) if m else uri.strip().split("/")[0].split(":")[0]


def sem_localhost(url):
    """DS-4 (0.20.16): `http://localhost…` → `http://127.0.0.1…`. No Windows, `localhost` resolve primeiro
    para ::1, e o serviço que só escuta IPv4 cobra a tentativa perdida a cada conexão. Só em http:// —
    em https o certificado é do nome, e o IP quebraria a verificação TLS."""
    return re.sub(r"^http://localhost(?=[:/]|$)", "http://127.0.0.1", url)


def base_query(cred):
    """Base da Query API: NEO4J_QUERY_URL (local: http://localhost:7474) ou https://host."""
    if cred.get("NEO4J_QUERY_URL"):
        return sem_localhost(cred["NEO4J_QUERY_URL"].rstrip("/"))
    return "https://" + host_da_uri(cred["NEO4J_URI"])


def url_ollama(cred):
    """Base do Ollama: OLLAMA_URL ou o padrão local, sem `localhost` (DS-4)."""
    return sem_localhost((cred.get("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/"))


def eh_falha_de_transporte(e):
    """P-AC: o banco não chegou a responder — recusa de conexão, DNS, tempo esgotado. Resposta HTTP,
    mesmo 5xx, NÃO é transporte: o servidor respondeu e o erro é dele (fica como reprovação)."""
    if isinstance(e, urllib.error.HTTPError):
        return False
    if isinstance(e, urllib.error.URLError):
        return True
    return isinstance(e, (ConnectionError, TimeoutError, socket.gaierror))


def eh_recusa_de_credencial(e):
    """P-AB: 401/403/429 ou os códigos de segurança do Neo4j — nada foi provado sobre a base."""
    return getattr(e, "code", None) in (401, 403, 429) or any(
        m in str(e) for m in ("Security.Unauthorized", "Security.AuthenticationRateLimit"))


def database(cred, consultar=None, verboso=True, levantar_sem_resposta=False, sair=True):
    """Nome do database: NEO4J_DATABASE declarado vence; sem ele, o HOME do usuário —
    descoberto no `system`, nunca presumido `neo4j` (armadilha do toró 2: script lê banco
    vazio em silêncio e reporta sucesso). Quem chama imprime qual usou. `sair=False` (MCP):
    devolve None onde o script sairia com a tabela — quem chama dá o erro, sem palpite."""
    if cred.get("NEO4J_DATABASE"):
        nome, origem = cred["NEO4J_DATABASE"], "declarado"
    else:
        if consultar is None:
            consultar = lambda s, p: query_api(cred, "system", s, p)
        try:
            linhas = consultar("SHOW DATABASES YIELD name, home WHERE home RETURN name", {})
        except Exception as e:
            if levantar_sem_resposta and (eh_falha_de_transporte(e) or eh_recusa_de_credencial(e)):
                raise
            linhas, erro = [], e
        else:
            erro = None
        if not linhas:
            if not sair:
                return None
            sys.exit("database não resolvido — declare NEO4J_DATABASE na credencial.\n"
                     "| testado | primitiva | resposta |\n|---|---|---|\n"
                     "| NEO4J_DATABASE | credencial | ausente |\n"
                     "| home database | SHOW DATABASES YIELD name, home WHERE home (db system) | %s |"
                     % (("erro: %s" % erro) if erro else "nenhuma linha"))
        nome, origem = linhas[0][0], "home descoberto"
    if verboso:
        print("database: %s (%s)" % (nome, origem))
    return nome


CYPHER_MARCA = "MATCH (m:MarcaInstancia {nome: $n}) RETURN count(m)"


def conferir_marca(cred, db):
    """Sem a chave, não consulta nada. Com ela, recusa (exit 2) o database sem a marca."""
    marca = str(cred.get("LASTRO_EXIGIR_MARCA") or "").strip()
    if not marca:
        return
    if not query_api(cred, db, CYPHER_MARCA, {"n": marca})[0][0]:
        print("base sem a marca '%s' — recusando (database em uso: %s)" % (marca, db))
        sys.exit(2)


def abrir_banco(explicito=None, sem_resposta="sair"):
    """U3: abertura única do banco nos scripts → (cred, db, consultar). `explicito` (`--database`) vence;
    senão a resolução de `database()`, que relança transporte e credencial recusada — nunca presume
    `neo4j`. Banco mudo: com sem_resposta="sair", SEM RESPOSTA + diário + exit 2 (P-AC); com
    "levantar", relança para quem tem mensagem própria (migrar, fiscal)."""
    cred = credenciais()
    if explicito:
        print("database: %s (declarado (--database))" % explicito)
        cred, db = dict(cred, NEO4J_DATABASE=explicito), explicito
    else:
        try:
            db = database(cred, levantar_sem_resposta=True)
        except Exception as e:
            if sem_resposta == "levantar" or not (eh_falha_de_transporte(e) or eh_recusa_de_credencial(e)):
                raise
            motivo = "credencial recusada" if eh_recusa_de_credencial(e) else "banco não respondeu"
            msg = ("SEM RESPOSTA — %s (%s: %s) — nada foi lido nem gravado: suba a instância ou corrija a "
                   "credencial e rode de novo" % (motivo, type(e).__name__, e))
            print("\n" + msg)
            registrar_ocorrencia(cred, os.path.basename(sys.argv[0] or "") or "script", "abertura do banco",
                                 msg, "nada executado; banco não consultado")
            sys.exit(2)
    conferir_marca(cred, db)
    return cred, db, lambda s, p=None: query_api(cred, db, s, p or {})


def chave(s, caminho=True):
    """P-AL: forma canônica de toda chave de documento/tópico — NFC (nome vindo de macOS/zip chega
    em NFD e deixa de casar com o índice em silêncio) e, para caminho, separador POSIX. Dono único:
    recorte, ingestão, migração, fiscal, estrutura e MCP comparam só por esta forma."""
    s = unicodedata.normalize("NFC", s or "")
    return s.replace("\\", "/") if caminho else s


def plano_nfc(linhas, campos_texto, campos_chave):
    """Plano da migração única para `chave()` (P-AL). Nó cuja chave nova já pertence a outro nó — ou a
    outra troca do mesmo plano — é COLISÃO: não troca, e a operação inteira aborta antes de gravar
    (fundir dois nós é decisão do PO, nunca efeito colateral de normalização)."""
    ocupadas = {}
    for i, c in linhas:
        ocupadas.setdefault(tuple(c[k] for k in campos_chave), set()).add(i)
    trocas, colisoes = [], []
    for i, c in linhas:
        novos = {k: chave(c[k], caminho=cam) for k, cam in campos_texto.items() if c.get(k)}
        mudou = {k: v for k, v in novos.items() if v != c[k]}
        if not mudou:
            continue
        k = tuple(mudou.get(x, c[x]) for x in campos_chave)
        if ocupadas.get(k, set()) - {i}:
            colisoes.append((i, k))
            continue
        ocupadas.setdefault(k, set()).add(i)
        trocas.append((i, mudou))
    return trocas, colisoes


def normalizar(s):
    """Forma de casamento do vocabulário: NFD sem marcas, minúsculas, espaços colapsados.
    Dono único — `ligar_estrutura.py` (MENCIONA) e o MCP (expansão da pergunta) usam esta."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"\s+", " ", s).strip()


def _eh_local(host):
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")


def _erro_legivel(e):
    """P-P: `HTTPError` com o corpo do Neo4j na mensagem — `code: message` de cada erro do JSON
    da Query API; corpo não-JSON vai truncado. Sem isto o 400 chega mudo ao traceback."""
    try:
        corpo = e.read().decode("utf-8", "replace")
    except Exception:
        return e
    try:
        erros = json.loads(corpo).get("errors") or []
        detalhe = "; ".join("%s: %s" % (x.get("code"), x.get("message")) for x in erros) or corpo[:400]
    except (ValueError, AttributeError):
        detalhe = corpo[:400]
    return urllib.error.HTTPError(e.url, e.code, "%s — %s" % (e.reason, detalhe), e.headers, None)


def _abrir(req, timeout):
    """urlopen que NÃO passa pelo proxy quando o alvo é local (o proxy não rotearia); erro HTTP
    volta com a mensagem do servidor (P-P)."""
    host = urllib.parse.urlparse(req.full_url).hostname or ""
    try:
        if _eh_local(host):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise _erro_legivel(e) from None


def _via_proxy_connect(host, porta, timeout=8):
    """CONNECT autenticado através do proxy. Devolve (ok, detalhe, socket|None, categoria).

    categoria: 'ok' | 'auth' (407 — credencial do proxy) | 'allowlist' (403) | 'outro'.
    407 e 403 são coisas diferentes — confundi-los já mandou abortar operação sã.
    """
    if _eh_local(host):
        try:
            s = socket.create_connection((host, porta), timeout=timeout)
            return True, "conexão direta (alvo local)", s, "ok"
        except OSError as e:
            return False, "direta a %s:%d falhou: %s" % (host, porta, e), None, "outro"
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy:
        try:
            s = socket.create_connection((host, porta), timeout=timeout)
            return True, "conexão direta (sem proxy declarado)", s, "ok"
        except OSError as e:
            return False, "conexão direta falhou: %s" % e, None, "outro"
    p = urllib.parse.urlparse(proxy if "//" in proxy else "http://" + proxy)
    try:
        s = socket.create_connection((p.hostname, p.port or 3128), timeout=timeout)
        pedido = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n" % (host, porta, host, porta)
        if p.username:
            cred = "%s:%s" % (urllib.parse.unquote(p.username),
                              urllib.parse.unquote(p.password or ""))
            pedido += "Proxy-Authorization: Basic %s\r\n" % \
                base64.b64encode(cred.encode()).decode()
        s.sendall((pedido + "\r\n").encode())
        resp = s.recv(4096).decode("latin-1", "replace")
        primeira = resp.splitlines()[0] if resp else "(vazio)"
        if " 200 " in primeira:
            return True, primeira.strip(), s, "ok"
        s.close()
        extra = [l for l in resp.splitlines() if l.lower().startswith("x-proxy-error")]
        detalhe = (primeira + (" · " + extra[0] if extra else "")).strip()
        if " 407 " in primeira:
            return False, detalhe + " — o PROXY pede credencial (não é allowlist); " \
                "confira user:senha em $HTTPS_PROXY", None, "auth"
        if " 403 " in primeira and any("allowlist" in x.lower() for x in extra):
            return False, detalhe, None, "allowlist"
        return False, detalhe, None, "outro"
    except OSError as e:
        return False, "falha ao falar com o proxy: %s" % e, None, "outro"


def registrar_ocorrencia(cred, origem, operacao, sintoma, efeito):
    """Diário de ocorrências (contrato: regras da esteira): persiste o SINTOMA em formato
    M18 — nunca diagnóstico, que é de sessão fria. Só age com LASTRO_DIARIO declarado."""
    pasta = (cred or {}).get("LASTRO_DIARIO") or os.environ.get("LASTRO_DIARIO")
    if not pasta or not os.path.isdir(pasta):
        return
    import datetime
    caminho = os.path.join(pasta, "ocorrencias-%s.yaml" % datetime.date.today().isoformat())
    linhas = ["- quando: %s" % datetime.datetime.now().isoformat(timespec="seconds"),
              "  origem: %s" % origem,
              "  operacao: %s" % json.dumps(operacao, ensure_ascii=False),
              "  sintoma: |"]
    linhas += ["    " + l for l in str(sintoma).splitlines()]
    linhas.append("  efeito: %s" % json.dumps(efeito, ensure_ascii=False))
    try:
        with io.open(caminho, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        print("(sintoma registrado no diário: %s)" % caminho)
    except OSError:
        pass  # diário nunca vira segundo erro


def _tabela_bloqueio(r):
    """M18: bloqueio nunca é uma frase — é a lista do que foi testado."""
    linhas = ["| sonda | resultado |", "|---|---|"]
    linhas += ["| %s | %s |" % (k, v) for k, v in r.items()]
    return "\n".join(linhas)


def sonda(cred, verboso=True, lista_procedures=False):
    host = host_da_uri(cred.get("NEO4J_QUERY_URL") or cred["NEO4J_URI"])
    r = {"host": host, "local": "sim" if _eh_local(host) else "não"}
    r["n10s"] = "não sondado — sem rota"

    porta_https = urllib.parse.urlparse(base_query(cred) + "/").port or 443
    ok, det, s, cat = _via_proxy_connect(host, porta_https)
    r["camada 1 (proxy/tcp :%d)" % porta_https] = det
    if s:
        s.close()
    if not ok:
        r["veredito"] = {"auth": "proxy pede autenticação — corrija $HTTPS_PROXY",
                         "allowlist": "rota fechada no proxy (allowlist) — liberar o host",
                         "outro": "sem rota TCP até o host"}[cat]
        if verboso:
            print(_tabela_bloqueio(r))
        return r

    try:
        req = urllib.request.Request(base_query(cred) + "/", method="GET")
        with _abrir(req, 10) as resp:
            r["camada 2 (origem)"] = "HTTP %d" % resp.status
    except urllib.error.HTTPError as e:
        r["camada 2 (origem)"] = "HTTP %d (origem viva)" % e.code
    except Exception as e:
        r["camada 2 (origem)"] = "sem resposta: %s" % e
        r["veredito"] = "TCP passa, origem não responde — instância parada?"
        if verboso:
            print(_tabela_bloqueio(r))
        return r

    porta_bolt = urllib.parse.urlparse("//" + cred["NEO4J_URI"].split("://")[-1]).port or 7687
    ok, det, s, _ = _via_proxy_connect(host, porta_bolt)
    if ok and s:
        try:
            if cred["NEO4J_URI"].startswith(("bolt://", "neo4j://")) and _eh_local(host):
                s.sendall(bytes.fromhex("6060b017") + bytes.fromhex("00000105") * 4)
                versao = s.recv(4)
            else:
                ctx = ssl.create_default_context()
                ts = ctx.wrap_socket(s, server_hostname=host)
                ts.sendall(bytes.fromhex("6060b017") + bytes.fromhex("00000105") * 4)
                versao = ts.recv(4)
                ts.close()
            r["camada 3 (bolt :%d)" % porta_bolt] = "aberta — versão %s" % versao.hex()
        except Exception as e:
            r["camada 3 (bolt :%d)" % porta_bolt] = "TCP ok, handshake falhou: %s" % e
        finally:
            try:
                s.close()
            except OSError:
                pass
    else:
        r["camada 3 (bolt :%d)" % porta_bolt] = det

    try:
        r["database"] = database(cred, verboso=False)
        r["database_origem"] = "declarado (NEO4J_DATABASE)" if cred.get("NEO4J_DATABASE") \
            else "descoberto (home database do usuário)"
    except SystemExit as e:
        r["database"] = None
        r["veredito"] = "Query API inacessível ou sem home database (%s) — reste a Via A (driver + shim)" % str(e).splitlines()[0]
        if verboso:
            print(_tabela_bloqueio(r))
        return r

    ok, nomes, det = verificar_ollama(cred)
    r["ollama"] = det if ok else "sem resposta: %s" % det
    modelo = cred.get("EMBED_MODEL", "")
    r["ollama · EMBED_MODEL=%s" % modelo] = "baixado" if (ok and modelo_baixado(modelo, nomes)) else "não consta em /api/tags"
    r["ollama_pronto"] = bool(ok and modelo and modelo_baixado(modelo, nomes))

    # Procedures POR DIALETO — a chamada usará o dialeto em que a procedure apareceu.
    achadas = {}
    for prefixo in ("", "CYPHER 25"):
        stmt = ((prefixo + " ") if prefixo else "") + \
            "SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'genai.' " \
            "OR name STARTS WITH 'ai.text' OR name STARTS WITH 'n10s.' RETURN name"
        try:
            for (nome,) in [tuple(l) for l in query_api(cred, r["database"], stmt)]:
                achadas.setdefault(nome, prefixo)
        except Exception:
            pass
    r["procedures"] = ", ".join(sorted(achadas)) or "(nenhuma genai/ai.text)"
    r["n10s"] = ("%d procedure(s)" % sum(n.startswith("n10s.") for n in achadas)) \
        if any(n.startswith("n10s.") for n in achadas) \
        else "plugin não carregado (0 procedures) — rota rdflib"
    if any(n.startswith("ai.text.embed") for n in achadas):
        nome = "ai.text.embedBatch"
        r["procedure_embedding"], r["dialeto"] = nome, achadas.get(nome, achadas.get("ai.text.embed", ""))
    elif "genai.vector.encodeBatch" in achadas:
        r["procedure_embedding"], r["dialeto"] = "genai.vector.encodeBatch", achadas["genai.vector.encodeBatch"]
    else:
        r["procedure_embedding"], r["dialeto"] = None, ""
    r["veredito"] = "Query API pronta — database '%s'; embedding no servidor: %s%s" % (
        r["database"],
        r["procedure_embedding"] or "nenhum (rota ollama ou plugin GenAI ausente)",
        (" (dialeto: %s)" % r["dialeto"]) if r.get("dialeto") else "")
    if verboso:
        print(linhas_sonda(r, lista_procedures))
    return r


def linhas_sonda(r, lista_procedures=False):
    """P-AO: a linha `procedures` (dezenas de n10s.*) só aparece com -v; `n10s` guarda a contagem."""
    return "\n".join("  %-28s %s" % (k + ":", v) for k, v in r.items()
                     if lista_procedures or k != "procedures")


def verificar_ollama(cred):
    """GET /api/tags (direto, sem proxy — alvo local). Nunca lança: (ok, modelos, detalhe)."""
    base = url_ollama(cred)
    try:
        with _abrir(urllib.request.Request(base + "/api/tags"), 5) as resp:
            nomes = [m.get("name", "") for m in json.load(resp).get("models", [])]
        return True, nomes, "%d modelo(s)" % len(nomes)
    except Exception as e:
        return False, [], "%s: %s" % (type(e).__name__, e)


def modelo_baixado(modelo, nomes):
    """'qwen3-embedding:8b' exige o tag exato; 'embeddinggemma' (sem tag) casa qualquer tag."""
    if not modelo:
        return False
    if ":" in modelo:
        return modelo in nomes
    return any(n.split(":")[0] == modelo for n in nomes)


def query_api(cred, database, statement, parameters=None, timeout=180):
    url = "%s/db/%s/query/v2" % (base_query(cred), database)
    corpo = json.dumps({"statement": statement,
                        "parameters": parameters or {}}).encode("utf-8")
    auth = base64.b64encode(("%s:%s" % (cred["NEO4J_USERNAME"],
                                        cred["NEO4J_PASSWORD"])).encode()).decode()
    req = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Authorization": "Basic " + auth})
    with _abrir(req, timeout) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError("; ".join("%s: %s" % (e.get("code"), e.get("message"))
                                     for e in payload["errors"]))
    return (payload.get("data") or {}).get("values") or []


def query_com_retentativa(cred, database, statement, parameters):
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            return query_api(cred, database, statement, parameters)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            # M5: resposta 4xx (credencial recusada, statement inválido) não melhora esperando — relança já
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                raise
            transitorio = isinstance(e, (urllib.error.URLError, TimeoutError)) or \
                "unavailable" in str(e).lower() or "timed out" in str(e).lower()
            if tentativa == TENTATIVAS or not transitorio:
                raise
            time.sleep(3 * tentativa)


GEMINI_MODELO = "gemini-embedding-2"


GEMINI_DIM = 3072


GEMINI_LIMITE_TOKENS = 8192


VERTEX_URL = "https://aiplatform.googleapis.com/v1/projects/%s/locations/global/publishers/google/models/%s:%s"


METADADOS_TOKEN = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


EXCEDE_TOKENS = "exceeds the maximum number of tokens"


def url_vertex(cred, metodo):
    """Endpoint `global` do Vertex para o modelo de embedding (D5). O projeto vem de INCERTO_GCP_PROJETO na
    credencial (`credenciais()` lê `INCERTO_*` do ambiente)."""
    projeto = str(cred.get("INCERTO_GCP_PROJETO") or "").strip()
    if not projeto:
        sys.exit("rota Vertex: INCERTO_GCP_PROJETO ausente — declare o projeto Google Cloud no ambiente (D5)")
    return VERTEX_URL % (projeto, GEMINI_MODELO, metodo)


def token_vertex(cred):
    """Token OAuth para o `Authorization: Bearer`, nunca impresso: CLOUDSDK_AUTH_ACCESS_TOKEN (injetado pelo
    gateway da sessão na nuvem, ou exportado pelo Workload Identity Federation no CI) ou, na falta dele, o
    servidor de metadados (Cloud Run, conta de serviço do job). Sem nenhum dos dois, sai listando o que
    tentou (M18). Chave de conta de serviço não é rota: nunca em repositório nem em imagem."""
    tentados = []
    token = str(cred.get("CLOUDSDK_AUTH_ACCESS_TOKEN") or os.environ.get("CLOUDSDK_AUTH_ACCESS_TOKEN") or "").strip()
    if token:
        return token
    tentados.append("CLOUDSDK_AUTH_ACCESS_TOKEN: ausente")
    try:
        req = urllib.request.Request(METADADOS_TOKEN, headers={"Metadata-Flavor": "Google"})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3) as resp:
            return json.load(resp)["access_token"]
    except Exception as e:
        tentados.append("servidor de metadados (%s): %s" % (METADADOS_TOKEN.split("/")[2], type(e).__name__))
    sys.exit("rota Vertex: sem token OAuth — o que foi tentado:\n  - " + "\n  - ".join(tentados))


def _chamar_gemini(cred, metodo, corpo, espera=time.sleep):
    """POST no modelo pelo Vertex AI, endpoint `global`, com `Authorization: Bearer` (D5) — sem chave de API.
    Mesma retentativa do Lastro: 429 espera o `Retry-After` (ou 2, 4, 8… s) e tenta de novo; 5xx e queda de
    transporte esperam 2, 4, 8… s; 4xx sobe."""
    url, token = url_vertex(cred, metodo), token_vertex(cred)
    for tentativa in range(1, TENTATIVAS + 1):
        req = urllib.request.Request(url, method="POST", data=json.dumps(corpo).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        try:
            with _abrir(req, 60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or tentativa == TENTATIVAS:
                raise
            depois = str((e.headers or {}).get("Retry-After") or "").strip()
            espera(float(depois) if re.fullmatch(r"\d+(\.\d+)?", depois) else float(2 ** tentativa))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if tentativa == TENTATIVAS:
                raise
            espera(float(2 ** tentativa))


def embed_gemini(cred, textos, espera=time.sleep):
    """(vetores, tokens): um `embedContent` por texto, em paralelo (GEMINI_CONCORRENCIA, default 4), na ordem
    de `textos` (já com o prefixo de documento). Texto acima do limite do modelo vira None — recusado, nunca
    truncado; quem chama avisa com documento e tópico. No Vertex o `countTokens` não existe para este modelo
    e o padrão é truncar: vai `autoTruncate: false`, e o 400 de excesso (ou `truncated: true`) é a recusa."""
    url_vertex(cred, "embedContent"), token_vertex(cred)     # sai cedo, com a mensagem, antes do lote
    n = str(cred.get("GEMINI_CONCORRENCIA") or "").strip()
    concorrencia = int(n) if n.isdigit() and int(n) > 0 else 4

    def um(texto):
        try:
            r = _chamar_gemini(cred, "embedContent", {"content": {"parts": [{"text": texto}]},
                                                      "outputDimensionality": GEMINI_DIM, "autoTruncate": False}, espera)
        except urllib.error.HTTPError as e:
            if e.code == 400 and EXCEDE_TOKENS in str(e):
                return None, 0
            raise
        if r.get("truncated"):
            return None, 0
        return r["embedding"]["values"], (r.get("usageMetadata") or {}).get("promptTokenCount", 0)

    with concurrent.futures.ThreadPoolExecutor(concorrencia) as ex:
        feitos = list(ex.map(um, textos))
    return [v for v, _t in feitos], sum(t for _v, t in feitos)
