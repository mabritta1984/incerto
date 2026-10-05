# Incerto — especialista de investimentos baseado em Nassim Taleb

Plugin do Claude Code, bifurcado do Jazida em repositório próprio. Um corpus de Taleb curado em grafo
(Neo4j), em que **equação é nó de primeira classe**, com **fiscal de duas vias** (SymPy e Wolfram)
antes de qualquer aprovação e dados do mercado brasileiro (BCB e B3) para análises de antifragilidade
e caudas gordas. O veredito do especialista nunca é recomendação de ativo.

**Versão:** `0.1.0` (ver [Changelog](#changelog)). **Spec:**
`docs/superpowers/specs/2026-10-04-incerto-bifurcacao-da-jazida.md`. **Plano:**
`docs/superpowers/plans/2026-10-04-incerto-0.1.0-bifurcacao-da-jazida.md`.

## O que existe

| Caminho | O quê |
|---|---|
| `.claude-plugin/plugin.json` | manifesto do plugin `incerto` |
| `.claude-plugin/marketplace.json` | marketplace com uma entrada, `source: ./` |
| `regras-do-incerto.md` | regras comuns, dono único do bloco injetado abaixo |
| `build/injetar_regras.py` | injetor de blocos de dono único (reuso direto do Lastro) |
| `skills/lavra/SKILL.md` | estação `lavra`: rito por onda em oito passos (copiar originais, conversão, portão, recorte/ingestão/extração, momentos, fiscal de duas vias, bloco de decisão, aprovação), cada um com comando e parada, e decisão do PO antes de gastar modelo ou escrever no Aura |
| `skills/lavra/references/devolucao.md` | formato do bloco de decisão único da rodada (renomeações, conceitos, heurísticas, momentos, indeterminados, vermelhos) e a linha JSONL de cada decisão, dono único |
| `skills/lavra/references/extracao-nuvem.md` | contrato de extração na nuvem (layout do bucket, portão do PO), dono único |
| `skills/lavra/references/fiscal.md` | protocolo da prova Wolfram do fiscal de duas vias (código, veredito, registro verbatim), dono único |
| `skills/lavra/references/grafo-incerto.md` | modelo do grafo (rótulos, chaves, relações), gate de aprovação e Cypher canônico de cada `MERGE`, dono único |
| `skills/lavra/scripts/conferir_onda.py` | portão do PO: relatório de fidelidade e aprovação de uma onda do `mineiro`; lê o sidecar de reparo e reconta itens, equações e perdas com as páginas emendadas |
| `skills/lavra/scripts/emendar_paginas.py` | reparo: emenda no `.md` da onda as páginas reconvertidas numa onda de reparo (sub-PDF `<documento>_pA-B`), entre marcadores, com sidecar `<documento>.reparos.json`; nunca altera o `report.json` do `mineiro` |
| `skills/lavra/scripts/recortar_trechos.py` | recorte verbatim dos `conferidos/` em trechos citáveis (`--nivel`, `--maxlen`); título de nível acima do corte fecha o bloco e vira tópico próprio, nunca é anexado ao tópico anterior |
| `skills/lavra/scripts/ingerir_trechos.py` | ingestão idempotente e retomável dos trechos no Neo4j (`:Trecho` com embedding Vertex, `:Documento`), com `--verificar` (contagem, dimensão e índices) |
| `skills/lavra/scripts/extrair_equacoes.py` | equações display → candidatos a `:Equacao` em staging (LaTeX + `srepr`); funções declaradas pelo PO por documento; `\pi` e `e^{…}` como as constantes π e e (π usado como variável é perda declarada); estatística de ordem `_{(…)}`, relação encadeada e resultado não relacional são perdas declaradas |
| `skills/lavra/scripts/fiscal.py` | fiscal de duas vias: P1 parse, P2 derivação, P3 condição, P4 via Wolfram (por derivação, momento fechado e **por equação**); vermelho nunca promove |
| `skills/lavra/scripts/registrar_prova.py` | registra verbatim a prova Wolfram rodada pelo agente (`--prova P2`, `momento` ou `equacao`); o veredito sai do último `Out[n]=` (verde só com 0 exato) |
| `skills/lavra/scripts/limite_sympy.py` | limite de tempo de parede do SymPy (padrão 10 s, `INCERTO_LIMITE_SYMPY_S`): equação que não volta vira perda `tempo_esgotado`, nunca trava a esteira |
| `skills/lavra/scripts/aprovar_onda.py` | único escritor que promove a `aprovado`, só com o gate do fiscal e as decisões do PO (`decisoes-<onda>.jsonl`) |
| `skills/lavra/scripts/nucleo.py` | credencial, Query API do Neo4j e embedding Gemini pelo Vertex (token OAuth do ambiente) |
| `skills/taleb/scripts/dados_br.py` | dados BR reproduzíveis: SGS do BCB e COTAHIST da B3, com cache em `dados/` e testes offline |
| `skills/taleb/references/dados-br.md` | séries do SGS, layout do COTAHIST, hosts a liberar na rede e download manual do ZIP, dono único |
| `skills/taleb/SKILL.md` | estação `taleb`: rito em cinco passos (exposição, corpus pelo MCP, dados BR, diagnósticos, Wolfram antes de afirmar conta fechada) e veredito marcado que nunca recomenda ativo |
| `skills/taleb/references/doutrina.md` | um verbete por conceito de Taleb, cada um com `fonte:` (`[externo]` até a onda 1 ser conferida) |
| `skills/taleb/references/heuristicas.md` | regras práticas com `condicao:` parseável pelo fiscal sobre `kappa`, `alpha`, `H`, `fracao_segura` |
| `skills/taleb/scripts/caudas.py` | razão máximo/soma, Hill, κ de Taleb (com `robusto=True` pela mediana) e geradores determinísticos |
| `skills/taleb/scripts/convexidade.py` | assimetria de convexidade, Kelly, barbell, crescimento temporal × ensemble |
| `skills/taleb/scripts/relatorio.py` | relatório por ativo, cada número com a equação e a marca de procedência; Extremistão por κ_1 = κ(1, 2) exato com intervalo bootstrap, contra o limiar 0,15 do corpus (SCFT 8.3.2) |
| `mcp/consulta_incerto.py` | MCP `incerto-consulta`, só leitura e só o aprovado: `buscar_equacao`, `ler_equacao` (por nome ou rótulo), `ler_conceito`, `situacao_camada` |
| `evals/` | três casos de `claude plugin eval` (especialista não cita staging como corpus, Wolfram antes de conta fechada, fiscal de duas vias); corrida manual por `.github/workflows/evals.yml` |
| `build/verificar_incerto.py` | verificador frio: versão, sintaxe, import cruzado, dependências, segredos |
| `build/testes/` | testes; `_carga.py` carrega módulos por caminho relativo à raiz |
| `dados/` | cache dos dados BR (conteúdo fora do git) |
| `docs/superpowers/` | spec e plano |
| `docs/oficina/onda-2026-10-TALEB-1.md` | registro da primeira onda: custos, portão, reparo, recorte, ingestão, extração, funções, fiscal, varredura Wolfram e erros da fonte |

## Onda `2026-10-TALEB-1` (aprovada no Aura, corpus `incerto`)

Seis documentos de Taleb: *Statistical Consequences of Fat Tails*, *Convex Responses*, *Hidden Risks*,
*Tail Option Prices*, *Bitcoin, Currencies and Fragility* e *Dynamic Hedging* (este entrou por decisão do PO
de 05/10; ver a emenda de A9 na spec). Registro completo em `docs/oficina/onda-2026-10-TALEB-1.md`.

| medida | valor |
|---|---|
| documentos | 6 (6 aptos no portão) |
| trechos | 881 (`--nivel 3 --maxlen 16000`) |
| equações extraídas | 953 |
| parseáveis | 82 |
| aprovadas | 76 (82 − 6 vermelhas no Wolfram) |
| verificadas pelo Wolfram (`verificado_por` com `wolfram`) | 21 |
| conceitos / heurísticas / rótulos de equação | 30 / 19 / 20 |

**Vermelhas no Wolfram por erro da fonte** (ficam em staging; o texto da fonte não é corrigido):

| equação | o que a fonte diz | o que o Wolfram dá |
|---|---|---|
| `Convex_Responses.pdf.md#17` | `f(x) = −½ erfc(−x/√2)`, que vai de 0 a 1 | o limite em +∞ dá −1, não 1 (`Out[1]= {0, -2}`): erro de sinal |
| `Dynamic_Hedging.pdf.md#285` | `u_n = n²π²/(2(h−l)²) + λ²` | a integral em t com `e^{−λ²t/2}` dá `λ²/2` no lugar de `λ²` (resíduo ≠ 0) |
| `Statistical_Consequences_of_Fat_Tails.pdf.md#89` | `lim log(w₁x^{−α₁} + w₂x^{−α₂})/log x = α₂` | o limite é `−α₂` (`Out[1]= -2*alphaU2`) |
| `Statistical_Consequences_of_Fat_Tails.pdf.md#226` | integral `= (1 − 2^{−n})/(n+1)` | resíduo `−2^{−1−n} n/(1+n)` |
| `Statistical_Consequences_of_Fat_Tails.pdf.md#248` | `lim φ_K/K = α/(1−α)` | Pareto dá `α/(α−1)` (resíduo `Out[1]= (2*a)/(-1 + a)`); o próprio corpus (Def. 10.1, eq. 11.7) também |
| `Statistical_Consequences_of_Fat_Tails.pdf.md#268` | `p*/p = α/(1−α)` | idem: `α/(α−1)` |

**Perdas declaradas** (não convertidas, assumidas no portão): *Statistical Consequences* pp. 7–14 (sumário,
sem conteúdo doutrinário); *Convex Responses* `pic_104` (descrição de figura, HTTP 429); *Dynamic Hedging*
`pic_1726` (mermaid, `MAX_TOKENS`). **Reparo:** *Dynamic Hedging* pp. 321–340 (scan sem camada de texto,
perdidas por HTTP 429) foram reconvertidas como sub-PDF na onda `2026-10-TALEB-1-reparo-DH` e emendadas no
`.md` por `emendar_paginas.py`.

## Ambiente

- **Ingestão** (`ingerir_trechos.py`, embedding Vertex) precisa de `INCERTO_GCP_PROJETO=jazida` no ambiente.
- **Dados BR**: o SGS do BCB e o COTAHIST da B3 precisam dos hosts `api.bcb.gov.br` e
  `bvmf.bmfbovespa.com.br` liberados na política de rede do ambiente; sem eles, use o cache em `dados/` ou o
  ZIP do COTAHIST baixado à mão (`skills/taleb/references/dados-br.md`).

## Changelog

### 0.1.0 — 05/10/2026

- Bifurcação da Jazida em repositório próprio: manifesto, regras de dono único, verificador frio, CI.
- Esteira da `lavra`: portão do PO, reparo de páginas (`emendar_paginas.py`), recorte verbatim com título
  acima do corte como tópico próprio, ingestão no Neo4j, extração de equações (equação é nó, funções
  declaradas pelo PO, constantes e e π, limite de tempo do SymPy), fiscal de duas vias com prova Wolfram por
  derivação, por momento fechado e por equação, e aprovação pelo único escritor.
- Estação `taleb`: diagnósticos de caudas, convexidade e ergodicidade sobre dados BR; κ_1 exato com
  intervalo bootstrap contra o limiar 0,15 do corpus; procedência `[corpus]`/`[staging]`/`[externo]`;
  MCP `incerto-consulta`, só leitura do aprovado; três evals.
- Primeira onda, `2026-10-TALEB-1`, aprovada: 6 documentos, 881 trechos, 76 equações aprovadas
  (21 verificadas pelo Wolfram), 30 conceitos, 19 heurísticas, 20 rótulos.

## Verificar

    python3 -B build/injetar_regras.py --check --raiz . --bloco-obrigatorio regras-do-incerto
    python3 -B -W error::ResourceWarning -m unittest discover -s build/testes -t build/testes -p "teste_*.py"

<!-- bloco:regras-do-incerto:inicio (gerado de regras-do-incerto.md — edite a fonte e rode build/injetar_regras.py --write) -->
## Regras do Incerto (comuns a skills, agentes e scripts)

**Autoridade.** Comunicação em português do Brasil; o **PO humano é a autoridade final**. Contradição,
dúvida ou achado que mude o modelo do grafo vira **bloco de decisão único** ao PO, nunca mudança
silenciosa.

**Escritor único.** Só `aprovar_onda.py` e `ingerir_trechos.py` escrevem no grafo do Incerto. Todo nó e
toda aresta levam `corpus: 'incerto'`; o Lastro e o Jazida nunca escrevem nele e o Incerto nunca
escreve no grafo deles.

**Nada sem fonte.** Todo nó e toda aresta curada cita `(documento, tópico)` dos `conferidos/`; aresta
derivada leva `origem: 'derivada'` e o script que a gravou. Equação sem fonte não entra nem em staging.

**Equação é nó; fórmula em texto livre não é.** A forma canônica é o `srepr` do SymPy mais o LaTeX de
origem. "Parseável" significa `parse_latex(strict=True)`, normalização de símbolos compostos e
conferência dos símbolos contra o LaTeX; o que falha é ⚠️ com o LaTeX preservado — perda declarada fica
em staging com forma `perda`, nunca aprovada.

**Fiscal de duas vias.** `DERIVA_DE` e `:Equacao` com momento fechado só saem de staging com a prova
SymPy verde **e** a prova Wolfram verde e concordante. Divergência entre as vias é vermelho, com as
duas saídas no relato; prova vermelha é pauta da rodada, não bloqueio silencioso.

**Wolfram pelo agente.** A via Wolfram é executada pelo agente, com as ferramentas MCP do Wolfram, e o
resultado é registrado na prova. Nenhum script chama o Wolfram; a rede só é tocada pelos hosts de Dados
BR, pelo Vertex e pelo Neo4j.

**Dados BR.** Séries do mercado brasileiro só dos hosts `api.bcb.gov.br` e `bvmf.bmfbovespa.com.br`,
com cache em `dados/`. Testes **nunca** tocam a rede.

**Sem import cruzado.** Nenhum `import` nem `spec_from_file_location` aponta para `Lastro`, `jazida`,
`plugin` ou `mineiro`. O que foi copiado leva no cabeçalho
`# copiado de mabritta1984/Lastro@1676115 <caminho>`.

**Credencial.** `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `INCERTO_*` e `VERTEX_*` vêm do
ambiente ou de `~/.lastro/credencial.txt`; Vertex com token OAuth do ambiente, nunca chave de API.
Nenhuma chave de conta de serviço em repositório ou imagem.

**Nunca recomendação de ativo.** O veredito do especialista descreve exposição, convexidade e risco de
cauda; jamais manda comprar, vender ou manter um ativo.

**Marcação de procedência.** Toda afirmação do especialista sai marcada `[corpus]` (veio do grafo
aprovado), `[staging]` (veio de staging, ainda sem aprovação) ou `[externo]` (veio de fora do
corpus, como os dados BR ou o cálculo Wolfram).

**Determinismo.** Separador `/`, `newline="\n"`, ordenação por bytes,
`json.dumps(sort_keys=True, ensure_ascii=False)`, nunca timestamp de execução no que é citável;
amostragens com `random.Random(semente)` explícita.
<!-- bloco:regras-do-incerto:fim -->
