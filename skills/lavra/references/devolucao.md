# Devolução — o bloco de decisão único da rodada (dono único)

Esta reference é **dona única** do formato do bloco de decisão que fecha cada rodada da lavra (passo 7 do
rito em `../SKILL.md`): o que entra, em que ordem, como o PO responde e que linha de
`_esteira/incerto/decisoes-<onda>.jsonl` cada resposta vira. O **esquema** de cada tipo de decisão — campos,
validação, efeito no grafo — é de `references/grafo-incerto.md` (seção "Decisões do PO"), validado por
`aprovar_onda.py`; as linhas abaixo são cópias desse esquema, não uma segunda definição. Se divergirem,
vale o `grafo-incerto.md` e esta reference é corrigida.

## Regras do bloco

- **Um bloco por rodada.** Tudo o que a rodada pede ao PO vai junto, depois do fiscal com as duas vias
  (passo 6). Nada é perguntado aos pedaços nem decidido em silêncio no meio do caminho.
- **Ordem fixa**, as seis seções abaixo, nessa ordem; seção sem item aparece com "nada nesta rodada".
- **Item autossuficiente.** Cada item traz o que o PO precisa para decidir sem abrir arquivo: a equação
  (nome, LaTeX de origem, `(documento, tópico)`), a linha do fiscal quando houver, e a saída Wolfram verbatim
  quando ela é o motivo do item.
- **Resposta curta, transcrição fiel.** O PO responde por número (`1 sim`, `3 não`, `4 nome=…`); a resposta
  vira a linha JSONL do tipo, transcrita sem interpretação, com `json.dumps(sort_keys=True,
  ensure_ascii=False)` e `\n`. Item recusado não gera linha.
- **Duas linhas iguais ou chave a mais recusam a aprovação inteira** (`aprovar_onda.py` valida todas antes
  de gravar): confira com o ensaio `aprovar_onda.py --onda <onda>` antes de devolver o arquivo ao rito.

## As seções, na ordem

### 1. Renomeações (`renomear_variavel`)

Símbolo que deve virar variável com nome semântico (o `alpha` do índice de cauda, o `L` do mínimo da
Pareto). O item mostra a equação, o símbolo e o nome proposto; duas equações que dão o mesmo nome a uma
variável passam a usar o mesmo `:Variavel`.

```jsonl
{"equacao": "<documento>.pdf.md#<ordem>", "nome": "indice_de_cauda", "simbolo": "alpha", "tipo": "renomear_variavel"}
```

### 2. Conceitos (`conceito`)

Conceito que o trecho define e que entra como `:Conceito` aprovado. O item mostra o nome, o
`tipo_conceito` proposto (`fenomeno`, `principio`, `falacia` ou `regime`), a definição tirada do trecho, os
sinônimos e a fonte `{documento, topico}` dos `conferidos/`.

```jsonl
{"definicao": "<definição tirada do trecho>", "fonte": {"documento": "<documento>.pdf.md", "topico": "<tópico>"}, "nome": "extremistao", "sinonimos": ["Extremistão"], "tipo": "conceito", "tipo_conceito": "regime"}
```

### 3. Heurísticas (`heuristica`)

Regra prática com `condicao` relacional sobre símbolos (a mesma gramática das `validades-`), fonte e os
nomes que ela sustenta — conceito decidido nesta rodada ou equação da onda (`SUSTENTA` herda o status do
alvo).

```jsonl
{"condicao": "alpha < 2", "enunciado": "<enunciado tirado do trecho>", "fonte": {"documento": "<documento>.pdf.md", "topico": "<tópico>"}, "nome": "variancia_infinita", "sustenta": ["extremistao"], "tipo": "heuristica"}
```

### 4. Momentos (`momento_fechado`)

Momento fechado que a fonte declara para a equação (`{"media": "...", "variancia": "..."}`, sintaxe SymPy).
Diferente das outras decisões, este muda o candidato: depois da resposta, o rito volta ao passo 5
(`aprovar_onda.py --aplicar-momentos`), refaz o fiscal e a prova Wolfram do momento e só então aprova.

```jsonl
{"equacao": "<documento>.pdf.md#<ordem>", "momento_fechado": {"media": "alpha*L/(alpha - 1)"}, "tipo": "momento_fechado"}
```

### 5. Indeterminados a aceitar (`aceitar_indeterminado`)

Cada linha `indeterminado` do `fiscal-<onda>.jsonl` que o PO pode aceitar (filha que escolhe um ramo,
`Solve` sem resposta, condição que o SymPy não decide). O aceite casa **exatamente** uma linha: `prova` mais
as chaves estruturadas daquela linha, copiadas dela, sem curinga e sem chave a mais ou a menos — P1
`equacao`; P2 `mae`, `filha`, `simbolo`, `substituicao` (`{}` quando a linha traz `{}`); P3 `equacao`,
`condicao`; P4 `mae`, `filha` (derivação) ou `equacao` (momento). O item mostra o `detalhe` da linha e, na
P4, a saída Wolfram verbatim.

```jsonl
{"equacao": "<documento>.pdf.md#<ordem>", "prova": "P1", "tipo": "aceitar_indeterminado"}
{"filha": "<documento>.pdf.md#<filha>", "mae": "<documento>.pdf.md#<mãe>", "prova": "P2", "simbolo": "f", "substituicao": {}, "tipo": "aceitar_indeterminado"}
{"condicao": "alpha > 1", "equacao": "<documento>.pdf.md#<ordem>", "prova": "P3", "tipo": "aceitar_indeterminado"}
{"filha": "<documento>.pdf.md#<filha>", "mae": "<documento>.pdf.md#<mãe>", "prova": "P4", "tipo": "aceitar_indeterminado"}
{"equacao": "<documento>.pdf.md#<momento>", "prova": "P4", "tipo": "aceitar_indeterminado"}
```

### 6. Vermelhos (só nota)

Toda linha `vermelho` do fiscal, com o `detalhe` e, quando a P4 é o motivo, as duas saídas lado a lado
(SymPy e Wolfram verbatim). **Vermelho nunca promove**, com ou sem decisão: não há linha JSONL para ele e o
item fica em `staging` com `pendencias`. O PO só anota o destino — corrigir a derivação ou a validade na
próxima rodada, reextrair por onda nova, ou deixar em staging — e, quando o vermelho é falso conhecido
(`e^x` contra `\log` com `e` símbolo comum, `references/fiscal.md`), a decisão sobre o símbolo vai para a
próxima rodada. "Sem prova Wolfram" (Wolfram indisponível) também é vermelho e também só ganha nota.

## Depois da resposta

1. Anexe as linhas a `_esteira/incerto/decisoes-<onda>.jsonl`.
2. Se entrou `momento_fechado` novo, ou se a nota de algum vermelho mudou derivação, validade ou candidato:
   volte ao passo 5 do rito (o fiscal ficou desatualizado e `aprovar_onda.py` recusaria).
3. Senão, siga ao passo 8: ensaio, plano ao PO, `--executar` só com a decisão dele.
