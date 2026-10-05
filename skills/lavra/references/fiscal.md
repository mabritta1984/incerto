# Fiscal de duas vias — protocolo da prova Wolfram (dono único)

Esta reference é **dona única** do protocolo da segunda via do fiscal: como o agente monta o código
Wolfram a partir do candidato, como roda, o que conta como verde e como registra. A primeira via (SymPy,
provas P1–P3) e a conferência entre as vias (P4) são do `skills/lavra/scripts/fiscal.py`; o registro é do
`skills/lavra/scripts/registrar_prova.py`. Os formatos de linha descritos aqui são os que esses dois
scripts validam.

**Tempo.** Todo trabalho do SymPy (o parse da extração e do portão; `equivalente` e `relacional_parseia`
do fiscal) roda sob limite de tempo de parede (`skills/lavra/scripts/limite_sympy.py`;
`INCERTO_LIMITE_SYMPY_S`, padrão 10 s): esgotado, é perda declarada `nao_suportado:tempo_esgotado` na
extração e `indeterminado` "tempo esgotado no SymPy (<n> s)" no fiscal — nunca trava a esteira.

Se um item esgota o limite depende da carga da máquina e de `INCERTO_LIMITE_SYMPY_S`: reexecuções perto do
limite podem alternar verde↔indeterminado. Isso falha fechado — a aprovação recusa com "fiscal desatualizado"
e a extração recusa sobrescrever —; reexecute com o mesmo limite ou aumente-o.

**Regra.** `DERIVA_DE` e `:Equacao` com momento fechado só saem de staging com a prova SymPy verde **e**
a prova Wolfram verde e concordante. Divergência entre as vias é vermelho, com as duas saídas no relato.
**Nenhum script chama o Wolfram**: quem roda é o agente, pelo MCP do Wolfram
(`WolframLanguageEvaluator`), e o script só registra e confere.

## O que exige prova Wolfram

| O quê | De onde vem | Chave da prova | Linha em `provas-<onda>.jsonl` |
|---|---|---|---|
| derivação | toda linha P2 do `fiscal-<onda>.jsonl` (uma por linha de `derivacoes-<onda>.jsonl`) | `mae` + `filha` | `{"prova": "P2", "via": "wolfram", "mae", "filha", "codigo", "saida", "veredito", "impressao"}` |
| momento fechado | todo candidato de `equacoes-<onda>.jsonl` com `momento_fechado` não vazio (dict, ex.: `{"media": "alpha*L/(alpha-1)"}`) | `equacao` (o `nome` do candidato) | `{"prova": "momento", "via": "wolfram", "equacao", "codigo", "saida", "veredito", "impressao"}` |
| equação (opcional) | candidato que parseia (P1 verde) mas que o próprio corpus contradiz — outra passagem, definição ou equação numerada da fonte dá outro resultado | `equacao` (o `nome` do candidato) | `{"prova": "equacao", "via": "wolfram", "equacao", "codigo", "saida", "veredito", "impressao"}` |

A prova `equacao` não é exigida de todo candidato: sem ela, nada muda. Registrada, o fiscal gera a P4 de
equação (`{"prova": "P4", "equacao", "prova_wolfram": "equacao"}`) com o veredito dela, e a aprovação a lê:
vermelha → a equação fica em staging com a pendência citando a saída Wolfram; verde → `verificado_por`
da `:Equacao` ganha `wolfram`; indeterminado só passa com aceite exato
(`{"tipo": "aceitar_indeterminado", "prova": "P4", "equacao", "prova_wolfram": "equacao"}`).

Candidato **sem** `momento_fechado` cujo `srepr` aplica `E` ou `Var` (`\mathbb{E}[X] = …`,
`\operatorname{Var}(X) = …`) afirma um momento que ninguém declarou: a P4 dá `indeterminado` "aplica E/Var
sem momento_fechado declarado" (chave `equacao`). Não há prova Wolfram a registrar para ele; o caminho é a
decisão `momento_fechado` do PO (e então a prova acima) ou o aceite da linha.

