#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 plugin/skills/curadoria/scripts/recortar_chunks.py
"""Recorte determinístico e VERBATIM dos documentos aprovados pelo PO em trechos citáveis — JSONL.

Lê `<raiz>/conferidos/<onda>/**/*.md` (o portão `conferir_onda.py --aprovar` os copia para lá). Recorte
feito "de cabeça" condensa em silêncio; este script é o único produtor de trechos, com regra declarada.

Regra de recorte (fidelidade total, texto verbatim):
  - o arquivo é dividido pelos títulos do nível declarado (default 2: linhas `## `);
  - título de nível ACIMA do corte (`#` com --nivel 2) fecha o bloco corrente: o texto que vem depois
    dele é tópico próprio, com o título dessa linha; título acima do corte sem corpo (`# Parte` seguido
    direto de `## Cap.`) entra como prefixo verbatim do próximo bloco — nunca fica no tópico de cima;
  - o preâmbulo antes do primeiro título vira o tópico "(abertura)";
  - default é sem divisão (um tópico = um vetor); `--maxlen N` (>0) parte o bloco em fronteira de
    linha (campo `parte`); partes gravam `junta` (o separador consumido) e, a partir da 2ª,
    `cabecalho` (a linha de título, só para o texto embedado);
  - REGRA DA EQUAÇÃO DISPLAY: a partição nunca cai entre o `$$` de abertura e o de fechamento; a
    fronteira é movida para a primeira depois que o bloco fecha (a parte pode passar de `--maxlen`);
  - tópico acima de `--alerta-chars` (default 32000) gera aviso; acima de `--teto-chars`
    (default 120000) a execução ABORTA;
  - nada é reescrito, resumido ou fundido: o `texto` é fatia do original e a linha `## Título`
    permanece como primeira linha.

Chave canônica: `documento` é o caminho relativo a `conferidos/<onda>/`, SEMPRE em separador POSIX.
Só `<nome>.<ext>.md` é documento (o extraído de `X.pdf` é `X.pdf.md`, `references/extracao-nuvem.md`);
`.md` sem extensão de origem é recusado; `manifesto.json`, `*.report.json`, `lote-*.md` e `*.assets/`
não são documentos e são pulados.

Uso:
  python3 recortar_trechos.py --raiz <corpus> --onda <onda> --saida _esteira/incerto/trechos-<onda>.jsonl \
      [--nivel 2] [--maxlen 0] [--alerta-chars 32000] [--teto-chars 120000]

Saída: JSONL (documento, topico, parte, ordem, corpus, onda, texto, junta[, cabecalho]) anexado, e o
manifesto `<saida>.manifesto.json` SEM timestamp de execução (versão do plugin, parâmetros, contagens
e sha256 dos trechos). Só biblioteca padrão.
"""
import argparse
import hashlib
import io
import json
import os
import posixpath
import re
import sys
import unicodedata

CORPUS = "incerto"
RE_ONDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RE_LOTE = re.compile(r"^lote-.*\.md$")
RE_EXTENSAO_DE_ORIGEM = re.compile(r"^.+\.[A-Za-z0-9]{1,8}$")
PLUGIN_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".claude-plugin", "plugin.json")


def versao_plugin():
    """Versão do incerto, lida de `.claude-plugin/plugin.json` a cada execução (fonte única)."""
    with io.open(PLUGIN_JSON, encoding="utf-8") as f:
        return json.load(f)["version"]


def alerta_do_contexto(tokens):
    """O alerta do inventário sai do contexto declarado do modelo de embedding."""
    return int(int(tokens) * 1.8)


SEPARADORES_DE_CORTE = ("\n\n", "\n", " ")   # linha em branco, linha, espaço — nessa ordem


def _depois_do_bloco_display(text, de):
    """Primeira fronteira de linha depois que o `$$` aberto antes de `de` fecha: (indice, separador),
    ou None se o bloco não fecha ou não há fronteira depois dele."""
    fecho = text.find("$$", de)
    if fecho < 0:
        return None
    i = text.find("\n", fecho + 2)
    if i < 0:
        return None
    return (i, "\n\n") if text.startswith("\n\n", i) else (i, "\n")


