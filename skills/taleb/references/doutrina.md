# Doutrina — os conceitos de Taleb que a estação usa

Um verbete por conceito, em paráfrase própria (nunca citação longa). Cada verbete diz o que o conceito
afirma, como ele aparece no diagnóstico da estação e de onde vem. A linha `fonte:` é obrigatória: enquanto
nenhuma onda do corpus estiver conferida, ela é `[externo]` e nomeia o livro de Taleb em que o tema é
desenvolvido; quando a onda 1 tiver o trecho (Task 19), passa a `(documento, tópico)` dos `conferidos/`, e a
afirmação do especialista que se apoiar no verbete passa de `[externo]` a `[corpus]` ou `[staging]`.

Quem consome: `SKILL.md` (passo 2 do rito) e `heuristicas.md` (campo `sustenta:`, que cita os títulos
abaixo literalmente).

### antifragilidade

Há três respostas possíveis de um sistema à volatilidade, ao estresse e ao acaso: o frágil perde com
elas, o robusto fica indiferente e o antifrágil melhora. A antifragilidade não é o mesmo que resistência:
é ter mais a ganhar do que a perder quando a variabilidade aumenta. O que define a classe é a forma da
resposta ao choque, não a previsão do choque.

No diagnóstico: a classe frágil/robusto/antifrágil de um ativo sai do intervalo bootstrap da assimetria
empírica H (`relatorio.py`, equação `assimetria_convexidade`): todo acima de 0 é antifrágil, todo abaixo é
frágil, intervalo que contém 0 é robusto.

fonte: [externo] — Antifragile: Things That Gain from Disorder (2012)

### caudas gordas

Extremistão × Mediocristão. No Mediocristão (altura, peso, consumo calórico) nenhuma observação isolada
muda o total de forma relevante, e média e variância descrevem bem o fenômeno. No Extremistão (riqueza,
vendas de livros, retornos de mercado, perdas de seguradora) um único evento pode dominar a soma, a
lei dos grandes números converge devagar demais para ser útil e momentos como a variância ficam
instáveis ou nem existem. Ferramentas calibradas para a distribuição normal (desvio-padrão, VaR
paramétrico, índice de Sharpe) enganam no Extremistão, porque escondem justamente a cauda que decide o
resultado.

No diagnóstico: `caudas.py` mede o domínio por três vias — razão máximo/soma R_n(p), expoente de cauda α̂
de Hill e a métrica κ de Taleb (velocidade de convergência da média). O `relatorio.py` declara Extremistão
quando κ(n0=1, n=30) > 0,3 ou α̂ < 2.

fonte: [externo] — Statistical Consequences of Fat Tails (2020); The Black Swan (2007), cap. 3

### convexidade

Uma exposição é convexa quando o ganho com um choque favorável supera a perda com um choque
desfavorável de mesmo tamanho; é côncava no caso contrário. Pela desigualdade de Jensen, a média da
resposta a choques simétricos fica acima da resposta à média quando a função é convexa: quem é convexo
ganha com a dispersão sem precisar acertar a direção. Fragilidade é, nessa leitura, concavidade a
choques; antifragilidade é convexidade.

No diagnóstico: H = [f(x+δ) + f(x−δ)]/2 − f(x) (`convexidade.assimetria`); sobre dados, a versão
empírica por quantis de ±2σ (`convexidade.assimetria_empirica`). H > 0 é convexo, H < 0 é côncavo.

fonte: [externo] — Antifragile (2012), livro V e apêndices técnicos

### barbell

Estratégia de dois extremos e nada no meio: a maior parte da exposição em algo de perda máxima
conhecida e pequena (o lado seguro) e uma fração menor em apostas convexas, de perda limitada ao que foi
aplicado e ganho potencialmente grande. O meio-termo "de risco moderado" é evitado porque costuma
esconder perda de cauda que não aparece na volatilidade medida. A virtude da construção é que a perda
máxima da carteira fica delimitada por construção, não por estimativa.

No diagnóstico: `convexidade.barbell(fracao_segura, perda_maxima_convexa)` devolve a perda máxima da
carteira, (1 − fracao_segura) · perda_maxima_convexa. A estação descreve essa perda máxima; não
dimensiona posição de ninguém.

