# Heurísticas — regras práticas com condição verificável

Cada heurística liga um diagnóstico numérico da estação a uma consequência de método. Campos:

- `enunciado:` a regra, em uma frase;
- `condicao:` quando ela se aplica, em sintaxe SymPy sobre os símbolos `kappa`, `alpha`, `H` e
  `fracao_segura` (`or`/`and`/`not` de comparações simples são aceitos). O teste da estação passa toda
  condição por `fiscal.relacional_parseia(condicao, ["kappa", "alpha", "H", "fracao_segura"])` (pode levantar `TempoEsgotado` numa condição patológica);
- `sustenta:` os conceitos de `doutrina.md` que a justificam, pelo título do verbete;
- `fonte:` como na doutrina — `[externo]` com o livro enquanto nenhuma onda estiver conferida; `(documento,
  tópico)` dos `conferidos/` depois da Task 19.

Símbolos, com a mesma definição do `relatorio.py`:

| Símbolo | O quê | De onde |
|---|---|---|
| `kappa` | κ(n0=1, n=30) de Taleb | `caudas.kappa`, equação `kappa` |
| `alpha` | α̂ de Hill da cauda esquerda, k = max(10, n//20) | `caudas.hill`, equação `hill` |
| `H` | assimetria empírica (choque de ±2σ por quantis) | `convexidade.assimetria_empirica`, equação `assimetria_convexidade` |
| `fracao_segura` | fração da carteira no lado de perda máxima conhecida | `convexidade.barbell` |

Uma condição sobre `H` vale para o **intervalo bootstrap inteiro** de H (o limite superior para `H < 0`, o
inferior para `H > 0`), como a classe de fragilidade do `relatorio.py`: ruído amostral não dispara
heurística. Os limiares de domínio (κ > 0,3, α̂ < 2) são os mesmos `LIMIAR_KAPPA` e `LIMIAR_ALFA` do
`relatorio.py`; mudar um exige mudar o outro.

Heurística é diagnóstico de método, nunca instrução sobre ativo: o que ela permite dizer é "esta medida não
serve aqui" ou "esta exposição é côncava", jamais o que o PO deve fazer com a posição.

### variância inútil no Extremistão

enunciado: se κ > 0,3 ou α̂ < 2, a variância não descreve o risco — não se usa VaR paramétrico, desvio-padrão nem índice de Sharpe como medida de risco; descreve-se a cauda (α̂, razão máximo/soma, pior perda observada).
condicao: `kappa > 0.3 or alpha < 2`
sustenta: caudas gordas, falácia lúdica
fonte: [externo] — Statistical Consequences of Fat Tails (2020)

### média sem sentido

enunciado: se α̂ ≤ 1, nem a média teórica existe; a média amostral é dominada pelo maior evento e não deve ser apresentada como "retorno esperado".
condicao: `alpha <= 1`
sustenta: caudas gordas, cisne negro
fonte: [externo] — Statistical Consequences of Fat Tails (2020)

### Mediocristão não é atestado de segurança

enunciado: κ ≤ 0,3 e α̂ ≥ 2 não declaram Extremistão pelos limiares do Incerto, mas não fazem da variância uma medida de risco: com 2 ≤ α̂ < 4 a variância existe, porém o quarto momento é infinito e a estimativa dela é instável (retornos de ações, com α perto de 3, são o exemplo de Taleb de por que desvio-padrão e Sharpe enganam); e a janela pode não ter visto o evento extremo.
condicao: `kappa <= 0.3 and alpha >= 2`
sustenta: problema do peru, caudas gordas
fonte: [externo] — Statistical Consequences of Fat Tails (2020); The Black Swan (2007), cap. 4

### exposição côncava primeiro

enunciado: se o intervalo de H fica todo abaixo de 0, a exposição perde mais com o choque desfavorável do que ganha com o favorável; o diagnóstico nomeia primeiro a fonte da concavidade (alavancagem, dívida, dependência de um cenário), antes de qualquer análise de ganho.
condicao: `H < 0`
sustenta: convexidade, antifragilidade, via negativa
fonte: [externo] — Antifragile (2012), livros V e VI

### o peru no Extremistão

enunciado: concavidade com cauda gorda é o caso mais frágil — uma série calma nessa combinação acumula fragilidade, e a ausência de perda grande no histórico não é evidência de segurança.
condicao: `H < 0 and (kappa > 0.3 or alpha < 2)`
sustenta: problema do peru, caudas gordas, convexidade
fonte: [externo] — The Black Swan (2007), cap. 4; Antifragile (2012)

### convexidade que paga na cauda

enunciado: se o intervalo de H fica todo acima de 0 em domínio de Extremistão, a exposição se beneficia da dispersão e os eventos raros pesam a favor; o diagnóstico registra que a média amostral subestima esse lado.
condicao: `H > 0 and (kappa > 0.3 or alpha < 2)`
sustenta: convexidade, antifragilidade, cisne negro
fonte: [externo] — Antifragile (2012), livro V

### perda máxima delimitada por construção

enunciado: num barbell com fracao_segura ≥ 0,85 (limiar autoral do Incerto, na faixa de 85–90% que Taleb cita), com lado seguro de perda nula, como em convexidade.barbell, e o lado convexo de perda limitada ao aplicado, a perda máxima da carteira é no máximo 15%, sem depender de previsão — é a perda que a estação descreve, não um tamanho de posição.
condicao: `fracao_segura >= 0.85`
sustenta: barbell, via negativa, ergodicidade
fonte: [externo] — Antifragile (2012); The Black Swan (2007), cap. 13 (faixa de 85–90%; o corte em 0,85 e o lado seguro de perda nula são do modelo do Incerto)
