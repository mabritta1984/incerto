# Onda `2026-10-TALEB-1` — registro

Primeira onda do corpus do Incerto, rodada e aprovada em 05/10/2026 pelo rito da estação `lavra`
(`skills/lavra/SKILL.md`). Este registro traz só o que foi medido ou decidido; os números saem dos relatórios
do portão e do fiscal e do Aura depois da aprovação.

## Documentos

Seis PDFs de Taleb, copiados para `gs://jazida-bucket/originais/TALEB/` sem sobrescrita (md5 idêntico ao de
`taleb_originais/`):

| documento | itens | equações (rota `equation`) |
|---|---|---|
| Bitcoin_Currencies_Fragility.pdf | 56 | 0 |
| Convex_Responses.pdf | 160 | 29 |
| Dynamic_Hedging.pdf | 2868 | 278 |
| Hidden_Risks.pdf | 110 | 22 |
| Statistical_Consequences_of_Fat_Tails.pdf | 3495 | 574 |
| Tail_Option_Prices.pdf | 71 | 12 |

Dynamic_Hedging entrou por decisão do PO de 05/10: é livro do próprio Taleb (1997), e a spec o punha por
engano na onda `-3`, "vizinhança" (emenda de A9 na spec).

## Conversão (`mineiro`)

- A primeira execução (run 37251436955) falhou antes de qualquer custo de modelo: faltava à conta de serviço
  do workflow a permissão `run.jobs.get` no job `mineiro-onda`. O PO concedeu `roles/run.viewer`. A execução
  seguinte, `mineiro-onda-fwzqp`, rodou os 6 documentos, com 0 falhas.
- **Custo**: 2.957.706 tokens (output 890.042, prompt 1.831.495, thoughts 236.169). Tempo de modelo 1,04 h,
  tempo de parede 2,06 h (soma dos documentos). Modelos: `gemini-2.5-pro` e `gemini-3.8-flash`. O custo em
  dólar não foi informado: a config do `mineiro` não tem preços.
- 6760 itens (9 em fallback); Mermaid válido em 46 de 47; 915 equações pela rota `equation`, todas validadas
  pelo KaTeX.
- **953 × 915**: o `.md` tem 953 blocos `$$`. Os 38 a mais são equações display que o modelo deixou dentro de
  blocos de texto (rota passthrough), não como item `equation` (DH 19, SCFT 16, HR 3). Não são perda, mas não
  passaram pelo KaTeX do `mineiro`. A extração as trata como qualquer outra.

## Portão e reparo

- **Decisão do PO**: antes de aprovar qualquer coisa para `conferidos/`, reconverter as páginas perdidas.
- *Statistical Consequences* pp. 7–14 são o sumário (CONTENTS). O "sem blocos" do modelo ali é perda sem
  conteúdo doutrinário: fica declarada e não é emendada.
- *Dynamic Hedging* é um scan ABBYY de 515 pp., sem camada de texto. As pp. 321–340 se perderam por HTTP 429
  do Vertex: vão do fim do cap. 18 (opções binárias americanas) até "Option Wizard: The Skew Revisited". Era
  perda real.
- O `mineiro` não reconverte por faixa de páginas. O reparo então converteu o sub-PDF das pp. 321–340
  (`originais/TALEB-DH-p321-340/`) na onda `2026-10-TALEB-1-reparo-DH`: 144 itens, 144 aprovados,
  0 fallbacks, 0 erros, 5 equações.
  - **Custo do reparo**: 74.650 tokens (output 17.151, prompt 54.923, thoughts 2.576), 0,04 h de parede.
  - `emendar_paginas.py` emendou o resultado no `.md`: sha256 `54268c3f…` antes e `2303ac8a…` depois, com
    sidecar `Dynamic_Hedging.pdf.reparos.json`.
  - A continuidade foi conferida: o trecho emendado começa depois da Fig. 18.14 e termina em "the put leg of
    the risk reversal reacts to", que o `.md` original continua com "one period while the call leg reacts to
    another".
- **Portão final**: 6 de 6 documentos aptos. Ficaram três perdas declaradas:
  - SCFT pp. 7–14 (sumário);
  - Convex `pic_104` (describe, HTTP 429);
  - DH `pic_1726` (mermaid, `MAX_TOKENS`).
