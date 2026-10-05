# Incerto — especialista de investimentos baseado em Nassim Taleb

Plugin do Claude Code, bifurcado do Jazida em repositório próprio. Um corpus de Taleb curado em grafo
(Neo4j), em que **equação é nó de primeira classe**, com **fiscal de duas vias** (SymPy e Wolfram)
antes de qualquer aprovação e dados do mercado brasileiro (BCB e B3) para análises de antifragilidade
e caudas gordas. O veredito do especialista nunca é recomendação de ativo.

**Versão:** `0.1.0-dev` (bump para `0.1.0` só na Task 20 do plano). **Spec:**
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
| `skills/lavra/scripts/conferir_onda.py` | portão do PO: relatório de fidelidade e aprovação de uma onda do `mineiro` |
| `skills/taleb/scripts/dados_br.py` | dados BR reproduzíveis: SGS do BCB e COTAHIST da B3, com cache em `dados/` e testes offline |
| `skills/taleb/references/dados-br.md` | séries do SGS, layout do COTAHIST, hosts a liberar na rede e download manual do ZIP, dono único |
| `skills/taleb/SKILL.md` | estação `taleb`: rito em cinco passos (exposição, corpus pelo MCP, dados BR, diagnósticos, Wolfram antes de afirmar conta fechada) e veredito marcado que nunca recomenda ativo |
| `skills/taleb/references/doutrina.md` | um verbete por conceito de Taleb, cada um com `fonte:` (`[externo]` até a onda 1 ser conferida) |
| `skills/taleb/references/heuristicas.md` | regras práticas com `condicao:` parseável pelo fiscal sobre `kappa`, `alpha`, `H`, `fracao_segura` |
| `evals/` | três casos de `claude plugin eval` (especialista não cita staging como corpus, Wolfram antes de conta fechada, fiscal de duas vias); corrida manual por `.github/workflows/evals.yml` |
| `build/testes/` | testes; `_carga.py` carrega módulos por caminho relativo à raiz |
| `dados/` | cache dos dados BR (conteúdo fora do git) |
| `docs/superpowers/` | spec e plano |

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
conferência dos símbolos contra o LaTeX; o que falha é ⚠️ com o LaTeX preservado — perda declarada,
nunca nó.

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
