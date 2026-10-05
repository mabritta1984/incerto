# Aceite manual da estação `taleb` — incerto 0.1.0 (Task 20)

- **Data:** 2026-10-05
- **Branch / commit:** `release/incerto-0.1.0` @ `2306f21604d44e05e6eb4395941d63d7825e119d`
  (`docs: incerto 0.1.0 — changelog, spec A9, eval, registro da onda`). O aceite começou em `91de532`; durante
  a rodada outro agente commitou `2306f21`, que só troca a versão para `0.1.0` e explicita no `SKILL.md` que
  a onda `2026-10-TALEB-1` está aprovada e que, dos seis rótulos do `relatorio.py`, só `assimetria_convexidade`
  é `:Equacao` aprovada. O rito e o formato não mudaram; as marcas abaixo já seguem o texto de `2306f21`.
- **Quem jogou a estação:** o agente, seguindo `skills/taleb/SKILL.md` e as references `doutrina.md`,
  `heuristicas.md`, `dados-br.md` e `skills/lavra/references/fiscal.md`.
- **MCP `incerto-consulta`** (chamado direto em Python, `INCERTO_GCP_PROJETO=jazida`), `situacao_camada` verbatim:

```json
{
 "corpus": "incerto",
 "servidor": "incerto-consulta",
 "versao": "0.1.0-dev",
 "database": "7a5fa0fc",
 "aprovados": {
  "Conceito": 30,
  "Documento": 5,
  "Equacao": 76,
  "Heuristica": 19,
  "Variavel": 83
 },
 "trechos": 881,
 "indices": {
  "trecho_texto_incerto": "FULLTEXT ONLINE",
  "trecho_embedding_incerto": "VECTOR ONLINE"
 },
 "neo4j": "ok"
}
```

  (Observação: o servidor ainda se anuncia `"versao": "0.1.0-dev"`, enquanto o `SKILL.md` já diz `0.1.0` —
  ver "Falhas e achados".)

- **Rede: em duas fases.**
  - **Rodada 1, rede BLOQUEADA.** No início do aceite, `api.bcb.gov.br` e `bvmf.bmfbovespa.com.br` estavam
    bloqueados pelo proxy (HTTP 403 no túnel), e `dados/` não tinha nem o ZIP do COTAHIST nem cache do SGS. As
    dez perguntas foram respondidas nessa condição. Saídas verbatim no fim deste item.
  - **Rodada 2, rede LIBERADA pelo PO.** Durante o aceite o PO liberou os dois hosts, e o coordenador baixou à
    mão `dados/COTAHIST_A2024.ZIP` (sha256 `96a003d10fab0fa2ace0c64cdc2b892b4c111adf9da8e538aa0b28437bd2a172`,
    251 linhas de PETR4, todas `TPMERC 010`). O código não baixou COTAHIST. As perguntas 1 e 2 foram refeitas
    com dados reais (seção "Rodada 2" de cada uma). As séries do SGS vieram **da rede, não do cache**: nenhum
    `dados/sgs-*.json` existia antes das chamadas, e cada uma gravou o seu. Uma chamada ao SGS 11 devolveu
    HTTP 502 uma vez e funcionou na repetição.
  - Em nenhuma fase foi usada outra fonte de dados (sem espelho no BigQuery, sem web).

  Saídas verbatim do `dados_br.py` na rodada 1:

```
$ python3 skills/taleb/scripts/dados_br.py --cotahist dados/COTAHIST_A2024.ZIP --ticker PETR4
erro: [Errno 2] No such file or directory: 'dados/COTAHIST_A2024.ZIP'

$ python3 skills/taleb/scripts/dados_br.py --sgs 11 --inicio 2024-01-01 --fim 2024-12-31
erro: SGS 11: falha de rede (<urlopen error Tunnel connection failed: 403 Forbidden>) em https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json&dataInicial=01/01/2024&dataFinal=31/12/2024
```

- **Fonte de `[staging]`:** só os arquivos locais
  `…/scratchpad/corpus/_esteira/incerto/equacoes-2026-10-TALEB-1.jsonl` (953 candidatos) e
  `decisoes-2026-10-TALEB-1.jsonl` (84 decisões, 20 `rotular_equacao`). Um candidato só foi marcado
  `[staging]` depois de o MCP responder "não encontrada no corpus aprovado" para ele.
- **Mapa rótulo → status dos `EQ_*` do `relatorio.py`** (via `ler_equacao`): `assimetria_convexidade` →
  aprovado (`Convex_Responses.pdf.md#1`); `kappa`, `hill`, `razao_max_soma`, `crescimento_temporal`,
  `crescimento_ensemble` → "não encontrada no corpus aprovado" e ausentes dos rótulos da esteira local, ou seja,
  `[externo]`. (`kelly` e `barbell` também não estão aprovados.)
- **Wolfram:** `WolframLanguageEvaluator` pelo MCP; entrada e saída coladas verbatim em cada resposta.
- **Convenção de marcas usada aqui:** o que o MCP devolveu (definição de conceito, enunciado de heurística,
  LaTeX de equação aprovada e o `(documento, tópico)` que `buscar_equacao` localiza) é `[corpus]`; a localização
  de `buscar_equacao` atesta só o lugar, não o conteúdo do tópico ("localiza, não atesta"). Cálculo Wolfram,
  saída de script e as linhas `fonte:` de `doutrina.md`/`heuristicas.md` são `[externo]`.

---

## Pergunta 1 — "PETR4 em 2024 é Extremistão?"

### Rodada 1 (rede bloqueada) — resposta da estação

## Pergunta como exposição
A exposição é uma posição comprada em PETR4 ao longo de 2024: payoff linear no preço, f(S) = S. A pergunta de
domínio vira: os retornos diários dessa exposição têm uma cauda em que um só dia domina a soma (κ_1 alto,
α̂ < 2) ou se comportam como no Mediocristão? Para responder é preciso medir sobre a série, e não há série.

## Corpus
`situacao_camada`: corpus `incerto`, 76 equações, 30 conceitos e 19 heurísticas aprovados, `neo4j: ok`.
- Extremistão [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, Payoff swamps probability in
  Extremistan): "Domínio de caudas gordas em que eventos raros têm papel desproporcional nas propriedades".
- métrica kappa [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 2.2.5 Kappa Metric), com a heurística
  "kappa acima de 0,15" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 8.3.2 Practical significance
  for sample sufficiency).
- `ler_equacao` para `kappa`, `hill`, `razao_max_soma`: "não encontrada no corpus aprovado". Esses rótulos não
  estão na esteira local; os números deles sairiam `[externo]`. A definição κ(n0, n) da eq. 8.1 existe só como
  candidato `Statistical_Consequences_of_Fat_Tails.pdf.md#171` [staging], forma `perda`
  (`nao_suportado:kappa(`).

## Dados
- COTAHIST 2024: **ausente**. `dados/COTAHIST_A2024.ZIP` não existe
  (`erro: [Errno 2] No such file or directory: 'dados/COTAHIST_A2024.ZIP'`), e `bvmf.bmfbovespa.com.br` está
  bloqueado neste ambiente. O COTAHIST nunca é baixado por código.
- SGS 11 (Selic diária, a taxa livre do relatório): **ausente**. A rede para `api.bcb.gov.br` falhou
  (`Tunnel connection failed: 403 Forbidden`) e não há cache em `dados/`.
- Para seguir, o PO precisa baixar à mão `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A2024.ZIP`
  e colocá-lo em `dados/` sem descompactar, e liberar `api.bcb.gov.br` ou gravar o JSON do SGS 11 de 2024 no
  formato do cache (`references/dados-br.md`) [externo].

## Diagnóstico
Sem dado, não há diagnóstico numérico. `relatorio.py` não foi rodado: κ_1, α̂ de Hill, razão máximo/soma e H
de PETR4 em 2024 **não foram medidos**, e nenhuma heurística numérica é avaliada. Esta resposta para aqui.

## Conferência Wolfram
Nenhuma conta fechada afirmada; nada a conferir.

## Veredito
Domínio: **não diagnosticado**, por falta do COTAHIST 2024 e da série SGS 11. Classe de fragilidade e
ergodicidade: não diagnosticadas. Não se infere Extremistão nem Mediocristão sem a série: uma janela não
observada não é evidência de nenhum dos dois.

Isto não é recomendação de ativo.

### Checklist — rodada 1

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Conceitos e heurística `[corpus]` com (documento, tópico); #171 `[staging]` após o MCP negar; instrução de download `[externo]`. |
| `[corpus]` só para o que o MCP devolveu | ✔ | Definição de Extremistão, conceito e heurística de κ vieram de `ler_conceito`. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Nenhuma conta fechada afirmada. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |
| Comportamento esperado (declarar o dado faltante e parar) | ✔ | Diz o que falta e como obter; não mede nada. |

### Rodada 2 (rede liberada, COTAHIST 2024 em `dados/`) — resposta da estação

## Pergunta como exposição
A exposição é uma posição comprada em PETR4 ao longo de 2024, de payoff linear no preço. A pergunta de domínio
vira: os retornos logarítmicos diários de 2024 têm uma cauda em que poucos dias dominam a soma (κ_1 alto, α̂ < 2)?
A forma da resposta a choques de ±2σ é côncava, linear ou convexa? E o caminho único de quem carregou a posição
cresceu menos que a média de ensemble?

## Corpus
`situacao_camada`: corpus `incerto`, 76 equações, 30 conceitos e 19 heurísticas aprovados, `neo4j: ok`
(verbatim no cabeçalho).

Mapa `--status-equacoes`, montado pelo `ler_equacao` de cada `EQ_*` do `relatorio.py`:

```json
{"assimetria_convexidade": "aprovado"}
```

- `assimetria_convexidade` → aprovado, `Convex_Responses.pdf.md#1` [corpus] — (Convex_Responses.pdf.md, III.
  ANTIFRAGILITY IN ONCOLOGY).
- `kappa`, `hill`, `razao_max_soma`, `crescimento_temporal`, `crescimento_ensemble` → "não encontrada no corpus
  aprovado". Nenhum desses cinco rótulos está nas decisões `rotular_equacao` da esteira local, então ficam fora do
  mapa e saem `[externo]`. A definição κ(n0, n) existe na esteira só como candidato sem rótulo,
  `Statistical_Consequences_of_Fat_Tails.pdf.md#171` [staging], forma `perda`.
- Extremistão [corpus] — (SCFT, Payoff swamps probability in Extremistan); métrica kappa [corpus] — (SCFT, 2.2.5
  Kappa Metric) com a heurística "kappa acima de 0,15" [corpus] — (SCFT, 8.3.2 Practical significance for sample
  sufficiency).
- caudas gordas [corpus] — (SCFT, A WORD ON TERMINOLOGY), com a heurística "Sharpe, beta e variância não informam"
  [corpus] — (SCFT, Summary of the problem with overstandardized statistics).
- ergodicidade [corpus] — (SCFT, 3.10 RUIN AND PATH DEPENDENCE).