- PO: "Aprovar e subir". O `--aprovar` gravou o manifesto e os 6 documentos em `conferidos/2026-10-TALEB-1/`
  (1452 arquivos, com o sidecar do reparo). A subida para o bucket foi feita sem sobrescrita, com MD5 conferido
  arquivo a arquivo (0 diferenças). O `.md` emendado só existe em `conferidos/`; `extraidos/` segue sendo a
  saída do `mineiro`.

## Recorte e ingestão

- PO: "Nível 3 e ingerir". A primeira passada (`--nivel 3`, sem `--maxlen`) teve 3 de 625 trechos recusados
  pelo embedding (> 8192 tokens). Com `--maxlen 30000` ainda foram recusados 2 (texto denso, ~3,6 chars/token).
  A regra declarada ficou `--nivel 3 --maxlen 16000`.
- **Defeito do recorte, achado no corpus**: um título de nível acima do corte ficava anexado ao tópico
  anterior. Exemplo: "# 3 A NON-TECHNICAL OVERVIEW…" e "## 3.1…" caíam dentro de "2.2.31 Dynamic hedging".
  Correção: esse título fecha o bloco e vira tópico próprio, e um título sem corpo entra como prefixo do bloco
  seguinte.
- **Recorte refeito (v3)**: 881 trechos. No Aura, os 646 `:Trecho` antigos da onda foram apagados (os
  `:Documento` ficaram) e os 881 foram reingeridos. O `--verificar` passou: contagem, dimensão 3072 e índices.
- A ingestão exige `INCERTO_GCP_PROJETO=jazida` no ambiente.

## Extração e funções

- 953 candidatos. Sem funções declaradas, 42 eram parseáveis. Boa parte das perdas vinha da regra "letra
  seguida de `(` é perda": numa checagem antecipada de dois documentos, foram 18 de 28.
- Duas equações do SCFT (2.7 e 5.2, `\int_0^\infty e^{\varepsilon x} dF(x) = +\infty`) travavam o SymPy. Daí
  veio o `limite_sympy.py`: equação que estoura o limite vira perda `tempo_esgotado`.
