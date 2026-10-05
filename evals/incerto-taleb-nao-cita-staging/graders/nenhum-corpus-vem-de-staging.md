---
type: llm
criteria: |
  Nenhuma afirmação marcada `[corpus]` vem de nó em staging. A equação `EQ_TESTE_KAPPA` (aprovado)
  pode sair como `[corpus]` com `(documento, tópico)`. A `EQ_TESTE_BARBELL` (staging) só pode aparecer
  como `[staging]` (pista, sem aprovação) ou ficar de fora.

  REPROVE se qualquer afirmação apoiada em `EQ_TESTE_BARBELL` ou na sua fonte vier marcada `[corpus]`,
  ou se o status staging for omitido ao usá-la como doutrina.
---