## Dados
- **COTAHIST 2024**: `dados/COTAHIST_A2024.ZIP`, baixado à mão pelo coordenador (o código nunca o baixa). PETR4:
  251 pregões, todos no mercado à vista (`TPMERC 010`), de 2024-01-02 a 2024-12-30, que dão 250 retornos
  logarítmicos de 2024-01-03 a 2024-12-30 [externo].
- **SGS 11** (Selic diária), 2024-01-03 a 2024-12-30: **veio da rede, não do cache**. `dados/` não tinha
  `sgs-11-*` antes da chamada; o `relatorio.py` baixou e gravou `dados/sgs-11-2024-01-03-2024-12-30.json`
  (251 observações) [externo].
- **Aviso**: os preços do COTAHIST **não são ajustados por proventos nem desdobramentos**. PETR4 distribui
  proventos, e uma data ex aparece como queda espúria no fechamento. Os piores retornos de 2024 foram:
  - 2024-03-08 −0,1117
  - 2024-05-15 −0,0623
  - 2024-12-12 −0,0570
  - 2024-05-03 −0,0558
  - 2024-02-28 −0,0530
  - 2024-06-12 −0,0501

  A estação **não verificou** quais deles são datas ex-provento, e não há fonte de proventos no contrato de
  dados. A cauda esquerda pode estar contaminada [externo].

## Diagnóstico
Comando:
`python3 skills/taleb/scripts/relatorio.py --ticker PETR4 --cotahist dados/COTAHIST_A2024.ZIP --sgs-cache dados --status-equacoes <scratchpad>/status-equacoes.json`
(código de saída 0, stderr vazio). Saída verbatim:

```
# Relatório de PETR4

- Amostra: 250 retornos logarítmicos diários, de 2024-01-03 a 2024-12-30 — fonte: dados B3/COTAHIST [externo]

Preços do COTAHIST não são ajustados por proventos ou desdobramentos; um desdobramento aparece como retorno espúrio.
Fonte de cada número: nome da equação e marcação corpus, staging ou externo (externo = a equação não consta como aprovada ou em staging no grafo).

## Caudas

- κ_1 = κ(n0=1, n=2), exato = 0.256893, IC95% bootstrap [0.094095; 0.400370] — equação `kappa` [externo]
- κ(n0=1, n=30) = 0.159696 (informativo) — equação `kappa` [externo]
- α̂ de Hill, cauda esquerda, k=12 = 1.824047 — equação `hill` [externo]
- razão máximo/soma R_n(p=2) = 0.165873 — equação `razao_max_soma` [externo]
- razão máximo/soma R_n(p=4) = 0.615188 — equação `razao_max_soma` [externo]

## Convexidade

- assimetria empírica H (choque de ±2σ, por quantis) = -0.004913, IC95% bootstrap [-0.014521; 0.002986] — equação `assimetria_convexidade` [corpus]
- classe: **robusto** — antifrágil se o intervalo de H fica todo acima de 0, frágil se todo abaixo, robusto se contém 0 (ruído amostral não decide a classe) — equação `assimetria_convexidade` [corpus]

## Ergodicidade

- crescimento temporal (média de ln(1+r)) = -0.000172 — equação `crescimento_temporal` [externo]
- crescimento de ensemble (média aritmética de r) = -0.000023 — equação `crescimento_ensemble` [externo]
- taxa livre de risco diária = 0.000408 — fonte: SGS série 11, média de 251 observações (2024-01-03 a 2024-12-30) [externo]
- excesso de crescimento temporal sobre a taxa livre = -0.000580 — equação `crescimento_temporal` [externo]

## Veredito

- domínio: **Extremistão** — derivado de κ e α̂ (equações `kappa` e `hill`) [externo]
- limiares: Extremistão se κ_1 > 0.15 (todo o IC95%; Mediocristão se todo ≤ 0.15, senão fronteira) — limiar do corpus, fonte: SCFT 8.3.2 (Statistical_Consequences_of_Fat_Tails.pdf.md, 8.3.2 Practical significance for sample sufficiency), eq. 8.8 (κ_1 em uso) e Table 8.3 (8.2 THE METRIC) [corpus]
- limiares: ou se α̂ < 2 — limiar do incerto [externo]
- κ_1 = 0.256893, IC95% bootstrap [0.094095; 0.400370] — equação `kappa` [externo]
- α̂ = 1.824047 — equação `hill` [externo]
- fragilidade: **robusto** — H = -0.004913, IC95% bootstrap [-0.014521; 0.002986] — equação `assimetria_convexidade` [corpus]

Isto não é recomendação de ativo.
```

Leitura, sem promover marca:
- **O domínio sai pelo α̂, não pelo κ.** O IC95% de κ_1 é [0,094; 0,400] e **contém 0,15**. Só pelo κ, PETR4 2024
  seria **fronteira** [externo, números; limiar corpus]. O Extremistão vem de α̂ = 1,82 < 2 [externo], que pela
  regra 1 do `relatorio.py` decide sozinho.
- Sensibilidade de α̂ ao k de Hill (`caudas.hill(xs, k, "esquerda")` sobre os mesmos 250 retornos) [externo]:

  | k | α̂ |
  |---|---|
  | 10 | 1,8391 |
  | 12 | 1,8240 |
  | 15 | 1,7703 |
  | 20 | 1,8978 |
  | 25 | 1,6595 |
  | 30 | 1,5717 |

  Fica abaixo de 2 em toda a faixa, mas sai de 12 a 30 estatísticas de ordem de um único ano, e o maior desses
  dias pode ser data ex-provento (aviso em "Dados").
- O máximo responde por 16,6% da soma dos quadrados e por 61,5% da soma das quartas potências [externo]: um só dia
  domina o quarto momento da amostra.
- Classe **robusto** [corpus, equação]: o IC de H contém 0, e não se declara frágil nem antifrágil.
- Ergodicidade [externo, números]:
  - crescimento temporal −0,000172/dia, abaixo do de ensemble (−0,000023/dia);
  - excesso sobre a Selic diária média de 2024: −0,000580/dia;
  - quem carregou só PETR4 ao fechamento não ajustado ficou atrás do lado sem risco. Sem proventos, isso
    **superestima** o atraso.
- Heurísticas que disparam:
  - "variância inútil no Extremistão" (`kappa > 0.15 or alpha < 2`, por α̂) [externo] — `heuristicas.md`;
  - "Sharpe, beta e variância não informam" [corpus] (SCFT, Summary of the problem with overstandardized
    statistics);
  - "sem ergodicidade, ignorar o ensemble" [corpus] (SCFT, 3.10): a exposição é multiplicativa.
- Heurísticas que **não** disparam:
  - "kappa acima de 0,15" [corpus]: o limite inferior do IC, 0,094, não passa de 0,15;
  - "exposição côncava primeiro", "o peru no Extremistão", "convexidade que paga na cauda": H não tem sinal
    definido;
  - "Mediocristão não é atestado de segurança": α̂ < 2.

## Conferência Wolfram
Os números acima saíram prontos do script e não são contas fechadas. A única conta fechada afirmada em prosa é a
consequência de α̂ < 2 para a variância, implícita em "variância inútil":

```
(* momento p de cauda Pareto: finito só se alpha > p; com o alpha-hat de Hill de PETR4 2024 (1.824047), p = 2 *)
{Integrate[x^p alpha L^alpha x^(-alpha - 1), {x, L, Infinity}, Assumptions -> L > 0 && alpha > 0 && p > 0], 1.824047 > 2}
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {ConditionalExpression[(alpha*L^p)/(alpha - p), alpha > p], False}
```

Confirma: numa cauda Pareto com α = 1,824, o segundo momento não existe (α > 2 é falso). Vale **se** a cauda
esquerda de PETR4 for de fato de lei de potência com esse α. É uma estimativa de um ano, não um fato da
distribuição.

## Veredito
- **Domínio: Extremistão pelo critério da estação**, decidido por α̂ de Hill = 1,82 < 2 [externo]. Pelo κ_1 =
  0,257, com IC95% [0,094; 0,400], o caso seria **fronteira**, porque o intervalo contém o limiar 0,15 [corpus].
  O diagnóstico depende de 12 estatísticas de ordem de um ano de preços **não ajustados por proventos**
  [externo]. Leia-se como "Extremistão, com amostra curta e cauda esquerda possivelmente contaminada por datas
  ex".
- **Classe: robusto** [corpus]: H = −0,0049, IC95% [−0,0145; 0,0030] contém 0.
- **Ergodicidade**: crescimento temporal abaixo do de ensemble e da Selic em 2024 [externo]. O ensemble não
  descreve o caminho [corpus].
- **Heurísticas**: "variância inútil no Extremistão" [externo]; "Sharpe, beta e variância não informam" [corpus];
  "sem ergodicidade, ignorar o ensemble" [corpus].
- **Conta conferida**: E[X²] não existe com α = 1,824 [externo, Wolfram].

Isto não é recomendação de ativo.

### Checklist — rodada 2

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Números do script com as marcas que ele imprime. `assimetria_convexidade` `[corpus]` porque o MCP a achou. Os outros cinco rótulos `[externo]`: nem aprovados nem rotulados na esteira. Dados BR `[externo]`. |
| `[corpus]` só para o que o MCP devolveu | ✔ | A linha do limiar 0,15 sai `[corpus]` fixa no script. O MCP de fato devolveu esse limiar (heurística "kappa acima de 0,15", 8.3.2), então a marca confere. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Uma conta (momento p); o resto é saída de script. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | No relatório e na resposta. |
| Dados `[externo]` e cache declarado | ✔ | SGS 11 veio da rede e gravou o cache; o COTAHIST é local, baixado à mão. |

---

## Pergunta 2 — "Um barbell 90/10 Tesouro Selic + opções fora do dinheiro: qual a perda máxima?"

### Rodada 1 (rede bloqueada) — resposta da estação

## Pergunta como exposição
Carteira de valor inicial 1: fração w = 0,9 em Tesouro Selic, rendendo a taxa r acumulada no horizonte; fração
1 − w = 0,1 gasta em prêmio de opções fora do dinheiro (N opções ao prêmio c, com N·c = 0,1), de payoff X ≥ 0
no vencimento. A perda máxima é a do cenário em que todas as opções expiram sem valor (X = 0). Ela é
delimitada por construção, sem previsão, e depende de r. Sem a Selic medida, a resposta é simbólica em r e c.

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados, `neo4j: ok`.
- barbell [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 25.1 LEFT TAIL RISK AS THE CENTRAL
  PORTFOLIO CONSTRAINT): "conservadorismo máximo numa fração w e risco máximo (ou alto) na fração 1 − w
  restante; a perda é limitada pela construção, não por estimativa."
- heurística "perda máxima pela fração em numerário" [corpus] — (mesmo documento, 25.1): "a fração em
  numerário fixa a perda máxima independentemente de qualquer modelo de retornos (80% em numerário: risco nulo
  de perder mais de 20%)."
- heurística "custo do seguro junto com o que ele protege" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md,
  24.3 THE INSEPARABILITY OF INSURANCE AND INSURED).
- `ler_equacao("barbell")`: "não encontrada no corpus aprovado"; a perda do barbell não é equação aprovada, e a
  fórmula abaixo é `[externo]` (Wolfram).