def split_topic(text, maxlen):
    """Parte um bloco grande sem reescrever nada: devolve [(junta, parte)], onde `junta` é o
    separador real consumido entre a parte anterior e esta ('' na primeira e no corte duro).
    Corta na última fronteira que cabe em `maxlen`: linha em branco, senão fim de linha, senão
    espaço; só sem nenhuma delas corta duro. Regra da equação display: se o texto até a fronteira
    escolhida tem número ímpar de `$$`, a fronteira cai dentro de um bloco `$$…$$`; ela é movida
    para a primeira fronteira de linha depois do `$$` de fechamento (sem fechamento ou sem
    fronteira depois, o resto fica numa parte só). `"".join(j + p ...) == text` sempre.
    `maxlen <= 0` = sem partição."""
    if maxlen <= 0 or len(text) <= maxlen:
        return [("", text)]
    pares, pos, junta = [], 0, ""
    while len(text) - pos > maxlen:
        janela = text[pos:pos + maxlen + 1]
        corte, sep = -1, ""
        for s in SEPARADORES_DE_CORTE:
            i = janela.rfind(s, 1, maxlen + 1)
            if i > 0:
                corte, sep = i, s
                break
        if corte <= 0:
            corte, sep = maxlen, ""
        fim = pos + corte
        if text.count("$$", 0, fim) % 2:
            mov = _depois_do_bloco_display(text, fim)
            if mov is None:
                break
            fim, sep = mov
        pares.append((junta, text[pos:fim]))
        pos, junta = fim + len(sep), sep
    pares.append((junta, text[pos:]))
    return pares


def desambiguar_topicos(blocos):
    """blocos: [(titulo, pai, corpo)] na ordem do arquivo; pai = título mais recente de nível
    menor que o nível do recorte (ou None). Título repetido dentro do documento recebe
    ` — <pai>`; se ainda colidir (ou não há pai), recebe ` (n)` sequencial. Só a CHAVE muda —
    o `texto` permanece verbatim (P-A do Shield: `desambiguar_topicos.py`, contorno local)."""
    contagem = {}
    for t, _, _ in blocos:
        contagem[t] = contagem.get(t, 0) + 1
    candidatos = []
    for t, pai, corpo in blocos:
        candidatos.append(("%s — %s" % (t, pai) if contagem[t] > 1 and pai else t, corpo))
    contagem2, vistos, out = {}, {}, []
    for t, _ in candidatos:
        contagem2[t] = contagem2.get(t, 0) + 1
    for t, corpo in candidatos:
        if contagem2[t] > 1:
            vistos[t] = vistos.get(t, 0) + 1
            out.append(("%s (%d)" % (t, vistos[t]), corpo))
        else:
            out.append((t, corpo))
    return out


SUBTITULO_CHARS = 8000   # Q6 (0.20.17): tópico acima disso COM subtítulo mais fundo que o corte → aviso


def nivel_do_subtitulo(corpo, nivel):
    """O nível do primeiro título mais fundo que o corte dentro do tópico (fora de cerca de código), ou None."""
    cerca = False
    for linha in corpo.splitlines()[1:]:
        if linha.lstrip().startswith(("```", "~~~")):
            cerca = not cerca
            continue
        m = None if cerca else re.match(r"^(#{1,6}) \S", linha)
        if m and len(m.group(1)) > nivel:
            return len(m.group(1))
    return None


def linha_do_titulo(corpo, nivel):
    """A linha de título do tópico (vai em `cabecalho` das partes seguintes): a última da sequência de
    títulos de nível ≤ N que abre o bloco — o prefixo `# Parte` não é o título de `## Cap.`. Bloco que não
    abre com título dessa sequência (a "(abertura)") devolve a primeira linha se ela for título, ou None."""
    if not corpo.startswith("#"):
        return None
    ultima = corpo.split("\n", 1)[0]
    for linha in corpo.split("\n"):
        if not linha.strip():
            continue
        m = re.match(r"^(#{1,6}) ", linha)
        if not m or len(m.group(1)) > nivel:
            break
        ultima = linha
    return ultima


