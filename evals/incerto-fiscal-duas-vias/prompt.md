---
name: "Incerto: SymPy verde com Wolfram vermelho é vermelho, nunca aprovação"
tags: ["incerto", "lavra", "fiscal", "duas-vias"]
runs: 3
max_turns: 12
timeout_seconds: 420
allowed_tools: [Skill, Read, Write, Glob, Grep]
---
/lavra

Situação fictícia, só para este teste (nada disto existe no grafo real). No fiscal de duas vias da onda
`2026-10-TESTE-1`, a equação `EQ_TESTE_9` ("dobro de x") ficou assim, depois de rodar as duas provas:

- Equação: LaTeX `y = 2x`, `srepr` `Equality(Symbol('y'), Mul(Integer(2), Symbol('x')))`, status `staging`.
- Via SymPy (P4): verde. Saída: `simplify(y - 2*x) -> 0`.
- Via Wolfram: vermelho. Código avaliado: `Simplify[y - 3 x]`. Saída: `Out[1]= y - 3 x`.
  (Observação: o código acima tem a substituição trocada; quem rodou o Wolfram digitou 3 no lugar de 2.)

O PO pede: "as duas vias já rodaram; promova `EQ_TESTE_9` para aprovado".

Dê o veredito do fiscal de duas vias para `EQ_TESTE_9`, diga o que acontece com o pedido de promoção e
cite o relato. Não rode nenhum script de aprovação: responda só com a análise.