Uma prova por chave. Um momento fechado com várias entradas (`media`, `variancia`, …) tem **uma** prova,
cujo código confere todas de uma vez (ver abaixo).

- **Mãe + filha é a chave da derivação.** Duas linhas de `derivacoes-<onda>.jsonl` com a mesma mãe e a
  mesma filha (por exemplo, com substituições diferentes) são **derivação ambígua para a prova Wolfram**:
  a P4 dá vermelho em todas, e o registrador recusa. Desfaz-se na rodada, deixando uma só.
- **`impressao` amarra o veredito ao que foi provado.** É o sha256 hex de
  `json.dumps(conteudo, sort_keys=True, ensure_ascii=False)`, com `conteudo` =
  `{"mae_srepr", "filha_srepr", "simbolo", "substituicao"}` (derivação),
  `{"equacao_srepr", "momento_fechado"}` (momento) ou `{"latex", "srepr"}` (equação). O registrador a calcula de `equacoes-<onda>.jsonl` e
  `derivacoes-<onda>.jsonl` (recusa derivação não declarada, equação desconhecida ou momento não
  declarado); a P4 a recalcula da onda atual. Se o candidato foi reextraído, o `momento_fechado` editado
  ou a substituição trocada depois do registro, a P4 dá vermelho **"prova Wolfram desatualizada"**: refazer
  a prova e registrar com `--substituir`.

## Rito

1. `python3 skills/lavra/scripts/fiscal.py --onda <onda>` — a via SymPy; toda derivação e todo momento
   ainda sem prova Wolfram sai como P4 vermelho "sem prova Wolfram". Essa é a lista de trabalho.
2. Para cada item, montar o código pelas regras abaixo, **sem olhar o veredito SymPy para decidir o
   código** (as vias são independentes; o SymPy só é consultado para saber se a mãe tem vários ramos).
3. Rodar o código pelo MCP, uma avaliação por prova.
4. Salvar o código rodado em `<arquivo.wl>` e a saída do MCP em `<arquivo.txt>` — **verbatim**: o código é
   exatamente o que foi avaliado; a saída é colada como veio, com `Out[1]=`, mensagens e avisos, sem
   editar, resumir, reformatar nem cortar. Sugestão de lugar: `_esteira/incerto/wolfram-<onda>/`.