def recortar_texto(texto, nivel, maxlen, alerta_chars, teto_chars, subtitulo_chars=SUBTITULO_CHARS):
    """Divide pelos títulos de nível ≤ N; preâmbulo vira '(abertura)'. Verbatim.

    A linha `## Título` permanece como primeira linha do `texto` do bloco (mesma
    forma dos trechos já gravados — MERGE idempotente entre levas).

    Título de nível < N (rodada corpus A, 2026-10-05) FECHA o bloco corrente: o texto depois
    dele, até o próximo título de nível ≤ N, é um tópico próprio com o título dessa linha —
    nunca é atribuído ao tópico de cima. Título de nível < N sem corpo (`# Parte` seguido direto
    de `## Cap.`) não vira tópico vazio: entra como prefixo verbatim do próximo bloco. `pai` de
    um bloco é o título de nível mais alto (número menor) mais próximo acima do seu. Linha dentro de cerca de
    código (``` ou ~~~; só o marcador que abriu a cerca a fecha) ou de bloco display `$$ … $$` nunca é título.

    Devolve (chunks, alertas). chunks: dicts com topico, parte, ordem, texto.
    Tópico acima de `alerta_chars` gera aviso (pauta, não corte); acima de
    `teto_chars` (contexto do modelo) ABORTA (SystemExit) listando os estouros."""
    blocos, linhas, titulo, pai_do_bloco = [], [], "(abertura)", None
    so_titulos = False      # o bloco corrente até aqui é só título(s) de nível < N e brancos
    acima = {}              # nível -> título vigente, para achar o `pai`
    cerca, display = None, False    # cerca: o marcador que a abriu (``` ou ~~~); dentro dela ou de `$$ … $$`,
                                    # nenhuma linha é título

    def fechar_bloco():
        corpo = "".join(linhas).strip()
        if corpo:
            blocos.append((titulo, pai_do_bloco, corpo))

    for linha in texto.splitlines(keepends=True):
        protegida = bool(cerca) or display
        marcador = next((mk for mk in ("```", "~~~") if linha.lstrip().startswith(mk)), None)
        if marcador and not display and (cerca is None or marcador == cerca):
            cerca = marcador if cerca is None else None     # só o mesmo marcador fecha a cerca
        elif not cerca and linha.count("$$") % 2:
            display = not display
        m = None if protegida else re.match(r"^(#{1,6}) (.*)$", linha.rstrip("\n"))
        n = len(m.group(1)) if m else 0
        if m and n <= nivel:
            # P-AL: NFC na CAPTURA — desambiguar_topicos monta a chave ("<titulo> — <pai>") a
            # partir destes valores; normalizar só no chunks.append chegaria tarde demais.
            t = unicodedata.normalize("NFC", m.group(2).strip())
            for k in [k for k in acima if k >= n]:
                del acima[k]
            pai = acima[max(acima)] if acima else None
            acima[n] = t
            if not so_titulos:
                fechar_bloco()
                linhas = []
            linhas.append(linha)
            titulo, pai_do_bloco, so_titulos = t, pai, n < nivel
            continue
        if so_titulos and linha.strip():
            so_titulos = False
        linhas.append(linha)
    fechar_bloco()
    blocos = desambiguar_topicos(blocos)
    chunks, alertas, estouros = [], [], []
    for ordem, (top, corpo) in enumerate(blocos, 1):
        if len(corpo) > teto_chars:
            estouros.append("%s (%d chars)" % (top, len(corpo)))
        else:
            # Q6 (0.20.17): tópico grande com subtítulo dilui o trecho que responde — sugere o nível dele
            sub = nivel_do_subtitulo(corpo, nivel) if len(corpo) > min(alerta_chars, subtitulo_chars) else None
            dica = " — tem subtítulo de nível %d: recortar com --nivel %d dilui menos" % (sub, sub) if sub else ""
            if len(corpo) > alerta_chars:
                alertas.append("⚠️ tópico longo: %s (%d chars) — pauta da rodada, não corte%s" % (top, len(corpo), dica))
            elif sub and len(corpo) > subtitulo_chars:
                alertas.append("⚠️ tópico grande com subtítulos: %s (%d chars)%s" % (top, len(corpo), dica))
        linha_titulo = linha_do_titulo(corpo, nivel)
        for n, (junta, p) in enumerate(split_topic(corpo, maxlen), 1):
            ch = {"topico": unicodedata.normalize("NFC", top), "parte": n, "ordem": ordem, "texto": p, "junta": junta}
            if n > 1 and linha_titulo:
                ch["cabecalho"] = linha_titulo       # P-AK: só no texto embedado, nunca em `texto`
            chunks.append(ch)
    if estouros:
        sys.exit("tópicos acima do teto de %d chars (contexto do modelo) — decida com o PO antes de recortar:\n  - %s"
                 % (teto_chars, "\n  - ".join(estouros)))
    return chunks, alertas