fonte: [externo] — Antifragile (2012); The Black Swan (2007), cap. 13

### via negativa

O conhecimento sobre o que falha é mais robusto do que o conhecimento sobre o que funciona; tirar o que
fragiliza costuma render mais, e com menos risco de erro, do que acrescentar o que promete melhorar. Na
prática: identificar e eliminar exposições côncavas (alavancagem, dívida, dependência de um único
cenário) antes de procurar ganhos.

No diagnóstico: a estação aponta o que torna uma exposição frágil (concavidade, cauda esquerda gorda,
crescimento temporal abaixo do de ensemble) em vez de apontar o que "deveria" ser feito para ganhar.

fonte: [externo] — Antifragile (2012), livro VI (Via Negativa)

### ergodicidade

Um processo é ergódico quando a média sobre muitos indivíduos num instante (ensemble) coincide com a
média de um só indivíduo ao longo do tempo. Em apostas multiplicativas com risco de ruína isso não vale:
a média de ensemble pode ser positiva enquanto quase todo caminho individual empobrece, porque quem
quebra não volta para colher a média. O que importa para quem vive um só caminho é a taxa de
crescimento temporal, e a ruína é absorvente.

No diagnóstico: `convexidade.crescimento_temporal` (média de ln(1+r)) contra
`convexidade.crescimento_ensemble` (média aritmética); a diferença entre os dois é o custo da
não-ergodicidade. Qualquer r ≤ −1 é ruína e dá −∞.

fonte: [externo] — Skin in the Game (2018), cap. "The Logic of Risk Taking"; Statistical Consequences of Fat Tails (2020)

### skin in the game

Quem decide deve arcar com as consequências da decisão; a simetria entre ganho e perda é condição de
justiça e de aprendizado. Quem transfere a cauda para outros (o gestor que fica com o bônus no ano bom e
repassa a perda no ano ruim) tem incentivo para construir exposições frágeis com aparência de estáveis.
Opinião sem exposição pesa pouco.

No diagnóstico: é a razão de a estação nunca emitir recomendação — ela não carrega a consequência da
decisão do PO; descreve a exposição e deixa a decisão com quem vai arcar com ela.

fonte: [externo] — Skin in the Game: Hidden Asymmetries in Daily Life (2018)

### falácia lúdica

Confundir a aleatoriedade domesticada dos jogos (dados, roleta, distribuição conhecida, regras fixas)
com a incerteza do mundo real, em que a própria distribuição é desconhecida e as regras mudam. Modelos
de risco que tratam o mercado como um cassino de probabilidades conhecidas importam essa falácia.

No diagnóstico: toda estimativa da estação (κ, α̂, H) sai com a amostra e o método declarados e, para H, com
intervalo bootstrap; o número é um diagnóstico sobre o passado observado, não a probabilidade "verdadeira"
de um jogo de regras conhecidas.

fonte: [externo] — The Black Swan (2007), cap. 9

### problema do peru

O peru alimentado todos os dias acumula evidência crescente de que o fazendeiro o quer bem, até a
véspera do feriado. Uma longa série sem dano não prova ausência de risco; em exposições côncavas, a
calmaria pode ser exatamente a acumulação de fragilidade. É o problema da indução aplicado a caudas.

No diagnóstico: uma janela de dados sem evento extremo não autoriza concluir Mediocristão. Volatilidade
baixa medida, com α̂ instável ou κ alto, é sinal de que a amostra ainda não viu a cauda.

fonte: [externo] — The Black Swan (2007), cap. 4; Fooled by Randomness (2001)

### cisne negro

Evento raro, de impacto extremo, que fica fora do que as expectativas regulares previam e que, depois de
acontecer, é racionalizado como se fosse previsível. A resposta de Taleb não é tentar prever o próximo,
mas reduzir a exposição aos cisnes negros negativos e aumentar a exposição aos positivos — trocar
previsão por estrutura de payoff.

No diagnóstico: é o motivo de o passo 1 do rito enquadrar toda pergunta como exposição (payoff) e nunca
como previsão de preço ou de evento.

fonte: [externo] — The Black Swan: The Impact of the Highly Improbable (2007)