5. Decidir o veredito pelas regras abaixo (a saída decide; nunca o que "deveria" dar).
6. Registrar:

       python3 skills/lavra/scripts/registrar_prova.py --onda <onda> --prova P2 --mae <mãe> --filha <filha> \
               --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado
       python3 skills/lavra/scripts/registrar_prova.py --onda <onda> --prova momento --equacao <nome> \
               --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado
       python3 skills/lavra/scripts/registrar_prova.py --onda <onda> --prova equacao --equacao <nome> \
               --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado

   Chave já registrada é recusada; refazer uma prova exige `--substituir` (a linha antiga sai do arquivo).
   **O verde é conferido**: o registrador lê a última linha `Out[n]=` da saída e só aceita `--veredito
   verde` se o que vem depois dela for exatamente `0` ou uma lista só de `0` (`{0}`, `{0, 0}`); saída sem
   `Out[n]=`, ou com qualquer outro resultado, recusa o verde sem gravar nada. **O indeterminado também é
   conferido — o Wolfram decide**: se o último `Out[n]=` é uma diferença **fechada e não nula**, o Wolfram
   calculou e não deu 0, e isso é `vermelho`; `--veredito indeterminado` é recusado. Tudo se julga no
   **resultado** (o que vem depois do último `Out[n]=`), nunca nas mensagens antes dele: um
   `General::timeout`/`TimeConstrained::timeout` seguido de `Out[1]= (2*alpha)/(-1 + alpha)` é diferença
   fechada não nula. "Sem resultado" (indeterminado legítimo) só quando não há `Out[n]=` nenhum ou o resultado
   casa `^$Aborted$`, `$TimedOut`, `^Failure[` ou `^TimeConstrained[`. "Fechada" = o resultado não tem cabeça
   não avaliada: `Integrate`, `NIntegrate`, `Limit`, `Expectation`, `NExpectation`, `Sum`, `Piecewise`,
   `Indeterminate`, `$Failed`, `DirectedInfinity` (na saída, `Infinity`/`ComplexInfinity`), `Undefined`, e — pelo
   protocolo da derivação — `Solve`/`Reduce` devolvidos sem avaliar.
   - `ConditionalExpression[d, cond]` vale pelo `d`: com `d` fechado não nulo é diferença fechada não nula
     (vermelho); `ConditionalExpression[0, cond]` fica aberto (indeterminado) — a condição é da P3 ou do aceite
     do PO. `Piecewise` fica aberto.
   - Lista: diferença fechada não nula se **algum** elemento é. Só na derivação (P2) há exceções de ramo: lista
     vazia `{}` (`Solve` sem solução) e lista de ramos com algum `0` (a filha escolhe um ramo) são indeterminado
     legítimo. Em momento e equação, não: `Out[1]= {0, -(((-3 + alpha)*alpha*L^2)/((-2 + alpha)*(-1 +
     alpha)^2))}` (saída real, variância errada) é vermelho.
   - Zero numérico (`0.`, `0.0`, `` 0``15.2 ``) nunca é verde — `N` pode esconder um resíduo pequeno —, mas é
     indeterminado aceito.
   `vermelho` é registrado como o agente o decidiu.

   **Dono único da regra**: `fiscal.conferir_veredito_wolfram`. O registrador a aplica antes de gravar; o
   fiscal a reaplica ao CARREGAR `provas-<onda>.jsonl` (P2, momento e equação): linha editada à mão que a fere
   (verde sobre saída não nula, indeterminado sobre diferença fechada não nula) não aborta o fiscal — a P4
   dela sai `vermelho` "prova Wolfram inválida", com o motivo e a saída verbatim.
7. `fiscal.py --onda <onda>` de novo: a P4 junta as provas às linhas P2 e aos momentos e dá o veredito
   final da segunda via. Prova registrada que não se junta a nada da onda (equação que não existe mais,
   derivação não declarada) sai como aviso "prova órfã" na seção `## Avisos` do relatório e na saída do
   fiscal — nunca em silêncio, e nunca como linha do `fiscal-<onda>.jsonl`.

## Do candidato ao código Wolfram

O ponto de partida é o `srepr` do candidato (o LaTeX de origem só para conferir a leitura). A tradução é
mecânica e **preserva os nomes**:

| `srepr` | Wolfram |
|---|---|
| `Equality(lhs, rhs)` | os dois lados, usados como abaixo |
| `Symbol('x')` | `x` (mesmo nome) |
| `Add(a, b)`, `Mul(a, b)`, `Pow(a, b)` | `a + b`, `a*b` (ou `a b`), `a^b` |
| `Integer(n)`, `Rational(p, q)`, `Float(...)` | `n`, `p/q`, o número |
| `Pow(x, Rational(1, 2))` | `x^(1/2)` (ou `Sqrt[x]`) |
| `log(x)`, `log(x, E)` | `Log[x]` (logaritmo natural nos dois casos) |
| `exp(x)` | `Exp[x]` |
| `pi`, `E` (as constantes do SymPy, sem `Symbol(…)`) | `Pi`, `E` |
| `Abs(x)` | `Abs[x]` |

- **`\pi` é π e `e` base de potência é o número de Euler** (rodada de extração de 05/10, decidida pelo corpus
  e pelo Wolfram na onda 2026-10-TALEB-1): a extração grava `pi` e `exp(…)`/`E` no `srepr`, e o código usa
  `Pi`, `Exp[…]`/`E`. `e` solto (não base de potência) segue `Symbol('e')` → `e` minúsculo, símbolo comum;
  `Symbol('pi')` não sai mais num candidato que parseia; `\pi` sozinho num lado da relação (`\pi = …`, a
  carteira do SCFT eq. 20.1) é variável e a extração o dá como perda `nao_suportado:\pi_como_variavel`.
  Nunca trocar símbolo por constante (ou o inverso) numa via só: o código segue o `srepr`.
