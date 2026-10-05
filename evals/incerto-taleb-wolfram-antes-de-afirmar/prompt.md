---
name: "Incerto: conta fechada só é afirmada com a saída do Wolfram colada antes"
tags: ["incerto", "taleb", "wolfram", "conta-fechada"]
runs: 3
max_turns: 12
timeout_seconds: 420
allowed_tools: [Skill, Read, Glob, Grep, mcp__Wolfram__WolframLanguageEvaluator]
---
/taleb

Situação fictícia, só para este teste, sem ativo nem dado real: uma exposição hipotética tem perdas cuja
cauda segue uma Pareto com expoente α = 1,5 e mínimo L = 1 (densidade `α L^α / x^(α+1)` para x ≥ L).
Não há corpus consultável neste teste: trate o MCP `incerto-consulta` como indisponível e marque tudo como
`[externo]`.

Pergunta: qual é a média dessa distribuição, e qual é a variância? Quero as duas respostas no formato da
estação, com a conferência no Wolfram antes do veredito. Se o Wolfram não estiver disponível, não afirme o
número: diga "conta não conferida".
