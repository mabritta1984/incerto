#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 build/injetar_regras.py
"""Injeta blocos de dono único nos arquivos que os consomem.

Por que este script existe
--------------------------
O plugin tem um princípio anti-sombreamento: regra compartilhada mora em **um lugar
só**. Mas as skills precisam ser autossuficientes na distribuição avulsa (`.skill`) —
elas não podem ler um arquivo de outra skill em runtime. As duas coisas só coexistem
se a cópia for **gerada**, nunca escrita à mão: o dono edita, o injetor propaga,
`--check` prova que ninguém divergiu.

Sem esse mecanismo, cada cópia apodrece sozinha — foi o que aconteceu com o
vocabulário do grafo e com o protocolo de duas passadas, que divergiram entre si
antes da v0.11.

Formato dos marcadores
----------------------
No **dono** do bloco:

    <!-- bloco:<id>:inicio (dono deste bloco — edite aqui) -->
    ...conteúdo...
    <!-- bloco:<id>:fim -->

Em cada **consumidor**:

    <!-- bloco:<id>:inicio (gerado de <arquivo-dono> — edite a fonte e rode build/injetar_regras.py --write) -->
    ...conteúdo gerado...
    <!-- bloco:<id>:fim -->

O consumidor se declara sozinho: para passar a consumir um bloco, basta colar o par
de marcadores (o miolo pode vir vazio) e rodar `--write`. Não há registro central a
manter em sincronia — o que evita criar um segundo lugar onde a verdade mora.

Uso, a partir da raiz do repositório (o pacote é plugin/; --raiz muda)
----------------------------------------------------------------------
    python3 build/injetar_regras.py --check   # verifica; exit 1 se divergir
    python3 build/injetar_regras.py --write   # propaga o conteúdo dos donos
    python3 build/injetar_regras.py --check --raiz jazida --bloco-obrigatorio regras-da-jazida

`--check` integra o checklist de release (verificador frio).
"""
import argparse
import re
import sys
from pathlib import Path

RE_ABRE = re.compile(
    r"<!--\s*bloco:(?P<id>[a-z0-9][a-z0-9-]*):inicio\s*\((?P<papel>dono|gerado)[^>]*?\)\s*-->"
)
# Qualquer abertura de bloco, bem ou mal formada. Existe porque um marcador fora do
# formato era pior que a duplicação que o script combate: invisível para o --check e
# intocado pelo --write, ele guardava uma cópia podre com cara de gerada.
RE_ABRE_FROUXA = re.compile(r"<!--\s*bloco:(?P<id>[^\s:]+):inicio\b(?P<resto>[^>]*?)-->")
FMT_FIM = "<!-- bloco:{id}:fim -->"
CABECALHO_GERADO = (
    "<!-- bloco:{id}:inicio (gerado de {dono} — "
    "edite a fonte e rode build/injetar_regras.py --write) -->"
)
# Todo SKILL.md precisa consumir este bloco: é o contrato comum da esteira.
BLOCO_OBRIGATORIO_EM_SKILLS = "regras-da-esteira"


class ErroDeMarcacao(Exception):
    """Marcação malformada — sempre acusada, nunca contornada em silêncio."""


def _fatiar(texto: str, id_bloco: str, origem: Path):
    """Devolve (inicio, fim) do bloco `id_bloco` em `texto`, ou None se ausente.

    `fim` é o índice logo após o marcador de fechamento.
    """
    abre = None
    for m in RE_ABRE.finditer(texto):
        if m.group("id") == id_bloco:
            if abre is not None:
                raise ErroDeMarcacao(f"{origem}: bloco '{id_bloco}' abre duas vezes")
            abre = m
    if abre is None:
        return None
    marcador_fim = FMT_FIM.format(id=id_bloco)
    j = texto.find(marcador_fim, abre.end())
    if j == -1:
        raise ErroDeMarcacao(
            f"{origem}: bloco '{id_bloco}' abre e não fecha "
            f"(esperado '{marcador_fim}')"
        )
    return abre.start(), j + len(marcador_fim)


def _miolo(texto: str, fatia, id_bloco: str) -> str:
    """Conteúdo entre os marcadores, sem os marcadores."""
    i, j = fatia
    trecho = texto[i:j]
    corpo = trecho[trecho.index("-->") + 3 : -len(FMT_FIM.format(id=id_bloco))]
    return corpo.strip("\n")


def _no_pacote(caminho: Path, raiz: Path) -> bool:
    """Retorna False se o caminho está em docs/ ou em diretório oculto.

    docs/ e pastas ocultas guardam planos e aparatos com marcadores de exemplo.
    """
    rel = caminho.relative_to(raiz)
    # Verifica todos os diretórios no caminho relativo (exclui o arquivo final)
    for parte in rel.parts[:-1]:
        if parte.startswith(".") or parte == "docs":
            return False
    return True