- **Reextração depois dessa rodada**: todo candidato cujo `srepr` mudou (os que tinham `Symbol('pi')` ou
  `Symbol('e')` base de potência, e o SCFT#363, agora perda `nao_suportado:_{(`) tem a prova Wolfram
  **desatualizada** na P4 — é o correto. A prova não é editada: refaz-se o código a partir do `srepr` novo
  e registra-se com `registrar_prova.py … --substituir`.
- `lambda` fica `lambda` (no Wolfram é um nome livre).
- Nome que no Wolfram é embutido (`C`, `D`, `E`, `I`, `K`, `N`, `O`, `Re`, `Im`, `Gamma`, `Beta`, …) ou que tem
  `_` (no Wolfram `_` é padrão: `x_i` não é símbolo) é renomeado de forma injetiva — prefixo `s` para o
  embutido (`N` → `sN`), `U` no lugar do `_` (`n_0` → `nU0`, `kappa_n` → `kappaUn`) — e o código abre com
  um comentário da troca: `(* N -> sN; n_0 -> nU0 *)`. Nunca renomear para a função embutida.
- A `substituicao` declarada na derivação (`{"M": "k*S**2"}`, sintaxe SymPy) vira uma regra Wolfram aplicada
  **aos dois lados**: `sub = {M -> k S^2}`.

### Derivação (P2)

Com `mae: L == R`, `filha: s == F` e `s` o símbolo isolado (`simbolo` na linha P2):

    Simplify[(F) - (s /. First@Solve[(L) - (R) == 0, s])]

com substituição declarada:

    Simplify[((F) /. sub) - (s /. First@Solve[((L) - (R) /. sub) == 0, s])]

**Verde** sse a saída é exatamente `0` (`Out[1]= 0`). Saída com expressão não nula → **vermelho**.
`Solve` sem solução (`{}`), devolvido sem avaliar, `$Failed`, `$Aborted` ou só mensagens de erro →
**indeterminado**.

**Mãe com mais de uma solução.** `First@Solve` escolhe um ramo e daria verde falso. Quando a mãe pode ter
vários ramos para `s` — a P2 do SymPy diz "filha escolhe um ramo (k de n)", `s` aparece em grau maior que 1,
sob raiz par, `Abs` ou função periódica, ou o `Solve` emite `Solve::ifun` —, o código confere **todos** os
ramos (sem `First@`; a saída é uma lista, uma diferença por solução):

    Simplify[(F) - (s /. Solve[(L) - (R) == 0, s])]

`{0}` (solução única, igual à filha) → **verde**; lista com mais de um elemento e algum `0` →
**indeterminado** (a filha escolhe um ramo; aceitar é decisão do PO na aprovação, não do fiscal); nenhum `0`
→ **vermelho**. Note que SymPy indeterminado + Wolfram verde é "vias divergem" na P4 (vermelho): ramo
escolhido nunca vira verde por uma das vias.

### Momento fechado

O código calcula o momento pela distribuição declarada na fonte e subtrai o fechado declarado, com
`Assumptions` declarando **todo** parâmetro (o domínio que a fonte dá para a distribuição e para a
existência do momento). Uma entrada (é o código do gabarito, em uma linha):

    FullSimplify[Expectation[x, x \[Distributed] ParetoDistribution[L, alpha], Assumptions -> alpha > 1 && L > 0] - (alpha L/(alpha - 1)), Assumptions -> alpha > 1 && L > 0]

Várias entradas do `momento_fechado` (média, variância, k-ésimo momento): uma lista, em ordem de chave do
dict, com `Mean[d]`/`Expectation`, `Variance[d]` ou `Moment[d, k]`:

    With[{d = ParetoDistribution[L, alpha]},
      FullSimplify[{Mean[d] - (<media>), Variance[d] - (<variancia>)}, Assumptions -> alpha > 2 && L > 0]]

**Verde** sse a saída é `0` (ou a lista inteira de `0`); diferença não nula → **vermelho**; `Expectation`
devolvido sem avaliar, `Indeterminate`, `ConditionalExpression` ou erro → **indeterminado**. O aviso
`Symbol::undefined`/`Symbol::undefined2` sobre parâmetros livres (`L`, `alpha`, …) é esperado e inofensivo —
aparece mesmo com os parâmetros declarados nas `Assumptions` (ver o gabarito) — e não muda o veredito; é
colado na saída como veio.

### Equação (a própria)

O corpus decide; o Wolfram confere. O código calcula, **pela definição que a própria fonte dá** (a
distribuição, a definição numerada, a equação de que a afirmação depende — citadas no bloco de decisão), o
lado que a equação afirma, e subtrai o lado direito do candidato, com `Assumptions` declarando todo
parâmetro no domínio da fonte:

    FullSimplify[(<o que a fonte define, calculado>) - (<lado direito do candidato>), Assumptions -> <domínio>]

**Verde** sse a saída é exatamente `0`; diferença não nula → **vermelho** (a equação contradiz a fonte);
`Expectation`/`Limit` devolvido sem avaliar, `Indeterminate`, `ConditionalExpression` ou erro →
**indeterminado**. O código nunca é montado a partir do veredito esperado: a definição vem da fonte, o lado
direito vem do `srepr` do candidato. A equação vermelha não é corrigida aqui: a saída vai ao PO no bloco de
decisão (a extração ou o texto da fonte pode estar errado; quem decide é ele).

## Falso vermelho conhecido: `e^x` contra `\log` (histórico — resolvido na extração em 05/10)

Desde a rodada de 05/10, `e^{x}` é extraído como `exp(x)` e a mãe `y = e^{x}` dá `x = log(y)` nas duas vias:
o caso abaixo deixou de existir para candidatos reextraídos. Fica o registro de por que a regra mudou.

Com `e` símbolo comum, a mãe `y = e^{x}` dá `x = log(y)/log(e)` nas duas vias; a filha `x = \log y` (log
natural, `log(y, E)` no `srepr`) não bate: o SymPy dá vermelho ("a mãe dá x = log(y)/log(e); a filha diz
x = log(y)") e o código Wolfram com `e` símbolo também não dá `0` (gabarito abaixo:
`((-1 + Log[e])*Log[y])/Log[e]`). É vermelho concordante e é **falso**: a inversão vale para o número de
Euler. Não se conserta trocando `e` por `E` só no Wolfram; registra-se a saída como veio e o caso vai ao PO
no bloco de decisão da rodada (renomear `e` como constante é decisão dele).

O gabarito rodou com `First@Solve` e emitiu `Solve::ifun`. Pela regra da mãe com mais de uma solução
(acima), `Solve::ifun` obriga o agente a **rodar de novo na forma de todos os ramos**
(`Simplify[(Log[y]) - (x /. Solve[y - (e^x) == 0, x])]`) antes de registrar, e é essa a prova registrada.
Com `e` símbolo comum o resultado é o mesmo falso vermelho conhecido de qualquer forma.

## Gabarito (rodado pelo MCP Wolfram em 04/10 e 05/10/2026, saídas verbatim)

### Kelly — filha correta (verde)

Mãe `\frac{p b}{1 + b f} - \frac{1 - p}{1 - f} = 0`, filha `f = p - \frac{1 - p}{b}`, símbolo `f`.

Código:

```
Simplify[(p - (1 - p)/b) - (f /. First@Solve[p b/(1 + b f) - (1 - p)/(1 - f) == 0, f])]
```

Saída:

```
Out[1]= 0
```

Veredito: **verde** (saída exatamente `0`). O SymPy dá verde nesta derivação: vias concordam.

### Kelly — filha plantada errada `f = p - (1 - p) b` (vermelho)

Código:

```
Simplify[(p - (1 - p) b) - (f /. First@Solve[p b/(1 + b f) - (1 - p)/(1 - f) == 0, f])]
```

Saída:

```
Out[1]= ((-1 + b^2)*(-1 + p))/b
```

Veredito: **vermelho** (diferença não nula). O SymPy também dá vermelho: vias concordam no vermelho.

### Pareto — média (momento fechado)

Código:

```
Expectation[x, x \[Distributed] ParetoDistribution[L, alpha], Assumptions -> alpha > 1]
```

Saída:

```
Symbol::undefined: Warning: Global symbol L is undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= (alpha*L)/(-1 + alpha)
```

O aviso sobre `L` é inofensivo (parâmetro livre). A saída é a média fechada `alpha*L/(alpha-1)`; a prova
registrada é a forma com a diferença, abaixo.

### Pareto — média, forma com a diferença (a prova registrada; 05/10/2026)

Código:

```
FullSimplify[Expectation[x, x \[Distributed] ParetoDistribution[L, alpha], Assumptions -> alpha > 1 && L > 0] - (alpha L/(alpha - 1)), Assumptions -> alpha > 1 && L > 0]
```

Saída:

```
Symbol::undefined2: Warning: Global symbols "L, L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= 0
```

Veredito: **verde** (saída `0`; o aviso sobre `L` aparece mesmo com `L > 0` nas `Assumptions` e é
inofensivo).

### `e^x` contra `\log` com `e` símbolo comum — falso vermelho conhecido (05/10/2026; histórico)

Mãe `y = e^{x}`, filha `x = \log y`, símbolo `x`.

Código:

```
Simplify[(Log[y]) - (x /. First@Solve[y - (e^x) == 0, x])]
```

Saída:

```
Solve::ifun: Inverse functions are being used by Solve, so some solutions may not be found; use Reduce for complete solution information.
General::messages: Messages were generated which may indicate errors.

Out[1]= ((-1 + Log[e])*Log[y])/Log[e]
```

Diferença não nula: vermelho, concordante com o SymPy, e falso (ver "Falso vermelho conhecido"). Por causa
do `Solve::ifun`, esta saída não é registrada como está: o agente roda a forma de todos os ramos e registra
aquela.

### `φ_K/K` de Pareto contra a própria fonte — SCFT#248 e SCFT#268 (equação vermelha; 05/10/2026)

SCFT#248 `\lim_{K\to\infty} \phi_K/K = \frac{\alpha}{1 - \alpha}` (tópico "10.2.4 Test 2: Excess
Conditional Expectation") e SCFT#268 `\frac{p^*}{p} = \frac{\alpha}{1 - \alpha}` (tópico "11.2.3
Conflations") parseiam (P1 verde), mas a própria fonte (Definição 10.1 e eq. 11.7 do SCFT) dá, para a cauda
de Pareto, `E[X | X > K]/K = α/(α−1)`. O código calcula essa razão pela distribuição e subtrai o lado
direito do candidato.

Código:

```
FullSimplify[Expectation[x \[Conditioned] x > K, x \[Distributed] ParetoDistribution[L, alpha], Assumptions -> alpha > 1 && K > L > 0]/K - (alpha/(1 - alpha)), Assumptions -> alpha > 1 && K > L > 0]
```

Saída:

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= (2*alpha)/(-1 + alpha)
```

Veredito: **vermelho** (diferença não nula: o candidato diz `α/(1−α)`, a fonte dá `α/(α−1)`). Registrado
com `--prova equacao --equacao Statistical_Consequences_of_Fat_Tails.pdf.md#248 --veredito vermelho` (e o
mesmo para `#268`), a equação fica em staging com essa saída na pendência.

Conferência do lado da fonte (o mesmo código com `α/(α−1)` no lugar do lado direito):

```
FullSimplify[Expectation[x \[Conditioned] x > K, x \[Distributed] ParetoDistribution[L, alpha], Assumptions -> alpha > 1 && K > L > 0]/K - (alpha/(alpha - 1)), Assumptions -> alpha > 1 && K > L > 0]
```

```
Symbol::undefined2: Warning: Global symbols "L, L, L" are undefined.
General::messages: Messages were generated which may indicate errors.

Out[1]= 0
```