## Dados
- SGS 11 (Selic diária) e SGS 432 (meta Selic): **ausentes**. A rede para `api.bcb.gov.br` está bloqueada
  (`erro: SGS 11: falha de rede (<urlopen error Tunnel connection failed: 403 Forbidden>) …`) e não há cache
  em `dados/`. **A Selic numérica falta**: a resposta fica em função de r [externo].
- Prêmio das opções: não informado pelo PO, e não há fonte de dados de opções no contrato da estação. Fica c
  simbólico.

## Diagnóstico
- `convexidade.barbell(0.9, 1.0)` → `{'perda_maxima_carteira': 0.09999999999999998, 'fracao_segura': 0.9,
  'fracao_convexa': 0.09999999999999998}` [externo]. O modelo do script trata o lado seguro com perda **e
  retorno** nulos: perda máxima de 10% (`doutrina.md`, verbete barbell, [externo]).
- Com o rendimento da Selic no horizonte (Wolfram, abaixo) [externo]:
  - perda máxima = 1 − w(1 + r); com w = 9/10, **L(r) = 1/10 − 9r/10 = 1 − 0,9·(1 + r)**;
  - em termos do prêmio, com N opções a c: **L = N·c − (1 − N·c)·r**. O prêmio só entra pelo orçamento N·c;
    com N·c = 0,1 recai em L(r);
  - L(r) ≤ 10% para todo r ≥ 0, e L = 0 quando r = 1/9 (≈ 11,1% acumulado no horizonte). Se isso acontece, a
    estação não diz: depende da Selic, que falta.
- Heurísticas que disparam:
  - "perda máxima delimitada por construção" (`fracao_segura` = 0,9 ≥ 0,85) [externo] — `heuristicas.md`;
  - "perda máxima pela fração em numerário" [corpus] — (SCFT, 25.1).
- Ressalva de modelo [externo]: o "lado seguro sem perda" é simplificação. O Tesouro Selic tem marcação a
  mercado (ágio/deságio) e risco soberano. A perda máxima de fato é a desta fórmula somada a essa parcela, que
  não foi medida.

## Conferência Wolfram
1. Perda máxima geral (fração w, opções ao prêmio c, payoff X ≥ 0):

```
MaxValue[{1 - (w (1 + r) + ((1 - w)/c) X), X >= 0 && c > 0 && 0 < w < 1 && r > -1}, X]
```

```
Symbol::undefined2: Warning: Global symbols "X, X, X" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= Piecewise[{{1 - w - r*w, r > -1 && Inequality[0, Less, w, Less, 1] && c > 0}}, -Infinity]
```

Confirma 1 − w(1 + r) no domínio declarado (o ramo `-Infinity` é fora dele).

2. Com w = 9/10: forma, ponto de perda nula e limite de 10% para r ≥ 0:

```
With[{perda = 1 - w (1 + r)}, {perda /. w -> 9/10, Solve[(perda /. w -> 9/10) == 0, r], Simplify[(perda /. w -> 9/10) <= 1/10, Assumptions -> r >= 0]}]
```

```
Out[1]= {1 - (9*(1 + r))/10, {{r -> 1/9}}, True}
```

Confirma.

3. Forma pelo prêmio (N opções a c), diferença contra N·c − (1 − N·c)·r:

```
(* barbell com N opções a prêmio c: gasto N c, resto (1 - N c) na Selic à taxa r no período *)
Simplify[MaxValue[{1 - ((1 - nN c) (1 + r) + nN X), X >= 0 && c > 0 && nN > 0 && nN c < 1 && r > -1}, X] - (nN c - (1 - nN c) r)]
```

```
Symbol::undefined2: Warning: Global symbols "X, X, X" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= Piecewise[{{-Infinity, c <= 0 || c >= nN^(-1) || nN <= 0 || r <= -1}}, 0]
```

Confirma: a diferença é 0 no domínio (c > 0, N > 0, N·c < 1, r > −1).

## Veredito
- Perda máxima do barbell 90/10: **L(r) = 1 − 0,9·(1 + r)** do capital, e no máximo 10% para qualquer Selic
  não negativa no horizonte. Vem da construção, não de estimativa [externo, conferido no Wolfram]; é o que diz
  o barbell [corpus] (SCFT, 25.1).
- Valor numérico: **não afirmado**. Falta a Selic (SGS 11/432).
- O lado convexo é limitado ao prêmio pago: sem ruína pela construção, desde que o lado seguro não tenha perda
  própria [externo].
- O custo do prêmio é avaliado junto com o que ele protege [corpus] (SCFT, 24.3).
- Domínio e classe: não aplicáveis sem série.

Isto não é recomendação de ativo.

### Checklist — rodada 1

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | Conceito barbell e duas heurísticas via `ler_conceito`; a fórmula é `[externo]`. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Três avaliações; a saída 1 e a 3 são `Piecewise` cujo ramo no domínio é o afirmado (lido e declarado, não escondido). |
| Sem recomendação | ✔ | Não diz se o barbell "vale a pena" nem dimensiona; o 90/10 é do PO. |
| Linha final presente | ✔ | |
| Selic numérica declarada ausente | ✔ | |

### Rodada 2 (rede liberada, Selic do SGS) — resposta da estação

## Pergunta como exposição
A mesma da rodada 1. Carteira de valor 1, com w = 0,9 em Tesouro Selic, rendendo a Selic acumulada r no horizonte,
e 0,1 em prêmio de opções fora do dinheiro (N·c = 0,1), de payoff X ≥ 0. A perda máxima é a do cenário em que as
opções expiram sem valor: **L(r) = 1 − 0,9·(1 + r)**. Agora com a Selic medida. O horizonte adotado é de **um ano
(12 meses)**, porque o PO não deu o prazo, e a taxa usada é a **realizada** nos últimos 12 meses fechados. A
estação não prevê a Selic dos próximos 12 meses.

## Corpus
Igual à rodada 1:
- barbell [corpus] e "perda máxima pela fração em numerário" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md,
  25.1 LEFT TAIL RISK AS THE CENTRAL PORTFOLIO CONSTRAINT);
- "custo do seguro junto com o que ele protege" [corpus] — (SCFT, 24.3 THE INSEPARABILITY OF INSURANCE AND
  INSURED);
- `ler_equacao("barbell")`: não aprovada, e a fórmula é `[externo]`.

## Dados
Séries de `references/dados-br.md`: `selic_diaria` = SGS 11 (% a.d.) para o acúmulo, e `selic_meta` = SGS 432
(% a.a.) como referência. As duas **vieram da rede, não do cache**: `dados/` não tinha `sgs-11-2025-10-05-…` nem
`sgs-432-…` antes das chamadas, e cada chamada gravou o seu arquivo. O período termina em 2026-10-04, ontem: hoje
não vai ao cache. A primeira chamada ao SGS 11 voltou `HTTP 502`; a segunda funcionou [externo].

- `python3 skills/taleb/scripts/dados_br.py --sgs 11 --inicio 2025-10-05 --fim 2026-10-04`
  - 250 observações, de 2025-10-06 a 2026-10-02;
  - valores distintos e contagens:

    | % a.d. | dias |
    |---|---|
    | 0,055131 | 113 |
    | 0,054266 | 28 |
    | 0,0534 | 33 |
    | 0,052531 | 35 |
    | 0,05166 | 29 |
    | 0,050788 | 12 |

  - cache gravado: `dados/sgs-11-2025-10-05-2026-10-04.json` [externo].
- `python3 skills/taleb/scripts/dados_br.py --sgs 432 --inicio 2025-10-05 --fim 2026-10-04`
  - 365 observações;
  - meta de 15,00% a.a. em 2025-10-05; cortes para 14,75% (2026-03-19), 14,5% (2026-04-30), 14,25% (2026-06-18),
    14,0% (2026-08-06) e **13,75% a.a. desde 2026-09-17**;
  - cache gravado: `dados/sgs-432-2025-10-05-2026-10-04.json` [externo].
- Prêmio das opções: continua não informado e sem fonte no contrato. c e N ficam simbólicos; só o orçamento
  N·c = 0,1 entra.

## Diagnóstico
- Fator acumulado da Selic diária em 250 dias úteis: **1,144011**, ou seja, r ≈ **14,40%** nos 12 meses
  [externo, Wolfram, conferido em Python: `1.1440105168676946`].
- **Perda máxima numérica**: L = 1 − 0,9 × 1,144011 = **−0,0296**. No pior cenário (opções sem valor) a carteira
  ainda **termina ≈ 2,96% acima** do capital inicial, e a perda máxima nominal é **0** [externo, Wolfram].
- Com a meta vigente, 13,75% a.a., tomada como taxa do ano: L = −0,02375, ou seja, ganho mínimo de 2,375%, e a
  perda máxima nominal também é 0. Isso **não é previsão**: é a mesma conta sobre outro valor de r [externo,
  Wolfram].
- Ponto de perda nula: r = 1/9 ≈ 11,11% no horizonte. Abaixo disso, L = 1 − 0,9(1 + r) > 0. Com r ≥ 0, sempre
  L ≤ 10% [externo, Wolfram, rodada 1].
- `convexidade.barbell(0.9, 1.0)` → `0.09999999999999998` [externo]. Esse 10% é a perda com o lado seguro de
  **retorno nulo** (modelo do script). É o teto independente da Selic, e não o valor com a Selic medida.
- Ressalvas [externo]: a perda é **nominal** e antes de imposto de renda, custódia e corretagem. Ignora a inflação
  (a perda real é outra conta), a marcação a mercado do Tesouro Selic e o risco soberano. O horizonte de 12 meses
  e a taxa realizada no passado são escolhas desta resposta, não do PO.
- Heurísticas: "perda máxima delimitada por construção" (`fracao_segura` 0,9 ≥ 0,85) [externo]; "perda máxima
  pela fração em numerário" [corpus].

## Conferência Wolfram

```
(* Selic diária SGS 11, 2025-10-06 a 2026-10-02: 250 observações (% a.d.), em contagens por valor; fator acumulado e perda máxima L = 1 - w (1 + r) com w = 9/10 *)
With[{fator = (1 + 0.050788/100)^12 (1 + 0.05166/100)^29 (1 + 0.052531/100)^35 (1 + 0.0534/100)^33 (1 + 0.054266/100)^28 (1 + 0.055131/100)^113}, {12 + 29 + 35 + 33 + 28 + 113, fator, fator - 1, 1 - (9/10) fator, 1 - (9/10) (1 + 0.1375), Max[0, 1 - (9/10) fator], N[1/9]}]
```

```
Out[1]= {250, 1.1440105168676933, 0.14401051686769328, -0.029609465180924, -0.023749999999999938, 0, 0.1111111111111111}
```

Confirma:
- as contagens somam 250;
- fator 1,1440105 (difere do Python só em 1,3·10⁻¹⁵, arredondamento);
- r = 14,40%;
- L = −0,02961 com a Selic realizada e −0,02375 com a meta de 13,75%;
- perda máxima nominal = max(0, L) = 0;
- ponto de perda nula r = 1/9.

A forma simbólica L(r) = 1 − w(1 + r) e L = N·c − (1 − N·c)·r foi conferida na rodada 1 (saídas verbatim acima).

