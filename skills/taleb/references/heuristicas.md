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
| `kappa` | κ_1 = κ(n0=1, n=2) de Taleb (o κ da eq. 8.8 e da Table 8.3 do SCFT), exato para a amostra | `caudas.kappa_1_exato`, intervalo `relatorio.intervalo_kappa_1`, equação `kappa` |
| `alpha` | α̂ de Hill da cauda esquerda, k = max(10, n//20) | `caudas.hill`, equação `hill` |
| `H` | assimetria empírica (choque de ±2σ por quantis) | `convexidade.assimetria_empirica`, equação `assimetria_convexidade` |
| `fracao_segura` | fração da carteira no lado de perda máxima conhecida | `convexidade.barbell` |

Uma condição sobre `H` vale para o **intervalo bootstrap inteiro** de H (o limite superior para `H < 0`, o
inferior para `H > 0`), como a classe de fragilidade do `relatorio.py`: ruído amostral não dispara
heurística. O mesmo vale para `kappa`: κ_1 é o exato da amostra (M(1) e M(2) da distribuição empírica, sem
Monte Carlo) e `kappa > 0.15` só vale se o limite **inferior** do IC95% bootstrap de κ_1 passa de 0,15;
`kappa <= 0.15` só se o **superior** fica ≤ 0,15. Intervalo que contém 0,15 é **fronteira**: nenhuma das
duas vale, e a heurística que depende só de κ não dispara (a que tem `or alpha < 2` ainda pode disparar
por α̂). Os limiares de domínio (κ_1 > 0,15, α̂ < 2) são os mesmos `LIMIAR_KAPPA` e `LIMIAR_ALFA` do
`relatorio.py`; mudar um exige mudar o outro. O de κ é do corpus [corpus] — (Statistical_Consequences_of_Fat_Tails.pdf.md,
8.3.2 Practical significance for sample sufficiency): "Any value of κ above .15 effectively indicates a high
degree of unreliability of the 'normal approximation'"; a eq. 8.8 (mesmo tópico) usa κ_1, e a Table 8.3
(tópico 8.2 THE METRIC) o tabula para Pareto e Student — κ_1 é a quantidade em uso; conferido no Wolfram, Student T(3) dá κ_1 = 0,2904 e
n_ν = 30^(−1/(κ_1−1)) = 120,7, os "120 observations" do mesmo tópico. O de α̂ é do incerto [externo].

Heurística é diagnóstico de método, nunca instrução sobre ativo: o que ela permite dizer é "esta medida não
serve aqui" ou "esta exposição é côncava", jamais o que o PO deve fazer com a posição.

### variância inútil no Extremistão

enunciado: se κ_1 > 0,15 ou α̂ < 2, a variância não descreve o risco — não se usa VaR paramétrico, desvio-padrão nem índice de Sharpe como medida de risco; descreve-se a cauda (α̂, razão máximo/soma, pior perda observada).
condicao: `kappa > 0.15 or alpha < 2`
sustenta: caudas gordas, falácia lúdica
fonte: [externo] — Statistical Consequences of Fat Tails (2020)

### média sem sentido

enunciado: se α̂ ≤ 1, nem a média teórica existe; a média amostral é dominada pelo maior evento e não deve ser apresentada como "retorno esperado".
condicao: `alpha <= 1`
sustenta: caudas gordas, cisne negro
fonte: [externo] — Statistical Consequences of Fat Tails (2020)

### Mediocristão não é atestado de segurança

enunciado: κ_1 ≤ 0,15 e α̂ ≥ 2 não declaram Extremistão pelos limiares do Incerto, mas não fazem da variância uma medida de risco: com 2 ≤ α̂ < 4 a variância existe, porém o quarto momento é infinito e a estimativa dela é instável (retornos de ações, com α perto de 3, são o exemplo de Taleb de por que desvio-padrão e Sharpe enganam); e a janela pode não ter visto o evento extremo.
condicao: `kappa <= 0.15 and alpha >= 2`
sustenta: problema do peru, caudas gordas
fonte: [externo] — Statistical Consequences of Fat Tails (2020); The Black Swan (2007), cap. 4

### exposição côncava primeiro

enunciado: se o intervalo de H fica todo abaixo de 0, a exposição perde mais com o choque desfavorável do que ganha com o favorável; o diagnóstico nomeia primeiro a fonte da concavidade (alavancagem, dívida, dependência de um cenário), antes de qualquer análise de ganho.
condicao: `H < 0`
sustenta: convexidade, antifragilidade, via negativa
fonte: [externo] — Antifragile (2012), livros V e VI

### o peru no Extremistão

enunciado: concavidade com cauda gorda é o caso mais frágil — uma série calma nessa combinação acumula fragilidade, e a ausência de perda grande no histórico não é evidência de segurança.
condicao: `H < 0 and (kappa > 0.15 or alpha < 2)`
sustenta: problema do peru, caudas gordas, convexidade
fonte: [externo] — The Black Swan (2007), cap. 4; Antifragile (2012)

### convexidade que paga na cauda

enunciado: se o intervalo de H fica todo acima de 0 em domínio de Extremistão, a exposição se beneficia da dispersão e os eventos raros pesam a favor; o diagnóstico registra que a média amostral subestima esse lado.
condicao: `H > 0 and (kappa > 0.15 or alpha < 2)`
sustenta: convexidade, antifragilidade, cisne negro
fonte: [externo] — Antifragile (2012), livro V

### perda máxima delimitada por construção

enunciado: num barbell com fracao_segura ≥ 0,85 (limiar autoral do Incerto, na faixa de 85–90% que Taleb cita), com lado seguro de perda nula, como em convexidade.barbell, e o lado convexo de perda limitada ao aplicado, a perda máxima da carteira é no máximo 15%, sem depender de previsão — é a perda que a estação descreve, não um tamanho de posição.
condicao: `fracao_segura >= 0.85`
sustenta: barbell, via negativa, ergodicidade
fonte: [externo] — Antifragile (2012); The Black Swan (2007), cap. 13 (faixa de 85–90%; o corte em 0,85 e o lado seguro de perda nula são do modelo do Incerto)
