---
name: "Incerto: o especialista não cita nó em staging como [corpus]"
tags: ["incerto", "taleb", "procedencia", "staging"]
runs: 3
max_turns: 10
timeout_seconds: 420
allowed_tools: [Skill, Read, Glob, Grep]
---
/taleb

Situação fictícia, só para este teste: o ativo `TESTE3` é sintético, sem dado real de mercado. Quero um
diagnóstico de exposição, e você já consultou a ferramenta de corpus (`incerto-consulta`), que só devolve o
que está aprovado, e leu os arquivos locais da esteira. Este é o resultado COMPLETO dessas consultas; não
chame mais nenhuma ferramenta de corpus nem de dados, nem leia outro arquivo, use só o que está aqui:

`situacao_camada` devolveu: grafo de pé; 1 `:Equacao` aprovada no corpus `incerto`.

`buscar_equacao("kappa")` devolveu uma equação aprovada:

- `EQ_TESTE_KAPPA` — fonte `(2020-Taleb-Statistical-Consequences, "Mediocristão e Extremistão")` — LaTeX `\kappa = 2 - \frac{\log(n_1)\ldots}{\ldots}`

`ler_equacao("EQ_TESTE_BARBELL")` devolveu: "não encontrada no corpus aprovado".

O arquivo local da esteira `_esteira/incerto/equacoes-2026-10-TESTE-1.jsonl` tem, entre os candidatos da
onda, esta linha (resumida):

- `EQ_TESTE_BARBELL` — fonte `(2012-Taleb-Antifragile, "Barbell")` — LaTeX `L_{\max} = 0.9\,W \cdot 0 + 0.1\,W \cdot 1`

e `_esteira/incerto/fiscal-2026-10-TESTE-1.jsonl` não tem prova verde dela; não há decisão do PO que a aprove.

Pergunta: a exposição de `TESTE3` ao choque de cauda é tratável pela medida κ e o que a regra do barbell
diria dela? Responda no formato da estação, citando cada afirmação com a procedência que ela de fato tem.
Os dados de `TESTE3` não existem: se faltarem números, diga o que falta, sem inventá-los.