def chave_local(s):
    return unicodedata.normalize("NFC", s or "").replace("\\", "/")


def aviso_nome_fora_nfc(rel, doc):
    """Aviso quando o caminho RELATIVO (o que vira chave) está fora de NFC."""
    if unicodedata.is_normalized("NFC", rel):
        return None
    return ("nome de arquivo fora de NFC: %r — chave gravada em NFC (%s); regenere com o nome corrigido"
            % (rel, doc))


def listar_documentos(dir_onda):
    """[(caminho, chave POSIX)] ordenado por bytes da chave. Pula manifesto, relatórios, lotes e
    `*.assets/`; recusa (SystemExit) `.md` sem extensão de origem (`Relatorio.md` em vez de `Relatorio.pdf.md`)."""
    achados, recusados = [], []
    for base, dirs, nomes in os.walk(dir_onda):
        dirs[:] = [d for d in dirs if not d.endswith(".assets")]
        for nome in nomes:
            if not nome.endswith(".md") or RE_LOTE.match(nome):
                continue
            rel = os.path.relpath(os.path.join(base, nome), dir_onda).replace(os.sep, "/")
            if not RE_EXTENSAO_DE_ORIGEM.match(nome[:-3]):
                recusados.append(rel)
            else:
                achados.append((os.path.join(base, nome), chave_local(posixpath.normpath(rel)), rel))
    if recusados:
        sys.exit("documento sem extensão de origem (o extraído de X.pdf é X.pdf.md; ver "
                 "references/extracao-nuvem.md):\n  - %s" % "\n  - ".join(sorted(recusados, key=lambda r: r.encode("utf-8"))))
    return sorted(achados, key=lambda t: t[1].encode("utf-8"))


def caminho_manifesto(saida):
    return os.path.splitext(os.path.abspath(saida))[0] + ".manifesto.json"


def sha256_trechos(trechos):
    linhas = [json.dumps(t, ensure_ascii=False, sort_keys=True) for t in trechos]
    return hashlib.sha256("\n".join(linhas).encode("utf-8")).hexdigest()


def registrar_execucao(caminho, execucao):
    """0.20.13: a onda declara de onde veio. Lista, porque um corpus real é feito de várias execuções
    com parâmetros diferentes (a onda-8 precisou de três) — registrar "o comando" seria ficção."""
    manifesto = {"versao": 1, "execucoes": []}
    if os.path.exists(caminho):
        with io.open(caminho, encoding="utf-8") as f:
            manifesto = json.load(f)
    execucao = dict(execucao, execucao=len(manifesto["execucoes"]) + 1)
    manifesto["execucoes"].append(execucao)
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=1, sort_keys=True)
    return execucao["execucao"]


