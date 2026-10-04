# Incerto — bifurcação da Jazida para um especialista em investimentos à la Taleb (spec)

**Data:** 04/10/2026. **Pedido do PO:** bifurcar a Jazida em repositório novo, copiando de `Lastro` só o
útil; manter a extração de texto (pelo `mineiro`, consumida pelo portão) e o tratamento de equações
(equação é nó, LaTeX → SymPy, fiscal antes de aprovado); criar um **especialista em investimentos baseado
em Nassim Taleb**; usar o **Wolfram** para validar equações e análises matemáticas; analisar inicialmente
**dados do mercado brasileiro**. O material do Taleb já está no bucket, pronto para conversão.

## O que existe hoje (medido em 04/10)

| Peça | Onde | Estado |
|---|---|---|
| Originais do Taleb | `gs://jazida-bucket/taleb_originais/` — 14 PDFs, 112 MB | fora do layout do contrato (`originais/<fonte>/`); nenhuma onda rodada |
| Conversor | `mabritta1984/mineiro`, Cloud Run Job `mineiro-onda`, projeto `jazida`, bucket montado em `/mnt/corpus` | em produção (ondas `2026-09-PSX-1` e `-2` conferidas) |
| Portão do PO | `jazida/skills/lavra/scripts/conferir_onda.py` + `references/extracao-nuvem.md` | pronto, testado |
| Núcleo (Neo4j Query API, credencial, embedding Vertex) | `jazida/skills/lavra/scripts/nucleo.py` (gerado do Lastro) | pronto |
| Recorte verbatim | `plugin/skills/curadoria/scripts/recortar_chunks.py` (Lastro) | pronto; a Jazida ainda não copiou |
| Parse LaTeX → SymPy, fiscal, consulta MCP | planejados na Jazida (V6–V8), **não implementados** | só a definição de "parseável" (decisão 2 de 28/09) |
| Wolfram | MCP `WolframLanguageEvaluator` / `WolframAlpha` nesta sessão; kernel sem estado | respondeu em 04/10 (Pareto α=3/2: média 3, variância indeterminada) |
| Dados brasileiros | `api.bcb.gov.br`, `bvmf.bmfbovespa.com.br`, `dados.cvm.gov.br`, `brapi.dev`, Yahoo | **todos bloqueados** pela política de rede desta sessão (HTTP 000); `pypi.org` liberado |

## Decisões assumidas (o PO confirma ou troca; cada uma cabe numa linha)

| # | Decisão | Alternativa |
|---|---|---|
| A1 | Nome do repositório e do plugin: **`incerto`** (`mabritta1984/incerto`, privado) | outro nome |
| A2 | Repositório **novo e autônomo**: sem `plugin/` do Lastro, sem `sincronizar_nucleo.py`; o `nucleo.py` vira arquivo próprio com a proveniência no cabeçalho | manter monorepo |
| A3 | **Mesmo bucket e mesmo projeto Google** (`jazida-bucket`, projeto `jazida`, job `mineiro-onda`); os PDFs são copiados para `originais/TALEB/` porque o contrato exige `originais/<fonte>/` | bucket novo |
| A4 | **Mesmo AuraDB**, partição `corpus: 'incerto'` em todo nó e aresta (a regra da Jazida já permite) | instância nova |
| A5 | **Sem QUDT, sem `pint`, sem `rdflib`**: finanças não têm vetor dimensional útil; o fiscal passa a ser **algébrico de duas vias** (SymPy no script + Wolfram pelo agente), e as duas têm de concordar | manter análise dimensional |
| A6 | Fora do Python só `sympy` (+ `mpmath`, `antlr4` transitivas), importados dentro de função, nos arquivos permitidos; análises em biblioteca padrão (`statistics`, `math`, `random`) | `numpy`/`pandas` |
| A7 | Wolfram entra **pelo MCP do agente**, não por biblioteca Python: o agente roda o código, e `registrar_prova.py` grava a saída verbatim como prova `via: wolfram`; sem credencial Wolfram em script | `wolframclient` |
| A8 | Dados BR: BCB SGS (Selic 11, CDI 12, meta 432, IPCA 433, PTAX 1, Ibovespa 7) e **COTAHIST da B3** (arquivo anual, largura fixa); cache em disco; testes offline com fixtures; a política de rede do ambiente precisa liberar `api.bcb.gov.br` e `bvmf.bmfbovespa.com.br` | `brapi`/Yahoo |
| A9 | Ondas do Taleb em três: `2026-10-TALEB-1` **técnica** (Statistical_Consequences, Convex_Responses, Hidden_Risks, Tail_Option_Prices, Bitcoin), `-2` **Incerto** (Fooled, Black_Swan, Anti_Fragile, Skin), `-3` **vizinhança** (Dynamic_Hedging, Safe_Haven [Spitznagel], Volatility_Surface [Gatheral], Poker_Face [Brown], Basic_Laws [Cipolla]) — a 0.1.0 roda só a primeira | uma onda só |
| A10 | O especialista é uma **estação** (`skills/taleb/SKILL.md`), não um agente: responde só com marcação `[corpus]` (aprovado) / `[staging]` / `[externo]`, roda os scripts de análise e **passa toda conta fechada pelo Wolfram antes de afirmar** | agente separado |