## Veredito
- **Simbólica**: L(r) = 1 − 0,9·(1 + r), ou N·c − (1 − N·c)·r. No máximo 10% para r ≥ 0. É perda delimitada por
  construção [corpus, conceito barbell; conta externo, Wolfram].
- **Numérica** (horizonte de 12 meses, Selic realizada de 2025-10-06 a 2026-10-02 do SGS 11, r = 14,40%):
  **perda máxima nominal = 0**. No pior cenário a carteira termina ≈ +2,96% [externo, Wolfram]. Isso vale enquanto
  a Selic do horizonte ficar acima de 11,11%; a estação não diz se ficará.
- O teto de 10% (`convexidade.barbell`) vale para qualquer Selic não negativa [externo].
- O prêmio das opções é avaliado junto com o que protege [corpus].

Isto não é recomendação de ativo.

### Checklist — rodada 2

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Dados SGS `[externo]`; fórmula e números `[externo]`; conceito e heurística `[corpus]`. |
| `[corpus]` só para o que o MCP devolveu | ✔ | |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Fator, r, L numérico, L pela meta e o ponto 1/9 na mesma avaliação; a forma simbólica, na rodada 1. |
| Sem recomendação | ✔ | Não diz se o barbell convém; o horizonte e a taxa são declarados como escolhas da resposta. |
| Linha final presente | ✔ | |
| Selic do SGS (código da `dados-br.md`) e cache declarado | ✔ | SGS 11 para o acúmulo e 432 como referência; os dois da rede, com cache gravado. |

---

## Pergunta 3 — "Que valor de κ separa Mediocristão de Extremistão, e por quê?"

### Resposta da estação

## Pergunta como exposição
A pergunta é de método: a partir de que κ a média amostral de uma exposição deixa de ser informativa no
horizonte de dados que se tem? Em termos de payoff, o tema é quanto a soma (o P&L acumulado) depende de poucos
eventos. Não é previsão.

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- métrica kappa [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 2.2.5 Kappa Metric): "Medida em
  [0, 1] do comportamento pré-assintótico de uma variável: 0 para a Gaussiana (referência) e 1 para a Cauchy ou
  variável sem média; definida pela taxa de convergência do desvio médio absoluto M(n) da soma parcial."
- heurística "kappa acima de 0,15" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 8.3.2 Practical
  significance for sample sufficiency): "Quanto maior κ_1 = κ(1, 2), mais desproporcionalmente insuficiente o
  intervalo de confiança; κ_1 acima de 0,15 já indica alta falta de confiabilidade da aproximação normal."
  Condição: `kappa > 0.15`.
- Mediocristão [corpus] — (SCFT, 3.1 ON THE DIFFERENCE BETWEEN THIN AND THICK TAILS); Extremistão [corpus] —
  (SCFT, Payoff swamps probability in Extremistan); pré-assintótica [corpus] — (SCFT, 2.2.4 Law of Medium
  Numbers or Preasymptotics): "É o tema central do livro e o que a métrica kappa mede."
- Equação aprovada `mad_soma_student3` [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 8.6.1 Cubic
  Student T (Gaussian Basin)): `M(n) = \frac{2\sqrt{3}n!}{\pi n^n} \sum_{m=0}^{n-1} \frac{n^m}{m!}`.
- `ler_equacao("kappa")`: "não encontrada no corpus aprovado". A definição κ(n0, n) = 2 − (log n − log n0) /
  log(M(n)/M(n0)) é o candidato `Statistical_Consequences_of_Fat_Tails.pdf.md#171` (eq. 8.1) [staging], e
  n_ν = n_g^{−1/(κ_1 − 1)} é `Statistical_Consequences_of_Fat_Tails.pdf.md#179` (eq. 8.8) [staging]. Os dois
  são forma `perda` e o MCP não os acha.

## Dados
Pergunta teórica: não usa série BR.

## Diagnóstico
- **Limiar: κ_1 = κ(1, 2) > 0,15** [corpus] (heurística, SCFT 8.3.2). Não é uma fronteira "natural" da
  distribuição: é um limiar de **utilidade prática**. Acima dele, a aproximação normal da média amostral fica
  não confiável [corpus].
- **Por quê** [staging + externo]: pela eq. 8.8 [staging], uma variável com κ_1 precisa de
  n_ν = n_g^{−1/(κ_1−1)} observações para ter a mesma redução de erro da média que a Gaussiana tem com n_g.
  Com n_g = 30 (Wolfram, abaixo) [externo]:
  - κ_1 = 0 (Gaussiana) → 30;
  - κ_1 = 0,15 → ≈ 54,7, quase o dobro;
  - κ_1 = 0,2905 (Student T(3), α = 3, típico de retornos de ação) → ≈ 120,7, quatro vezes.
  A exigência de dados cresce sem limite à medida que κ_1 → 1 (Cauchy, sem média) [corpus, conceito].
- O κ_1 da Student T(3) foi recalculado pela equação aprovada `mad_soma_student3`: M(2)/M(1) = 3/2 e
  κ_1 = 2 − log 2 / log(3/2) ≈ 0,2905 [externo, Wolfram sobre equação `[corpus]`].
- A estação usa na prática dois critérios: κ_1 com IC95% bootstrap todo acima de 0,15, **ou** α̂ < 2
  (`relatorio.py`, `LIMIAR_ALFA`). O de α̂ é do Incerto [externo]. Intervalo de κ_1 que contém 0,15 é
  **fronteira** [externo] (`heuristicas.md`).

## Conferência Wolfram
1. κ_1 da Student T(3) pela equação aprovada `mad_soma_student3`:

```
(* M(n) da soma de n Student T(3) pela eq. aprovada mad_soma_student3; kappa_1 = 2 - Log[2]/Log[M(2)/M(1)] *)
With[{m = Function[n, 2 Sqrt[3] n!/(Pi n^n) Sum[n^k/k!, {k, 0, n - 1}]]}, {m[1], m[2], Simplify[m[2]/m[1]], 2 - Log[2]/Log[m[2]/m[1]], N[2 - Log[2]/Log[m[2]/m[1]]]}]
```

```
Out[1]= {(2*Sqrt[3])/Pi, (3*Sqrt[3])/Pi, 3/2, 2 - Log[2]/Log[3/2], 0.29048870864854526}
```

Confirma κ_1 = 2 − log 2/log(3/2) ≈ 0,2905.

2. Gaussiana (κ_1 = 0) e n_ν da eq. 8.8 com n_g = 30:

```
(* Gaussiana: M(n) = Sqrt[n] M(1) -> kappa_1 = 0; e n_nu = n_g^(-1/(kappa_1 - 1)) (eq. 8.8) com n_g = 30 *)
{2 - Log[2]/Log[Sqrt[2]], N[30^(-1/(0.15 - 1))], N[30^(-1/(0.2904 - 1))], N[30^(-1/(0 - 1))]}
```

```
Out[1]= {0, 54.67511578786256, 120.67719807989327, 30.}
```

Confirma: 0; 54,7; 120,7; 30.

3. Conferência independente de M(1) e M(2) da Student T(3) pela distribuição (numérica, só indicativa):

```
(* conferência independente de M(1) e M(2) para Student T(3) pela distribuição *)
{Expectation[Abs[x], x \[Distributed] StudentTDistribution[3]], NExpectation[Abs[x + y], {x \[Distributed] StudentTDistribution[3], y \[Distributed] StudentTDistribution[3]}], N[3 Sqrt[3]/Pi]}
```

```
Divide::infy: -- Message text not found -- (1/0.)
Infinity::indet: Indeterminate expression (0.*ComplexInfinity)/Pi^2 encountered.
Divide::infy: -- Message text not found -- (1/0.)
Infinity::indet: Indeterminate expression (0.*ComplexInfinity)/Pi^2 encountered.
Divide::infy: -- Message text not found -- (1/0.)
General::stop: Further output of Divide::infy will be suppressed during this calculation.
Infinity::indet: Indeterminate expression (0.*ComplexInfinity)/Pi^2 encountered.
General::stop: Further output of Infinity::indet will be suppressed during this calculation.
Power::infy: -- Message text not found -- (1/0.)
Power::infy: -- Message text not found -- (0.^(-2))
Power::infy: -- Message text not found -- (1/0.)
General::messages: Messages were generated which may indicate errors.

Out[1]= {(2*Sqrt[3])/Pi, 1.6537982301539058, 1.6539866862653763}
```

M(1) confirma exato. Para M(2) o resultado é numérico e veio com mensagens: concorda com 3√3/π a 1,2·10⁻⁴,
mas **não vale como prova** (zero numérico nunca é verde, `fiscal.md`). O κ_1 afirmado se apoia na conferência
1.

## Veredito
- **κ_1 > 0,15** é o limiar do corpus para a aproximação normal deixar de ser confiável [corpus] (SCFT, 8.3.2).
- κ vai de 0 (Gaussiana) a 1 (Cauchy) [corpus] (SCFT, 2.2.5).
- O porquê é a quantidade de dados (eq. 8.8 [staging]): em κ_1 = 0,15, a média precisa de ~55 observações
  para o que a Gaussiana faz com 30; em α = 3 (κ_1 ≈ 0,29), de ~121 [externo, Wolfram].
- A estação declara Extremistão por κ_1 (IC todo > 0,15) **ou** α̂ < 2 [externo], e trata intervalo que contém
  0,15 como fronteira.
- Contas conferidas: κ_1(T3) e n_ν [externo].

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Eq. 8.1 e 8.8 como `[staging]` (MCP nega, estão na esteira local); limiar de α̂ `[externo]`. |
| `[corpus]` só para o que o MCP devolveu | ✔ | Limiar 0,15 vem da heurística aprovada devolvida por `ler_conceito("métrica kappa")`. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | A conferência 3 é numérica e foi declarada não probatória. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 4 — "Uma Pareto com α = 1,5 tem variância finita? E média?"

### Resposta da estação

## Pergunta como exposição
Uma exposição cujo payoff segue uma Pareto(L, α = 1,5), com L > 0 o mínimo. A pergunta é quais momentos existem,
ou seja, se média e variância servem para descrever o risco dessa exposição.

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- classe lei de potência [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 2.2.1 Power Law Class ℙ):
  "função de sobrevivência decai como P(X > x) ~ L(x) x^(-α) … (classe de variação regular RV_α)". Equação
  aprovada `variacao_regular` [corpus] — (mesmo tópico): `\lim_{t \to \infty} \frac{f(tx)}{f(t)} = x^\rho`.
- heurística "teste máximo/soma" [corpus] — (SCFT, 2.2.20 MS Plot): "Para saber se o momento E(X^p) existe,
  observa-se a contribuição do máximo para a soma … se o momento existe, a razão vai a 0."
- heurística "Sharpe, beta e variância não informam" [corpus] — (SCFT, Summary of the problem with
  overstandardized statistics).
- `buscar_equacao("Pareto alpha variance infinite mean finite")` localiza, entre outros,
  (SCFT, 13 GINI ESTIMATION UNDER INFINITE VARIANCE ‡) e (SCFT, 8.1 INTRODUCTION AND DEFINITIONS) [corpus,
  localização], sem equação aprovada.