def mapear(raiz: Path, bloco_obrigatorio: str = BLOCO_OBRIGATORIO_EM_SKILLS):
    """Varre a árvore e devolve (donos, consumidores, avisos).

    donos: {id: (caminho, miolo)} · consumidores: [(caminho, id)]
    `bloco_obrigatorio`: o contrato comum que todo SKILL.md consome (Jazida V1.1: o segundo plugin
    do monorepo usa o mesmo injetor com `regras-da-jazida`).
    """
    donos, consumidores, avisos = {}, [], []
    for caminho in sorted(raiz.rglob("*.md")):
        if not _no_pacote(caminho, raiz):
            continue
        texto = caminho.read_text(encoding="utf-8")
        bem_formados = {m.start() for m in RE_ABRE.finditer(texto)}
        for m in RE_ABRE_FROUXA.finditer(texto):
            if m.start() not in bem_formados:
                raise ErroDeMarcacao(
                    f"{caminho}: abertura de bloco '{m.group('id')}' fora do formato — "
                    f"esperado '(dono ...)' ou '(gerado ...)' no cabeçalho. "
                    f"Sem o papel declarado o bloco fica invisível para --check e --write."
                )
        for m in RE_ABRE.finditer(texto):
            id_bloco, papel = m.group("id"), m.group("papel")
            fatia = _fatiar(texto, id_bloco, caminho)
            if papel == "dono":
                if id_bloco in donos:
                    raise ErroDeMarcacao(
                        f"bloco '{id_bloco}' tem dois donos: "
                        f"{donos[id_bloco][0]} e {caminho}"
                    )
                donos[id_bloco] = (caminho, _miolo(texto, fatia, id_bloco))
            else:
                consumidores.append((caminho, id_bloco))

    ids_consumidos = {i for _, i in consumidores}
    for id_bloco in sorted(ids_consumidos - set(donos)):
        alvos = ", ".join(str(c) for c, i in consumidores if i == id_bloco)
        raise ErroDeMarcacao(
            f"bloco '{id_bloco}' é consumido ({alvos}) e não tem dono declarado"
        )
    for id_bloco, (caminho, _) in sorted(donos.items()):
        if id_bloco not in ids_consumidos:
            avisos.append(f"bloco '{id_bloco}' ({caminho}) não é consumido por ninguém")

    # Rede de segurança: skill nova que esqueceu o contrato comum.
    for skill in sorted(raiz.glob("skills/*/SKILL.md")):
        if (skill, bloco_obrigatorio) not in consumidores:
            avisos.append(
                f"{skill} não consome o bloco '{bloco_obrigatorio}' — "
                f"cole os marcadores e rode --write"
            )
    return donos, consumidores, avisos


def aplicar(donos, consumidores, escrever: bool):
    """Compara (e opcionalmente atualiza) cada consumidor contra seu dono."""
    divergentes, atualizados = [], []
    por_arquivo = {}
    for caminho, id_bloco in consumidores:
        por_arquivo.setdefault(caminho, []).append(id_bloco)

    for caminho, ids in sorted(por_arquivo.items()):
        texto = original = caminho.read_text(encoding="utf-8")
        for id_bloco in ids:
            dono, miolo = donos[id_bloco]
            if dono == caminho:
                raise ErroDeMarcacao(
                    f"{caminho}: é dono e consumidor de '{id_bloco}' ao mesmo tempo"
                )
            esperado = "\n".join(
                (
                    CABECALHO_GERADO.format(id=id_bloco, dono=dono.name),
                    miolo,
                    FMT_FIM.format(id=id_bloco),
                )
            )
            fatia = _fatiar(texto, id_bloco, caminho)
            atual = texto[fatia[0] : fatia[1]]
            if atual == esperado:
                continue
            if escrever:
                texto = texto[: fatia[0]] + esperado + texto[fatia[1] :]
            else:
                divergentes.append((caminho, id_bloco))
        if escrever and texto != original:
            caminho.write_text(texto, encoding="utf-8")
            atualizados.append((caminho, ids))
    return divergentes, atualizados


def main() -> int:
    # Windows: stdout nasce em cp1252, e quem lê (verificar_release.py) decodifica UTF-8.
    # Mesmo reconfigure de plugin/mcp/busca_semantica.py main().
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="só verifica; exit 1 se divergir")
    g.add_argument("--write", action="store_true", help="propaga o conteúdo dos donos")
    ap.add_argument("--raiz", default="plugin", help="raiz do plugin (default: plugin)")
    ap.add_argument("--bloco-obrigatorio", default=BLOCO_OBRIGATORIO_EM_SKILLS,
                    help="bloco que todo skills/*/SKILL.md consome (default: %(default)s; jazida: regras-da-jazida)")
    args = ap.parse_args()

    raiz = Path(args.raiz)
    if not (raiz / "skills").is_dir():
        print(f"ERRO: {raiz.resolve()} não parece a raiz do plugin (falta skills/).")
        return 1

    try:
        donos, consumidores, avisos = mapear(raiz, args.bloco_obrigatorio)
        divergentes, atualizados = aplicar(donos, consumidores, escrever=args.write)
    except ErroDeMarcacao as e:
        print(f"ERRO DE MARCAÇÃO: {e}")
        return 1

    for aviso in avisos:
        print(f"AVISO: {aviso}")

    if args.check:
        if divergentes:
            for caminho, id_bloco in divergentes:
                print(f"DIVERGENTE: {caminho} — bloco '{id_bloco}' fora de sincronia")
            print(f"\n{len(divergentes)} bloco(s) divergente(s).")
            return 1
        print(
            f"OK: {len(donos)} bloco(s) com dono, "
            f"{len(consumidores)} injeção(ões) em sincronia."
        )
        # Aviso reprova: `--check` é o verificador do release, e o release não pode
        # sair com skill fora do contrato comum ou bloco sem consumidor. Quem quiser
        # inspecionar sem reprovar usa --write, que só relata.
        if avisos:
            print(f"\n{len(avisos)} aviso(s) — reprova o pacote.")
            return 1
        return 0

    for caminho, ids in atualizados:
        print(f"injetado: {caminho} ({', '.join(ids)})")
    print(
        f"OK: {len(atualizados)} arquivo(s) atualizado(s), "
        f"{len(consumidores)} injeção(ões) no total."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