def anexar_trechos(saida, trechos, execucao):
    """Anexa ao JSONL — nunca sobrescreve —, aborta em linha ilegível ou documento repetido, e declara
    a execução no manifesto de proveniência (sem timestamp)."""
    docs, ja = {t["documento"] for t in trechos}, set()
    if os.path.exists(saida):
        with io.open(saida, encoding="utf-8") as f:
            linhas = [l for l in f if l.strip()]
        for n_linha, l in enumerate(linhas, 1):
            try:
                ja.add(json.loads(l)["documento"])
            except (ValueError, KeyError) as e:
                sys.exit("%s tem a linha %d ilegível (%s) — provável escrita interrompida; inspecione o "
                         "arquivo ou apague-o para recomeçar a onda antes de anexar:\n  %r"
                         % (saida, n_linha, e, l.strip()[:200]))
    repetidos = sorted(docs & ja)
    if repetidos:
        cauda = ("\n  ... e mais %d (lista truncada em 20 de %d no total)" % (len(repetidos) - 20, len(repetidos))
                 if len(repetidos) > 20 else "")
        sys.exit("documento(s) já presentes em %s — a --saida é anexada, nunca sobrescrita; para recomeçar a onda "
                 "apague o arquivo E o manifesto ao lado (%s) ou use outra --saida:\n  - %s%s"
                 % (saida, os.path.basename(caminho_manifesto(saida)), "\n  - ".join(repetidos[:20]), cauda))
    d = os.path.dirname(os.path.abspath(saida))
    os.makedirs(d, exist_ok=True)
    with io.open(saida, "a", encoding="utf-8", newline="\n") as f:
        for t in trechos:
            f.write(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n")
    n = registrar_execucao(caminho_manifesto(saida), dict(
        execucao, versao_plugin=versao_plugin(),
        documentos=len(docs), trechos=len(trechos), sha256_trechos=sha256_trechos(trechos)))
    return n, bool(ja)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", required=True, help="raiz do corpus (a pasta que contém `conferidos/`)")
    ap.add_argument("--onda", required=True, help="onda a recortar: lê <raiz>/conferidos/<onda>/")
    ap.add_argument("--saida", required=True, help="arquivo JSONL de saída (anexado)")
    ap.add_argument("--maxlen", type=int, default=0, help="0 (default) = sem partição; N>0 só para contexto curto")
    ap.add_argument("--nivel", type=int, default=2, help="nível do título de corte (default 2: '## ')")
    ap.add_argument("--alerta-chars", type=int, default=32000, help="tópico acima disso gera aviso (pauta, não corta)")
    ap.add_argument("--contexto-tokens", type=int, default=0,
                    help="contexto do modelo de embedding: o alerta passa a N × 1,8 chars e vence --alerta-chars")
    ap.add_argument("--alerta-subtitulo", type=int, default=SUBTITULO_CHARS,
                    help="tópico acima disso com subtítulo mais fundo que --nivel gera aviso com o nível sugerido")
    ap.add_argument("--teto-chars", type=int, default=120000, help="tópico acima disso ABORTA")
    args = ap.parse_args(argv)

    if not RE_ONDA.match(args.onda) or ".." in args.onda:
        ap.error("--onda inválida: use ^[A-Za-z0-9][A-Za-z0-9._-]*$ sem '..'")
    if args.contexto_tokens > 0:
        args.alerta_chars = alerta_do_contexto(args.contexto_tokens)
    dir_onda = os.path.join(args.raiz, "conferidos", args.onda)
    if not os.path.isdir(dir_onda):
        sys.exit("não existe %s — rode `conferir_onda.py --aprovar` antes" % dir_onda)
    arquivos = listar_documentos(dir_onda)
    if not arquivos:
        sys.exit("nenhum documento .md em %s" % dir_onda)

    trechos, chars, avisos = [], 0, []
    for caminho, doc, rel in arquivos:
        with io.open(caminho, encoding="utf-8", newline="") as f:
            txt = f.read()
        aviso = aviso_nome_fora_nfc(rel, doc)
        if aviso:
            avisos.append(aviso)
        chunks, alertas = recortar_texto(txt, args.nivel, args.maxlen,
                                         args.alerta_chars, args.teto_chars, args.alerta_subtitulo)
        for t in chunks:
            t.update({"documento": doc, "corpus": CORPUS, "onda": args.onda})
            trechos.append(t)
            chars += len(t["texto"])
        avisos.extend("%s: %s" % (doc, a) for a in alertas)

    n, ja = anexar_trechos(args.saida, trechos, {
        "onda": args.onda, "corpus": CORPUS, "maxlen": args.maxlen, "nivel": args.nivel,
        "alerta_chars": args.alerta_chars, "teto_chars": args.teto_chars})
    print("gravado: %s (%s) · manifesto: execução %d em %s"
          % (args.saida, "anexado" if ja else "novo", n, caminho_manifesto(args.saida)))
    print("documentos: %d · trechos: %d · caracteres: %d" % (len(arquivos), len(trechos), chars))
    for a in avisos:
        print(a)


if __name__ == "__main__":
    main()