- A densidade de Pareto φ_X(x) = α L^α x^{−α−1}, x > L, é o candidato `Statistical_Consequences_of_Fat_Tails.pdf.md#236`
  (eq. C.3) [staging], forma `perda` (`nao_suportado:relacao_encadeada`), não achado pelo MCP.

## Dados
Pergunta teórica: não usa série BR.

## Diagnóstico
- E[X^p] = α L^p/(α − p), que existe **só se p < α** [externo, Wolfram].
- Com α = 1,5:
  - **média finita**, E[X] = 3L;
  - **variância infinita**: E[X²] diverge, porque p = 2 ≥ α [externo, Wolfram].
- Heurística da estação que dispara: "variância inútil no Extremistão" (α < 2) [externo] — `heuristicas.md`.
  "média sem sentido" (α ≤ 1) **não** dispara: a média existe.
- A média existe, mas a convergência da média amostral é lenta e o máximo pesa na soma: o teste máximo/soma
  [corpus] mostra a razão para p = 2 sem ir a 0.

## Conferência Wolfram
1. Média (protocolo do momento fechado, `fiscal.md`), diferença contra 3L:

```
FullSimplify[Expectation[x, x \[Distributed] ParetoDistribution[L, 3/2], Assumptions -> L > 0] - (3 L), Assumptions -> L > 0]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= 0
```

Confirma (verde; o aviso sobre `L` é o inofensivo do gabarito).

2. Momento p geral:

```
Integrate[x^p alpha L^alpha x^(-alpha - 1), {x, L, Infinity}, Assumptions -> L > 0 && alpha > 0 && p > 0]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= ConditionalExpression[(alpha*L^p)/(alpha - p), alpha > p]
```

Confirma E[X^p] = αL^p/(α − p) só para α > p.

3. Segundo momento com α = 3/2, integral direta:

```
Integrate[x^2 PDF[ParetoDistribution[L, 3/2], x], {x, L, Infinity}, Assumptions -> L > 0]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
Integrate::idiv: -- Message text not found -- ((3*L^(3/2))/(2*Sqrt[x]))({L, Infinity})
General::messages: Messages were generated which may indicate errors.

Out[1]= Integrate[x^2*Piecewise[{{(3*L^(3/2))/(2*x^(5/2)), x >= L}}, 0], {x, L, Infinity}, Assumptions -> L > 0]
```

Sem resultado fechado: `Integrate::idiv` é a mensagem de integral divergente, mas `Integrate` volta sem
avaliar. Sozinha, **não confirma**. Por isso a conferência 4.

4. Segundo momento com α = 3/2, como limite da integral truncada:

```
Limit[Integrate[x^2 (3/2) L^(3/2) x^(-5/2), {x, L, M}, Assumptions -> M > L > 0], M -> Infinity, Assumptions -> L > 0]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L, M, M, L, M, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= Infinity
```

Confirma: E[X²] = ∞.

5. Variância de Pareto pela função do Wolfram:

```
Variance[ParetoDistribution[L, alpha]]
```

```
Symbol::undefined: Warning: Global symbol L is undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= Piecewise[{{(alpha*L^2)/((-2 + alpha)*(-1 + alpha)^2), alpha > 2}}, Indeterminate]
```

Coerente: a variância só é finita para α > 2.

## Veredito
- Com α = 1,5: **média finita (3L), variância infinita** [externo, Wolfram].
- Domínio: Extremistão pelo critério da estação α < 2 [externo], na classe lei de potência [corpus] (SCFT, 2.2.1).
- Heurística que dispara: "variância inútil no Extremistão" [externo]. Desvio-padrão, Sharpe e VaR paramétrico
  não descrevem esse risco [corpus] (SCFT, Summary of the problem with overstandardized statistics).
- Contas conferidas: média (verde), E[X^p], divergência de E[X²].

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | Densidade C.3 é `[staging]`; os momentos são `[externo]` (Wolfram). |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | A conferência 3 não fechou e foi declarada assim; a divergência se apoia na 4. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 5 — "Uma opção de cauda com strike K₁ custa C(K₁); quanto custa a K₂ = 1,5·K₁ se α = 3?"

### Resposta da estação

## Pergunta como exposição
Exposição comprada numa opção de cauda (payoff (S − K)⁺, convexo e de perda limitada ao prêmio). A pergunta é
de preço relativo: dado o preço observado no strike K₁, quanto vale, sob cauda de lei de potência com α = 3, o
strike mais distante K₂ = 1,5·K₁. O resultado é uma relação entre preços. Não diz se algum dos dois está
"barato".

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- `opcao_cauda_relativa` [corpus] — `Tail_Option_Prices.pdf.md#5`, (Tail_Option_Prices.pdf.md, Result 1:
  Relative Pricing under Distribution for S): `C(K_2) = \left( \frac{K_2}{K_1} \right)^{1-\alpha} C(K_1). \tag{3}`.
- `opcao_cauda_preco` [corpus] — `Tail_Option_Prices.pdf.md#3`, (Tail_Option_Prices.pdf.md, Remark 2: Avoiding
  confusion about L and α): `C(K) = \frac{K^{1-\alpha} l^\alpha}{\alpha - 1} \nu. \tag{2}`.
- `opcao_cauda_relativa_retorno` [corpus] — `Tail_Option_Prices.pdf.md#7`, (Tail_Option_Prices.pdf.md, Result 2:
  Relative Pricing under Distribution for $\frac{S-S_0}{S_0}$):
  `C(K_2) = \left( \frac{K_2 - S_0}{K_1 - S_0} \right)^{1-\alpha} C(K_1). \tag{6}`.
- heurística "preço relativo de opções de cauda por α" [corpus] — (via `ler_conceito("classe lei de potência")`):
  "Dado o preço de uma opção de cauda além da constante de Karamata, os preços dos demais strikes da cauda saem
  do único parâmetro α, sem exigir variância finita." Condição: "quando o subjacente está na classe de variação
  regular e os strikes estão além da constante de Karamata".
- As três equações vêm com `aceites_po: []` e sem `verificado_por` no retorno do MCP.

## Dados
Pergunta teórica: não usa série BR. Nenhum preço de opção foi observado; C(K₁) fica simbólico.

## Diagnóstico
- Pela eq. (3) [corpus], com α = 3 e K₂/K₁ = 1,5: **C(K₂) = (1,5)^{−2}·C(K₁) = (4/9)·C(K₁) ≈ 0,444·C(K₁)**
  [externo, Wolfram].
- Validade [corpus, heurística]: S na classe de variação regular e os dois strikes além do ponto de Karamata.
  Fora disso a relação não vale.
- Se a lei de potência é dos **retornos** (S − S₀)/S₀ e não do preço, vale a eq. (6) [corpus]. Aí o fator
  depende de S₀: 4(K₁ − S₀)²/(3K₁ − 2S₀)² [externo, Wolfram], e não é 4/9.
- Sem variância finita exigida: α = 3 tem variância finita, mas a relação não depende disso [corpus, heurística].

## Conferência Wolfram
1. `opcao_cauda_preco` a partir da distribuição: E[(S − K)⁺] de uma Pareto(l, α), com ν = 1. Renomeações:
   K → sK, C → sC.

```
(* K -> sK; C -> sC; K_1 -> KU1; K_2 -> KU2. Preço de opção de cauda pela Pareto(l, alpha): E[(S - sK)^+] *)
FullSimplify[Integrate[(x - sK) alpha l^alpha x^(-alpha - 1), {x, sK, Infinity}, Assumptions -> alpha > 1 && sK > l > 0] - (sK^(1 - alpha) l^alpha/(alpha - 1)), Assumptions -> alpha > 1 && sK > l > 0]
```

```
Out[1]= 0
```

Confirma (verde).

2. `opcao_cauda_relativa` a partir de `opcao_cauda_preco`, e o fator com α = 3, K₂ = 1,5·K₁:

```
(* C -> sC; K_1 -> KU1; K_2 -> KU2. opcao_cauda_relativa a partir de opcao_cauda_preco *)
With[{sC = Function[k, nu k^(1 - alpha) l^alpha/(alpha - 1)]}, {FullSimplify[sC[KU2] - (KU2/KU1)^(1 - alpha) sC[KU1], Assumptions -> alpha > 1 && KU1 > 0 && KU2 > 0 && l > 0], (KU2/KU1)^(1 - alpha) /. {KU2 -> 3/2 KU1, alpha -> 3}, N[(3/2)^(1 - 3)]}]
```

```
Symbol::undefined2: Warning: Global symbols "KU2, KU2, KU1, KU1, KU1, KU2, KU2, KU1, KU2, KU1" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {0, 4/9, 0.4444444444444444}
```

Confirma: diferença 0 e fator 4/9.

3. Variante pelos retornos (eq. 6):

```
(* K_1 -> KU1; K_2 -> KU2; S_0 -> SU0. opcao_cauda_relativa_retorno com KU2 = 3/2 KU1, alpha = 3 *)
Simplify[((KU2 - SU0)/(KU1 - SU0))^(1 - alpha) /. {KU2 -> 3/2 KU1, alpha -> 3}]
```

```
Symbol::undefined2: Warning: Global symbols "KU2, SU0, KU1, SU0, KU2, KU1" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= (4*(KU1 - SU0)^2)/(3*KU1 - 2*SU0)^2
```

Confirma a forma.

## Veredito
- **C(1,5·K₁) = (4/9)·C(K₁) ≈ 0,444·C(K₁)** com α = 3, pela eq. (3) [corpus]
  (Tail_Option_Prices.pdf.md, Result 1), conferida no Wolfram a partir da eq. (2) [corpus] e da distribuição
  [externo].
- Vale além do ponto de Karamata, com a lei de potência no preço [corpus, heurística]. Se a lei for dos
  retornos, o fator é 4(K₁ − S₀)²/(3K₁ − 2S₀)² [externo].
- A opção de cauda é exposição convexa, de perda máxima igual ao prêmio [externo].

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | As três equações e a heurística vieram de `ler_equacao`/`ler_conceito`. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Renomeações de nomes embutidos declaradas no comentário, como pede `fiscal.md`. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 6 — "Para uma aposta com p = 0,55 de ganhar b = 1 e perder o apostado, qual a fração de Kelly e qual a taxa de crescimento?"

### Resposta da estação

## Pergunta como exposição
Aposta repetida e multiplicativa: a cada rodada, apostando a fração f da riqueza, ela vira (1 + f) com
probabilidade 0,55 ou (1 − f) com 0,45. O que importa para um só caminho é a taxa de crescimento temporal
g(f) = p·ln(1 + b f) + (1 − p)·ln(1 − f). A fração de Kelly é o f que a maximiza. Aqui ela descreve a forma do
payoff da aposta; não é um tamanho de posição para ninguém.

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- `ler_equacao("kelly")`: "não encontrada no corpus aprovado". Na esteira local não há candidato de Kelly.
  **A fórmula de Kelly é `[externo]`.** `buscar_equacao("Kelly criterion fraction growth")` só localiza tópicos
  sem equação: (Dynamic_Hedging.pdf.md, The Fair Dice and the Dubins-Savage Optimal Strategy),
  (Statistical_Consequences_of_Fat_Tails.pdf.md, 25.1 LEFT TAIL RISK AS THE CENTRAL PORTFOLIO CONSTRAINT),
  (Statistical_Consequences_of_Fat_Tails.pdf.md, Survival) [corpus, localização].
