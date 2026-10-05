# Fiscal de duas vias — protocolo da prova Wolfram (dono único)

Esta reference é **dona única** do protocolo da segunda via do fiscal: como o agente monta o código
Wolfram a partir do candidato, como roda, o que conta como verde e como registra. A primeira via (SymPy,
provas P1–P3) e a conferência entre as vias (P4) são do `skills/lavra/scripts/fiscal.py`; o registro é do
`skills/lavra/scripts/registrar_prova.py`. Os formatos de linha descritos aqui são os que esses dois
scripts validam.

**Regra.** `DERIVA_DE` e `:Equacao` com momento fechado só saem de staging com a prova SymPy verde **e**
a prova Wolfram verde e concordante. Divergência entre as vias é vermelho, com as duas saídas no relato.
**Nenhum script chama o Wolfram**: quem roda é o agente, pelo MCP do Wolfram
(`WolframLanguageEvaluator`), e o script só registra e confere.

## O que exige prova Wolfram

| O quê | De onde vem | Chave da prova | Linha em `provas-<onda>.jsonl` |
|---|---|---|---|
| derivação | toda linha P2 do `fiscal-<onda>.jsonl` (uma por linha de `derivacoes-<onda>.jsonl`) | `mae` + `filha` | `{"prova": "P2", "via": "wolfram", "mae", "filha", "codigo", "saida", "veredito", "impressao"}` |
| momento fechado | todo candidato de `equacoes-<onda>.jsonl` com `momento_fechado` não vazio (dict, ex.: `{"media": "alpha*L/(alpha-1)"}`) | `equacao` (o `nome` do candidato) | `{"prova": "momento", "via": "wolfram", "equacao", "codigo", "saida", "veredito", "impressao"}` |

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
  `{"mae_srepr", "filha_srepr", "simbolo", "substituicao"}` (derivação) ou
  `{"equacao_srepr", "momento_fechado"}` (momento). O registrador a calcula de `equacoes-<onda>.jsonl` e
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

   Chave já registrada é recusada; refazer uma prova exige `--substituir` (a linha antiga sai do arquivo).
   **O verde é conferido**: o registrador lê a última linha `Out[n]=` da saída e só aceita `--veredito
   verde` se o que vem depois dela for exatamente `0` ou uma lista só de `0` (`{0}`, `{0, 0}`); saída sem
   `Out[n]=`, ou com qualquer outro resultado, recusa o verde sem gravar nada. `vermelho` e
   `indeterminado` são registrados como o agente os decidiu.
7. `fiscal.py --onda <onda>` de novo: a P4 junta as provas às linhas P2 e aos momentos e dá o veredito
   final da segunda via.

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
| `Abs(x)` | `Abs[x]` |

- **`pi` e `e` são símbolos comuns no corpus** (decisão vigente até o PO decidir): o código usa `pi` e `e`
  minúsculos, nunca `Pi` nem `E`. Trocar pela constante numa via só cria divergência que não existe na
  outra — e esconde a pendência de decisão.
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

## Falso vermelho conhecido: `e^x` contra `\log`

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

### `e^x` contra `\log` com `e` símbolo comum — falso vermelho conhecido (05/10/2026)

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