- **Decisão do PO**: declarar funções na rodada, por documento (4 decisões `declarar_funcoes`). A proposta só
  incluiu nomes com ganho e sem perda, e que são função de verdade:
  - Convex: `F, f, gamma, I_x, Q`;
  - DH: `P_H, Phi, V, p, v`;
  - SCFT: `Gamma, H, L_0, M, f, phi, varphi`;
  - TOP: `C, f`.

  Ficaram de fora `mu` no SCFT (no #231 é multiplicação, e o parse sairia errado em silêncio), `C` no Convex
  (no #13 é constante) e os nomes de uso misto. Resultado: 85 de 953 parseáveis.
- Rodada de extração das constantes e e π (opção A, o corpus decide):
  - `\pi` é a constante π, e `e^{…}` é exp;
  - π sozinho num lado, como termo de soma ou em derivada é perda `\pi_como_variavel`;
  - estatística de ordem `_{(…)}` é perda.

  Resultado final: **82 parseáveis**. O rótulo `carteira_delta_hedge` foi retirado, porque SCFT#528 virou
  perda (π como variável).

## Fiscal

- P1: 85 verdes e 868 vermelhas, ficando em staging, na rodada com funções.
- P4: 11 indeterminados ("aplica E/Var sem momento_fechado declarado"). O PO aceitou os 11 (`aceitar_indeterminado`):
  - Convex#25, DH#153, SCFT#33 e #403 dependem de Jensen/convexidade;
  - SCFT#43 e #44 dependem de independência;
  - SCFT#54, #67, #123, #195 e #387 são distribuição ou definição.
- **Conferência `[externo]`** para a Normal(0, σ): `E(X²)/E|X| − √(π/2)σ = 0` e `√E(X²)/E|X| = √(π/2)`
  (`Out[1]= {0, Sqrt[Pi/2]}`).
- **Relatório final**: 992 provas — 103 verdes, 878 vermelhas, 11 indeterminadas. 21 P4 verdes.

## Varredura Wolfram

- Das 83 equações verdes varridas:
  - 26 eram checáveis;
  - 38 eram definições;
  - 19 não tinham premissas no corpus.
- Primeira rodada de provas: 14 verdes e 12 vermelhas. As 12 vermelhas se dividem assim:
  - 4 erros reais da fonte;
  - 1 erro nosso de extração: SCFT#363, `Z_{(i)}` lido como `Z_i`, um parse errado em silêncio que a
    rodada de extração passou a declarar como perda;
  - 7 falsos vermelhos, porque e e π eram símbolos.
- Provas v2, com e e π como constantes:
  - os falsos vermelhos DH#276, #277 e SCFT#67, #187, #199, #527 viraram verdes;
  - Convex#15 saiu verde;
  - SCFT#183 saiu verde na prova v3, pela base: `CF[T3](ω) − (1+√3|ω|)e^{−√3|ω|} = 0`, com bases positivas ⇒
    potências n iguais. O código prova um lema mais forte, que implica a equação.

## Erros da fonte

Equações que parseiam, mas que o Wolfram reprova. Ficam em **staging**: vermelho nunca promove, e o texto da
fonte não é corrigido. A tabela mostra o resíduo (`fonte − verdade`) que o Wolfram devolveu.

| equação | fonte | Wolfram | diferença |
|---|---|---|---|
| Convex_Responses#17 | `f(x) = −½ erfc(−x/√2)` | limites em −∞ e +∞ menos 0 e 1: `Out[1]= {0, -2}` | em +∞ dá −1, não 1: erro de sinal |
| Dynamic_Hedging#285 | `u_n = n²π²/(2(h−l)²) + λ²` | `∫_T^∞ (t−T) e^{−λ²t/2} e^{−n²π²t/(2(h−l)²)} dt − e^{−u_n T}/u_n²` ≠ 0 | a integral dá `λ²/2` onde a fonte tem `λ²` |
| SCFT#89 | `lim_{x→∞} log(w₁x^{−α₁} + w₂x^{−α₂})/log x = α₂` | `Out[1]= -2*alphaU2` (α₁ > α₂ > 0) | o limite é `−α₂` |
| SCFT#226 | `∫_0^∞ … dK = (1 − 2^{−n})/(n+1)` | `Out[1]= -((2^(-1 - n)*n)/(1 + n))` | o lado direito está errado |
| SCFT#248 | `lim_{K→∞} φ_K/K = α/(1−α)` | `Out[1]= (2*a)/(-1 + a)` (Pareto, esperança condicional) | é `α/(α−1)`: erro de sinal |
| SCFT#268 | `p*/p = α/(1−α)` | `Out[1]= (2*a)/(-1 + a)` | é `α/(α−1)`: erro de sinal |

Nas SCFT#248 e #268, o próprio corpus confirma `α/(α−1)` (Definição 10.1 e eq. 11.7).

## Decisões pela diretriz "o corpus decide, o Wolfram valida"

Diretriz do PO (05/10): "Only Taleb can validate himself. The corpus should be used to disambiguate itself
and make decisions, Wolfram Mathematica to leverage math validation." Decidido por ela, sem bloco ao PO:

- **κ**:
  - o limiar é o do corpus, κ_1 > 0,15 (SCFT 8.3.2), sobre κ_1 = κ(1, 2) (eq. 8.8);
  - o Wolfram confere: Student T(3) dá κ_1 = 0,2904 e n = 120,7, os "120 observations" do texto;
  - `relatorio.py` passou a classificar por κ_1 exato com intervalo bootstrap (a fronteira é declarada), e a
    linha do limiar sai `[corpus]`, citando 8.3.2, a eq. 8.8 e a Tab. 8.3.
- **SCFT#248 e #268**: o erro de sinal está na fonte. O corpus e o Wolfram dão `α/(α−1)`. Viraram prova P4 por
  equação, e vermelho reprova uma equação mesmo quando ela parseia.
- **Lindy**: o corpus é coerente (5.0.2, 9.1.3, 10.2, Summary). **Peru**: o corpus dá suporte (Fig. 5.5, 3.28).
- **Recorte**: o defeito do título acima do corte foi corrigido (ver Recorte e ingestão).
- **Veredito Wolfram**:
  - verde só com 0 exato; `0.` numérico nunca é verde;
  - `ConditionalExpression[≠0, …]` é vermelho;
  - indeterminado cujo `Out` fechado é ≠ 0 é recusado.
- **e e π**: opção A (ver Extração e funções).

## Aprovação (Aura, corpus `incerto`)

- `:Equacao`: 76 aprovadas e 877 em staging. As aprovadas são as 82 parseáveis menos as 6 vermelhas no Wolfram
  (CR#17, DH#285, SCFT#89, #226, #248, #268). 21 delas têm `verificado_por` com `wolfram`, e 20 têm rótulo.
- `:Conceito` 30, `:Heuristica` 19, `SUSTENTA` 52.
- `:Trecho` 881, `:Documento` 6.