## O que o Incerto 0.1.0 entrega

1. **Corpus** do Taleb em grafo: `:Documento`, `:Trecho` (verbatim, com embedding), `:Conceito`,
   `:Variavel`, `:Equacao` (LaTeX + `srepr`), `:Heuristica` (regra prática com `condicao` e fonte),
   `:Metodo`; relações `USA`, `DEFINIDA_POR`, `DERIVA_DE`, `VALIDA_SOB`, `EXPRESSA`, `SUSTENTA`
   (heurística → conceito/equação), `APLICA`, `MEDE`, `DEFINE`, `MENCIONA`, `DIVERGE_DE`. Nada sem
   `(documento, topico)` dos `conferidos/`.
2. **Fiscal de duas vias**: P1 parseável (decisão 2 de 28/09), P2 `DERIVA_DE` equivalente por SymPy,
   P3 relacionais de `VALIDA_SOB`/`faixa_validade` parseiam, P4 prova Wolfram presente e concordante
   para toda `DERIVA_DE` e toda `:Equacao` com forma fechada de momento. Vermelho nunca promove.
3. **Dados BR** reproduzíveis: séries do SGS e cotações do COTAHIST, retornos logarítmicos, cache.
4. **Análises de Taleb** sobre esses dados: razão máximo/soma, estimador de Hill, métrica κ,
   sobrevivência log-log, assimetria de convexidade (fragilidade), Kelly, barbell, ergodicidade
   (crescimento temporal × ensemble). Cada função nomeia a equação do corpus que implementa.
5. **Estação `taleb`** com doutrina referenciada e relatório por ativo; **MCP** `consulta_incerto`
   (`buscar_equacao`, `ler_equacao`, `ler_conceito`, `situacao_camada`); evals.

## Fora da 0.1.0

Ondas 2 e 3; agente derivador; opções e superfície de volatilidade (Dynamic_Hedging/Volatility_Surface
só entram como texto); dados intradiários; qualquer recomendação de compra/venda (o especialista
diagnostica exposição e fragilidade, não recomenda ativos); ponte `REPRESENTA` com o Lastro.

## Fórmulas que o plano pina (as provas de teste saem daqui)

| Nome | Forma | Valor de teste |
|---|---|---|
| Kelly (aposta binária) | `f* = p − (1−p)/b` | `p=0,6, b=1 → 0,2` |
| Média de Pareto | `E[X] = α L/(α−1)`, `α>1` | `α=3/2, L=1 → 3`; variância indefinida para `α≤2` (Wolfram, 04/10) |
| Hill | `α̂ = k / Σ_{i≤k} ln(X_(i)/X_(k+1))`, estatísticas de ordem decrescentes | Pareto α=1,5 simulada, n=20 000, k=500 → `|α̂−1,5| < 0,3` |
| Razão máximo/soma | `R_n(p) = max|X_i|^p / Σ|X_i|^p` | gaussiana p=4, n=20 000 → `R_n < 0,05`; Pareto α=1,5, p=2 → `R_n > 0,1` |
| κ (Taleb, SCFT cap. "kappa") | `κ(n0,n) = 2 − (ln n − ln n0)/ln(M(n)/M(n0))`, `M(n)=E|S_n − E S_n|` | gaussiana → `|κ| < 0,15`; Cauchy → `|κ−1| < 0,15` (n0=1, n=30, 4 000 reamostras, semente 7) |
| Assimetria de convexidade | `H = [f(x+Δ)+f(x−Δ)]/2 − f(x)` | `x²,Δ=1 → 1` (antifrágil); `−x² → −1` (frágil); linear → 0 |
| Barbell | perda máxima da carteira = `(1−s)·perda_máxima_convexa` | `s=0,9 → 0,1` |
| Ergodicidade | temporal `E[ln(1+r)]` × ensemble `E[r]` | r∈{+0,5; −0,4}: ensemble `+0,05`, temporal `ln(0,9)/2 ≈ −0,0527` |