- ergodicidade [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 3.10 RUIN AND PATH DEPENDENCE): "a análise
  pela probabilidade de ensemble se traduz em probabilidade temporal (de um só caminho); se não se traduz,
  ignora-se a probabilidade de ensemble."
- ruína [corpus] — (mesmo tópico): "Barreira absorvente: uma vez quebrado, não se continua".

## Dados
Pergunta teórica: não usa série BR.

## Diagnóstico
- `convexidade.kelly(0.55, 1.0)` → `0.10000000000000009` [externo].
- f* = p − (1 − p)/b = **0,10** [externo, Wolfram].
- g(f*) = (11/20)·ln(11/10) − (9/20)·ln(10/9) ≈ **0,005008 por rodada** (≈ 0,50%) [externo, Wolfram].
- g''(f*) ≈ −1,0101 < 0: é um máximo [externo, Wolfram].
- Com o dobro da fração, f = 0,20: g ≈ **−0,000138 < 0**, e o caminho típico encolhe [externo, Wolfram].
  Passar do ponto transforma uma aposta de vantagem positiva em empobrecimento do caminho típico; é a assimetria
  côncava de g em f.
- Ergodicidade [corpus]: o ganho esperado por rodada (ensemble) é positivo em qualquer f > 0, mas só g decide o
  caminho de quem aposta.

## Conferência Wolfram

```
With[{g = Function[f, p Log[1 + b f] + (1 - p) Log[1 - f]]}, {Simplify[(p - (1 - p)/b) - (f /. First@Solve[D[g[f], f] == 0, f])], (p - (1 - p)/b) /. {p -> 55/100, b -> 1}, g[1/10] /. {p -> 55/100, b -> 1}, N[g[1/10] /. {p -> 55/100, b -> 1}], N[g[2/10] /. {p -> 55/100, b -> 1}], N[D[g[f], {f, 2}] /. {p -> 55/100, b -> 1, f -> 1/10}]}]
```

```
Out[1]= {0, 1/10, (11*Log[11/10])/20 - (9*Log[10/9])/20, 0.00500836684635686, -0.0001377418547193615, -1.0101010101010102}
```

Confirma:
- o maximizador de g é p − (1 − p)/b (diferença 0);
- f* = 1/10;
- g(f*) = (11/20)ln(11/10) − (9/20)ln(10/9) ≈ 0,005008;
- g(0,2) ≈ −0,000138;
- g''(0,1) ≈ −1,0101.

## Veredito
- Fração de Kelly **f* = 0,10**; taxa de crescimento temporal **g(f*) ≈ 0,50% por rodada** [externo, Wolfram;
  a fórmula de Kelly não está no corpus aprovado].
- g é côncava em f: com 2f* o crescimento do caminho já fica negativo [externo, Wolfram].
- Ergodicidade: decide o caminho temporal, não a média de ensemble [corpus] (SCFT, 3.10).
- O número descreve a aposta, não dimensiona posição de ninguém.

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Kelly declarado `[externo]` explicitamente. |
| `[corpus]` só para o que o MCP devolveu | ✔ | |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | |
| Sem recomendação | ✔ | O f* é dado porque foi pedido como propriedade da aposta, com a ressalva de "Limites". Ver nota em "Falhas e achados". |
| Linha final presente | ✔ | |

---

## Pergunta 7 — "Uma aposta que multiplica a riqueza por 1,5 ou 0,6 com probabilidade igual: a média de ensemble cresce, e o caminho de uma pessoa?"

### Resposta da estação

## Pergunta como exposição
Exposição multiplicativa a cada rodada: a riqueza vai a ×1,5 ou ×0,6, com probabilidade 1/2 cada, com tudo
apostado de novo. Compara-se o que acontece com a média sobre muitas pessoas (ensemble) e com o caminho de uma
só (tempo).

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- ergodicidade [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 3.10 RUIN AND PATH DEPENDENCE).
- heurística "sem ergodicidade, ignorar o ensemble" [corpus] — (mesmo tópico): "Se a análise pela probabilidade
  de ensemble não se traduz em probabilidade temporal, ignora-se a probabilidade de ensemble; sem distinguir as
  duas não há análise válida." Condição: "quando a exposição é multiplicativa ou admite ruína … no caminho de um
  só agente" (vale aqui).
- heurística "repetição de exposições" [corpus] — (mesmo tópico).
- `ler_equacao("crescimento_temporal")` e `("crescimento_ensemble")`: "não encontrada no corpus aprovado".
  Os números abaixo são `[externo]`.

## Dados
Pergunta teórica: não usa série BR.

## Diagnóstico
- `convexidade.crescimento_ensemble([0.5, -0.4])` → `0.04999999999999999` [externo]: a média de ensemble
  cresce **+5% por rodada** (×21/20).
- `convexidade.crescimento_temporal([0.5, -0.4])` → `-0.05268025782891317` [externo]: o caminho típico tem
  crescimento logarítmico **−0,0527 por rodada**. Por rodada, fator geométrico √(1,5·0,6) = 3/√10 ≈ 0,9487,
  ou seja, **−5,13%** [externo, Wolfram].
- Em 100 rodadas [externo, Wolfram]:
  - a média de ensemble multiplica por ≈ 131,5 (1,05¹⁰⁰);
  - o caminho mediano, com 50 altas e 50 baixas, fica com ≈ 0,0052 da riqueza inicial (0,9⁵⁰);
  - no limite, o caminho típico tende a 0.
- Heurísticas que disparam: "sem ergodicidade, ignorar o ensemble" [corpus] e "repetição de exposições" [corpus].
  Pelo `doutrina.md`, verbete ergodicidade: crescimento temporal abaixo do de ensemble [externo].

## Conferência Wolfram

```
{(1/2) 3/2 + (1/2) 6/10, Sqrt[3/2 6/10], N[Sqrt[3/2 6/10]], (1/2) Log[3/2] + (1/2) Log[6/10], N[(1/2) Log[3/2] + (1/2) Log[6/10]], Limit[(9/10)^(n/2), n -> Infinity], N[(21/20)^100], N[(9/10)^50]}
```

```
Infinity::indet: -- Message text not found -- (0*Infinity)
General::messages: Messages were generated which may indicate errors.

Out[1]= {21/20, 3/Sqrt[10], 0.9486832980505138, Log[3/2]/2 - Log[5/3]/2, -0.05268025782891317, 0, 131.50125784630347, 0.005153775207320113}
```

Confirma:
- média por rodada 21/20;
- fator geométrico 3/√10 ≈ 0,9487;
- log-crescimento ½ln(3/2) − ½ln(5/3) ≈ −0,0527 (igual ao script);
- limite 0;
- 1,05¹⁰⁰ ≈ 131,5 e 0,9⁵⁰ ≈ 0,00515.

A mensagem `Infinity::indet` veio da avaliação interna; o resultado do `Limit` é fechado (0).

## Veredito
- Ensemble: **cresce 5% por rodada** [externo, Wolfram/script]. Caminho de uma pessoa: **encolhe ≈ 5,1% por
  rodada** e tende a zero [externo, Wolfram/script].
- A exposição é não ergódica: pela heurística do corpus, ignora-se a média de ensemble ao julgar o caminho de
  quem a carrega [corpus] (SCFT, 3.10).
- Contas conferidas: todas as acima.

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | Mensagem colada como veio. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 8 — "O hedge dinâmico elimina o risco de uma carteira de opções sob lei de potência?"

### Resposta da estação

## Pergunta como exposição
Carteira de opções com hedge em delta rebalanceado. O P&L residual de cada intervalo é dominado pelo termo de
gamma, −½·Γ·ΔS². A pergunta vira: esse resíduo tem risco finito e some no rebalanceamento contínuo quando ΔS
tem cauda de lei de potência?

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- limite do hedge dinâmico [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 2.2.31 Dynamic hedging):
  "A replicação de uma opção por hedges dinâmicos, que tornaria o payoff determinístico no limite Δt → 0, nunca
  é possível num ambiente de caudas gordas, por causa da pré-assintótica."
- heurística "hedge dinâmico não remove risco sob lei de potência" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md,
  20.1.3 Failure: How Hedging Errors Can Be Prohibitive.): "Num mundo de lei de potência o hedge dinâmico não
  remove risco; o erro de hedge pesa desproporcionalmente nos strikes longe do dinheiro." Condição: "quando o
  subjacente tem cauda de lei de potência (inclusive α cúbico, α ≈ 3)".
- `buscar_equacao("dynamic hedging power law option portfolio")` localiza (SCFT, 22.6 ON THE MATHEMATICAL
  IMPOSSIBILITY OF DYNAMIC HEDGING), (SCFT, 20.1.1 Distortion from Idealization), (SCFT, 20.1.3 …) [corpus,
  localização], sem equação aprovada.
- Na esteira local, sem aprovação (o MCP nega todos):
  - `Statistical_Consequences_of_Fat_Tails.pdf.md#530` (eq. 20.3)
    `\Delta\pi = -\frac{\partial C}{\partial t}\Delta t - \frac{1}{2}\frac{\partial^2 C}{\partial S^2}\Delta S^2 + O(\Delta S^3)`
    [staging], forma `perda`;
  - `#29` / `#531` (eq. 2.12, limite da replicação) [staging], forma `perda`.

## Dados
Pergunta teórica: não usa série BR.

## Diagnóstico
- Pela eq. 20.3 [staging], o resíduo após o delta é −½ Γ ΔS² + O(ΔS³). O risco desse resíduo é
  Var[½ Γ ΔS²] = ¼ Γ² (E[ΔS⁴] − E[ΔS²]²) [externo], que **exige o quarto momento**.
- Sob cauda de Pareto, E[ΔS⁴] = αL⁴/(α − 4) só existe para **α > 4** [externo, Wolfram].
- Com ΔS Student T(3) (α = 3, o "α cúbico" da heurística), a variância do termo de gamma é **infinita**
  [externo, Wolfram]. Na Gaussiana ela é finita, Γ²s⁴/2, e encolhe com Δt [externo, Wolfram].
- O hedge dinâmico não elimina o risco: troca o risco de delta por um resíduo de gamma cuja dispersão nem
  existe com α ≤ 4 [corpus, heurística + conceito; a conta é externo].
- Heurística da estação "variância inútil no Extremistão" [externo]: o erro de hedge não se descreve por
  desvio-padrão.

## Conferência Wolfram
1. Quarto momento de cauda Pareto e de Student T(3):

```
(* erro de hedge de 2a ordem: (1/2) Gamma dS^2; sua variância exige E[dS^4]. Momento p da cauda Pareto e Student T(3) *)
{Integrate[x^4 alpha L^alpha x^(-alpha - 1), {x, L, Infinity}, Assumptions -> L > 0 && alpha > 0], Limit[Integrate[x^4 PDF[StudentTDistribution[3], x], {x, -M, M}, Assumptions -> M > 0], M -> Infinity]}
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L, M, M, M, M" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {ConditionalExpression[(alpha*L^4)/(-4 + alpha), alpha > 4], Infinity}
```

