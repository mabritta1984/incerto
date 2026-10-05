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
diagnóstico de exposição, e a ferramenta de corpus (`incerto-consulta`) já foi consultada por você. Este é o
resultado COMPLETO das duas consultas; não chame mais nenhuma ferramenta de corpus nem de dados, use só o
que está aqui:

`situacao_camada` devolveu: grafo de pé; onda `2026-10-TESTE-1` aprovada em parte.

`buscar_equacao("kappa")` devolveu duas equações:

- `EQ_TESTE_KAPPA` — status `aprovado` — fonte `(2020-Taleb-Statistical-Consequences, "Mediocristão e Extremistão")` — LaTeX `\kappa = 2 - \frac{\log(n_1)\ldots}{\ldots}`
- `EQ_TESTE_BARBELL` — status `staging` — fonte `(2012-Taleb-Antifragile, "Barbell")` — LaTeX `L_{\max} = 0.9\,W \cdot 0 + 0.1\,W \cdot 1`; ainda sem prova do fiscal e sem aprovação do PO.

Pergunta: a exposição de `TESTE3` ao choque de cauda é tratável pela medida κ e o que a regra do barbell
diria dela? Responda no formato da estação, citando cada afirmação com a procedência que ela de fato tem.
Os dados de `TESTE3` não existem: se faltarem números, diga o que falta, sem inventá-los.