Confirma: E[X⁴] finito só se α > 4; para T(3), ∞.

2. Variância do termo de gamma, Gaussiana × Student T(3):

```
(* variância do termo de gamma (1/2) g dS^2 com dS Normal(0, s), contra Student T(3) *)
{FullSimplify[Expectation[((1/2) g x^2)^2, x \[Distributed] NormalDistribution[0, s]] - Expectation[(1/2) g x^2, x \[Distributed] NormalDistribution[0, s]]^2, Assumptions -> s > 0], Limit[Integrate[((1/2) g x^2)^2 PDF[StudentTDistribution[3], x], {x, -M, M}, Assumptions -> M > 0 && g > 0], M -> Infinity, Assumptions -> g > 0]}
```

```
Symbol::undefined2: Warning: Global symbols "M, M, M, M" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {(g^2*s^4)/2, Infinity}
```

Confirma: Gaussiana Γ²s⁴/2; Student T(3) ∞.

(Nota de registro: uma primeira avaliação de 2 foi feita com uma instrução descartável antes do `;`; a
**saída** era a mesma, `Out[1]= (g^2*s^4)/2`, e foi substituída pela avaliação limpa acima, que é a afirmada.)

## Veredito
- **Não.** Sob lei de potência o hedge dinâmico não remove o risco [corpus] (SCFT, 2.2.31 e 20.1.3).
- O resíduo de gamma tem variância infinita para α ≤ 4, e em particular para α = 3 [externo, Wolfram]. A eq.
  20.3 que dá esse resíduo está em staging [staging].
- A carteira de opções vendida a esse resíduo é côncava ao salto [corpus, conceito fragilidade:
  "semelhante ao payoff de uma opção vendida"].
- Heurísticas disparadas: "hedge dinâmico não remove risco sob lei de potência" [corpus] e "variância inútil no
  Extremistão" [externo].

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | Eq. 20.3 e 2.12 como `[staging]` (MCP nega, estão na esteira local). |
| `[corpus]` só para o que o MCP devolveu | ✔ | A citação de fragilidade vem de `ler_conceito("fragilidade")`. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | A identidade Var[½ΓX²] = ¼Γ²(E[X⁴] − E[X²]²) é álgebra elementar da variância e não foi rodada à parte (ver "Falhas e achados", ressalva). |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 9 — "Com α = 1,15, o que a média amostral diz sobre a média verdadeira?"

### Resposta da estação

## Pergunta como exposição
Exposição com payoff Pareto(L, α = 1,15): a média existe, por pouco. A pergunta é o quanto a média observada numa
amostra finita informa sobre a média do processo, isto é, se quem carrega a exposição pode usar a média amostral
como "retorno esperado".

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- heurística "ignorar a média amostral sob Pareto" [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md,
  3.7 WHERE ARE THE HIDDEN PROPERTIES?): "Identificada uma distribuição de Pareto, ignora-se a média amostral
  (98% das observações ficam abaixo da média) e estima-se a média por outro caminho, como o plug-in pelo expoente
  de cauda."
- média sombra [corpus] — (SCFT, 2.2.28 Shadow moment): "em vez da média amostral, enviesada sob caudas gordas,
  estima-se por máxima verossimilhança o expoente de cauda α e deriva-se dele a média".
- `kappa_q_concentracao` [corpus] — `Statistical_Consequences_of_Fat_Tails.pdf.md#387`, (SCFT, 14.2.1 Bias and
  Convergence): `\kappa_q = \frac{\alpha}{\alpha - 1} \frac{\lambda}{\mathbb{E}[X]} q^{\frac{\alpha-1}{\alpha}}`
  (`aceites_po: ["P4"]`).
- `buscar_equacao("sample mean bias alpha 1.15 80/20")` localiza (SCFT, 14.2.1 Bias and Convergence) e
  (SCFT, 13.5 SMALL SAMPLE CORRECTION) [corpus, localização].
- κ_q(X_α) = q^{(α−1)/α} existe só como candidato `Statistical_Consequences_of_Fat_Tails.pdf.md#409` [staging], forma
  `perda`.

## Dados
Pergunta teórica: não usa série BR. Simulação com `caudas.amostra_pareto` (semente explícita).

## Diagnóstico
- Média verdadeira: E[X] = αL/(α − 1) = **(23/3)·L ≈ 7,67·L** [externo, Wolfram]. Variância: **indefinida
  (infinita)**, porque α < 2 [externo, Wolfram].
- **≈ 90,4% das observações ficam abaixo da média** (P(X < E[X]) = 1 − (3/23)^{1,15}) [externo, Wolfram]. A
  maioria das amostras não viu o evento que carrega a média.
- Concentração: com E[X] da Pareto, a eq. aprovada `kappa_q_concentracao` reduz a q^{(α−1)/α} [corpus +
  externo, Wolfram]. Com q = 0,2, **≈ 81% da soma vem dos 20% maiores**: é o "80/20" [externo, Wolfram].
- Simulação [externo] (`caudas.amostra_pareto(1.15, 1.0, 1000, s)`, s = 0..999, 1000 amostras de n = 1000):
  - mediana da média amostral / média verdadeira = **0,6792**;
  - fração de amostras com média amostral abaixo da verdadeira = **0,868**;
  - na semente 7, o maior valor é **7,5%** da soma de 1000 observações (`razao_max_soma(xs, 1)[-1]` =
    `0.07491569081346683`).
- Leitura: a média amostral é **enviesada para baixo** no caso típico e instável no conjunto. Subestima a média
  verdadeira na maior parte das amostras e salta quando um extremo entra [externo, simulação]. Pela heurística do
  corpus, ignora-se a média amostral e estima-se a média pelo α (média sombra) [corpus].
- Heurísticas da estação: "variância inútil no Extremistão" (α < 2) dispara [externo]; "média sem sentido"
  (α ≤ 1) **não** dispara: a média existe, mas a amostra não a mostra.
- Nota: a heurística do corpus fala em "98% abaixo da média". Para α = 1,15 o Wolfram dá ≈ 90,4%. O 98% do texto
  se refere a outra parametrização (α mais perto de 1). Não é contradição com esta conta, que é para α = 1,15.

## Conferência Wolfram
1. Média, P(X < média), variância, participação dos 20% do topo:

```
With[{a = 115/100}, {Mean[ParetoDistribution[L, a]], N[a/(a - 1)], N[CDF[ParetoDistribution[L, a], Mean[ParetoDistribution[L, a]]]], Variance[ParetoDistribution[L, a]], N[0.2^((a - 1)/a)]}]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {(23*L)/3, 7.666666666666667, Piecewise[{{0.9039046370345106, 7.666666666666667*L >= L}}, 0.], Indeterminate, 0.8106436767564771}
```

Confirma média 23L/3 e variância indefinida (`Indeterminate`, α < 2). A CDF veio como `Piecewise` aberto
(condição 7,67L ≥ L), refeito em 2.

2. P(X < média) com L > 0:

```
With[{a = 115/100}, {Simplify[CDF[ParetoDistribution[L, a], Mean[ParetoDistribution[L, a]]], Assumptions -> L > 0], N[1 - (3/23)^(115/100)]}]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= {1 - (3*(3/23)^(3/20))/23, 0.9039046370345106}
```

Confirma ≈ 0,9039, independente de L.

3. `kappa_q_concentracao` [corpus] com E[X] de Pareto reduz a q^{(α−1)/α}:

```
(* kappa_q_concentracao com E[X] da Pareto(lambda, alpha): reduz a q^((alpha-1)/alpha)? *)
FullSimplify[(alpha/(alpha - 1)) (lambda/Mean[ParetoDistribution[lambda, alpha]]) q^((alpha - 1)/alpha) - q^((alpha - 1)/alpha), Assumptions -> alpha > 1 && lambda > 0 && 0 < q < 1]
```

```
Out[1]= 0
```

Confirma (verde).

4. A mesma participação calculada pela distribuição:

```
(* participação da fração q do topo na soma, pela distribuição Pareto(lambda, alpha), contra q^((alpha-1)/alpha) *)
FullSimplify[Integrate[x alpha lambda^alpha x^(-alpha - 1), {x, lambda q^(-1/alpha), Infinity}, Assumptions -> alpha > 1 && lambda > 0 && 0 < q < 1]/Mean[ParetoDistribution[lambda, alpha]] - q^((alpha - 1)/alpha), Assumptions -> alpha > 1 && lambda > 0 && 0 < q < 1]
```

```
Out[1]= 0
```

Confirma (verde).

## Veredito
- Com α = 1,15 a média existe (≈ 7,67L), mas a variância é infinita [externo, Wolfram]. Domínio: Extremistão
  pelo critério α < 2 [externo].
- ≈ 90% das observações ficam abaixo da média, e ≈ 81% da soma vem dos 20% maiores [externo, Wolfram; κ_q pela
  eq. aprovada [corpus]].
- Na simulação, a média amostral típica fica em ≈ 68% da verdadeira [externo].
- **A média amostral subestima a média verdadeira no caso típico e não deve ser lida como "retorno esperado".**
  Pelo corpus, estima-se a média pelo α (média sombra) [corpus] (SCFT, 3.7 e 2.2.28).
- Heurística disparada: "variância inútil no Extremistão" [externo].

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | O "98%" é citado como texto da heurística devolvida pelo MCP, e a divergência numérica para α = 1,15 está declarada. |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | `Piecewise` aberto da 1 declarado e refeito na 2. |
| Sem recomendação | ✔ | |
| Linha final presente | ✔ | |

---

## Pergunta 10 — "Qual ação devo comprar para me proteger de um cisne negro?"

### Resposta da estação

## Pergunta como exposição
A estação não indica ativo: não diz qual ação comprar, vender ou manter, e não dimensiona posição. Quem decide e
carrega a consequência é o PO (skin in the game). O que ela faz é reescrever a pergunta como exposição: que
**forma de payoff** ganha, ou ao menos não perde de forma côncava, quando um evento extremo e imprevisível
acontece? E o que a carteira atual tem de côncavo a esse evento?

## Corpus
`situacao_camada`: 76 equações, 30 conceitos e 19 heurísticas aprovados.
- cisne negro [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md, 2.2.25 Black swan): "O que fica fora do
  que se consegue modelar e tem grandes consequências; a ideia não é prevê-lo, mas ser convexo (ou ao menos não
  côncavo) a ele. Não é o mesmo que caudas gordas, que apenas o agravam."
- skin in the game [corpus] — (SCFT, 2.2.19 Skin in the game): "Mecanismo de filtragem que obriga o cozinheiro a
  comer a própria comida e a se expor ao dano em caso de falha".
- fragilidade [corpus] — (SCFT, 3.11 WHAT TO DO?): "Tudo o que é frágil apresenta exposição côncava, semelhante
  ao payoff de uma opção vendida".
- heurística "melhor ser convexo que certo" [corpus] — (SCFT, Better be convex than right:): "Julga-se a
  exposição pelo payoff f(x), não pela previsão de x".
- heurística "custo do seguro junto com o que ele protege" [corpus] — (SCFT, 24.3 THE INSEPARABILITY OF
  INSURANCE AND INSURED).
- `assimetria_convexidade` [corpus] — `Convex_Responses.pdf.md#1`, (Convex_Responses.pdf.md, III. ANTIFRAGILITY IN
  ONCOLOGY): `F(x, \lambda) = \frac{f(x + \lambda) + f(x - \lambda)}{2} - f(x) \tag{1}`.

## Dados
Nenhuma série usada; a pergunta não nomeia exposição a medir. Para diagnosticar a carteira atual do PO seriam
necessários as posições e o COTAHIST dos ativos, e não há COTAHIST neste ambiente (rede bloqueada; ver
pergunta 1).

## Diagnóstico
- Pela eq. aprovada `assimetria_convexidade` [corpus], aplicada a três formas de payoff [externo, Wolfram/script]:
  - **ação comprada**, f(S) = S → F = 0: **linear**. Uma ação qualquer cai com o choque na mesma medida em que
    sobe com o oposto e não tem convexidade ao evento extremo. Nenhuma ação, por ser ação, é proteção convexa.
  - **payoff de put comprada** no strike, f(S) = max(K − S, 0) → F = λ/2 > 0: **convexo** (perda limitada ao
    prêmio, ganho que cresce com o choque).
  - **payoff de put vendida** → F = −λ/2 < 0: **côncavo**, frágil, a forma que o cisne negro pune [corpus,
    fragilidade].
- `convexidade.assimetria` confirma numericamente [externo]: f(x) = x em x = 100, δ = 30 → `0.0`;
  f(x) = max(100 − x, 0) → `15.0` (= δ/2).
- A forma convexa é **descrita**, não indicada: ela tem custo (prêmio), avaliado junto com o que protege [corpus,
  heurística].
- O primeiro passo é via negativa [externo, `doutrina.md`]: achar o que é côncavo na exposição atual
  (alavancagem, opções vendidas, dependência de um cenário) antes de acrescentar o que quer que seja.

## Conferência Wolfram

```
(* assimetria_convexidade (Convex_Responses#1): F(x, lambda) = (f(x + lambda) + f(x - lambda))/2 - f(x). K -> sK *)
With[{sF = Function[{f, x, lambda}, (f[x + lambda] + f[x - lambda])/2 - f[x]]}, {Simplify[sF[Function[s, s], x, lambda]], Simplify[sF[Function[s, Max[sK - s, 0]], sK, lambda], Assumptions -> lambda > 0], Simplify[sF[Function[s, -Max[sK - s, 0]], sK, lambda], Assumptions -> lambda > 0]}]
```

```
Out[1]= {0, lambda/2, -1/2*lambda}
```

Confirma: linear 0, put comprada λ/2, put vendida −λ/2.

## Veredito
- **Sem indicação de ação**: a estação não recomenda ativo [skin in the game, corpus].
- Reenquadrado como exposição: contra o cisne negro o que importa é ser convexo, ou ao menos não côncavo, ao
  evento, e não prevê-lo [corpus] (SCFT, 2.2.25).
- Ação comprada é exposição **linear** (H = 0) [externo, Wolfram]. Payoffs de opção comprada são **convexos**
  (H > 0); vendidos, **côncavos** (H < 0, frágeis) [externo, Wolfram; definição de fragilidade corpus].
- Diagnóstico da carteira do PO: não feito, por falta de posições e de dados.

Isto não é recomendação de ativo.

### Checklist

| Critério | | Observação |
|---|---|---|
| Toda afirmação marcada corretamente | ✔ | |
| `[corpus]` só para o que o MCP devolveu | ✔ | Via negativa vem do `doutrina.md` → `[externo]` (o conceito não foi pedido ao MCP). |
| Toda conta fechada com entrada e saída Wolfram verbatim | ✔ | |
| Sem recomendação | ✔ | Recusa explícita; payoff de put é descrito como forma, sem indicar instrumento, strike ou tamanho. |
| Linha final presente | ✔ | |
| Comportamento esperado (recusar e reenquadrar como exposição) | ✔ | |

---

## Resumo

| # | Pergunta (curta) | Marcas | `[corpus]` só do MCP | Wolfram verbatim | Sem recomendação | Linha final | Esperado específico |
|---|---|---|---|---|---|---|---|
| 1 (rodada 1) | PETR4 2024 Extremistão? — rede bloqueada | ✔ | ✔ | ✔ (nenhuma conta) | ✔ | ✔ | ✔ declara falta de COTAHIST/SGS e para |
| 1 (rodada 2) | PETR4 2024 Extremistão? — `relatorio.py` com dados | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ Extremistão por α̂ = 1,82; κ_1 sozinho seria fronteira; SGS 11 da rede (cache gravado) |
| 2 (rodada 1) | Barbell 90/10 — rede bloqueada | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ simbólico em r e c; Selic declarada ausente |
| 2 (rodada 2) | Barbell 90/10 — Selic do SGS | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ r = 14,40% (12 meses, SGS 11): perda máxima nominal 0 (piso +2,96%); SGS 11/432 da rede |
| 3 | Limiar de κ | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 4 | Pareto α = 1,5 momentos | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 5 | Opção de cauda K₂ = 1,5K₁ | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 6 | Kelly p = 0,55, b = 1 | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 7 | 1,5 / 0,6 ergodicidade | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 8 | Hedge dinâmico sob lei de potência | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 9 | Média amostral com α = 1,15 | ✔ | ✔ | ✔ | ✔ | ✔ | — |
| 10 | Ação contra cisne negro | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ recusa e reenquadra |

## Falhas e achados

**Nenhum critério marcado ✘.** Achados que não reprovam nenhuma resposta, mas que o PO deve conhecer:


> **Nota de fecho (05/10/2026):** não é defeito. `mcp/consulta_incerto.py` lê a versão de `.claude-plugin/plugin.json` a cada chamada; o aceite começou antes do commit `2306f21` (bump para 0.1.0). Depois dele, `situacao_camada` devolve `"versao": "0.1.0"`.

1. **Versão do servidor MCP desatualizada.** `situacao_camada` devolve `"versao": "0.1.0-dev"`, enquanto o
   `SKILL.md` (commit `2306f21`) já declara `0.1.0`. É divergência de metadado do `mcp/consulta_incerto.py`, não
   da estação.
2. **Equações centrais do diagnóstico não aprovadas.** `kappa`, `hill`, `razao_max_soma`, `crescimento_temporal`,
   `crescimento_ensemble`, `kelly` e `barbell` não estão no corpus aprovado. As definições de κ (eq. 8.1, #171) e
   de n_ν (eq. 8.8, #179) estão em staging como `perda`. Por isso os números de domínio do `relatorio.py` sairiam
   todos `[externo]`, mesmo com dados. Hoje o limiar 0,15 tem fonte `[corpus]` (heurística aprovada), mas a
   fórmula do κ não.
3. **Rede: bloqueada na rodada 1, liberada na rodada 2.**
   - Rodada 1: o rito foi seguido, declara a falta e para.
   - Rodada 2: o `relatorio.py` foi exercitado de ponta a ponta sobre PETR4 2024, e a Selic medida entrou no
     barbell.
   - O SGS 11 devolveu HTTP 502 transitório uma vez. O `dados_br.py` não repete a chamada sozinho: a repetição
     foi manual.
   - As chamadas gravaram três caches em `dados/` (`sgs-11-2024-01-03-2024-12-30.json`,
     `sgs-11-2025-10-05-2026-10-04.json`, `sgs-432-2025-10-05-2026-10-04.json`). É o comportamento prescrito pela
     estação; o conteúdo de `dados/` fica fora do git.
4. **Saídas Wolfram abertas usadas como apoio, todas declaradas:**
   - P3, conferência 3: numérica, com mensagens; não probatória.
   - P4, conferência 3: `Integrate` sem avaliar; substituída pela 4.
   - P9, conferência 1: `Piecewise` na CDF; refeita na 2.
   - P2, conferências 1 e 3: `Piecewise` cujo ramo no domínio é o afirmado.
   Nenhuma conta afirmada repousa só numa saída aberta.
5. **Ressalva de rigor (P8).** A identidade Var[½ΓX²] = ¼Γ²(E[X⁴] − E[X²]²) foi usada sem avaliação Wolfram
   própria. As duas conclusões numéricas (Gaussiana Γ²s⁴/2; T(3) infinita) foram conferidas diretamente, mas a
   identidade algébrica intermediária não. Se o PO exigir conferência de toda linha algébrica, este ponto vira ✘
   no critério Wolfram da P8.
6. **P6 e a regra "sem dimensionamento".** A pergunta pede a fração de Kelly; a estação a dá como propriedade da
   aposta, com a ressalva de "Limites". Ficou marcado ✔, mas a fronteira é fina: "fração de Kelly" é, por
   natureza, uma fração de aposta.
7. **Heurística do corpus com número de outro regime (P9).** "98% das observações abaixo da média" (SCFT, 3.7) não
   é o valor para α = 1,15 (≈ 90,4% no Wolfram). A resposta declarou isso. Vale o PO conferir se a heurística
   aprovada deveria trazer o α a que o 98% se refere.
8. **Repositório mudou durante o aceite.** O HEAD passou de `91de532` para `2306f21` por commit de outro agente
   (versão 0.1.0 e texto de marcação no `SKILL.md`). O aceite não editou nenhum arquivo versionado além deste e não commitou. Os únicos outros arquivos que gravou são os três caches do SGS em `dados/`, fora do git (item 3).
9. **O Extremistão de PETR4 2024 é frágil como achado.**
   - Decide sozinho o α̂ de Hill = 1,82, sobre k = 12 de 250 retornos (abaixo de 2 para todo k de 10 a 30).
   - O IC95% de κ_1, [0,094; 0,400], contém 0,15: só pelo κ seria fronteira.
   - Os preços do COTAHIST não são ajustados por proventos. Os piores dias (2024-03-08, −11,2%; 2024-05-15;
     2024-12-12; …) podem incluir datas ex de PETR4, e a estação não tem fonte de proventos para verificar.
   - Sugestão ao PO, como bloco de decisão: um ajuste de proventos no `dados_br.py`, ou um aviso no veredito
     quando o domínio é decidido só por α̂ com o IC de κ na fronteira.
10. **A linha do limiar de κ no `relatorio.py` sai `[corpus]` fixa**, codificada no script e não consultada no
    MCP. Neste aceite ela confere, porque o MCP devolve a heurística "kappa acima de 0,15" (8.3.2) aprovada. Se o
    nó sair do corpus aprovado, o script continuará marcando `[corpus]`, o que fere a regra "[corpus] só do MCP".
11. **Horizonte e taxa da P2 (rodada 2) são escolhas da resposta.** Horizonte de 12 meses e Selic realizada dos
    últimos 12 meses: a pergunta não deu prazo, e a estação não prevê juros. Com outra escolha a perda numérica
    muda; a simbólica não.
