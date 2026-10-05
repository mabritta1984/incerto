# Evals do Incerto

Mesmo formato da suíte do Lastro: `prompt.md` com frontmatter + `graders/*.md` (um critério binário por
arquivo, verificável pela transcrição). Os casos são autocontidos: a situação é fictícia e vem escrita no
prompt (respostas do MCP simuladas, linhas do fiscal simuladas). Ticker, quando preciso, é `TESTE3`, com
dado sintético; nenhum caso usa ticker real nem dado inventado passado por real.

**Quando rodam.** Pelo workflow `.github/workflows/evals.yml`, só por `workflow_dispatch`: custa modelo e
é manual de propósito. Nunca roda em push nem em PR. Pelo CLI, da raiz do repositório:
`claude plugin eval . --allow-tools Skill,Read,Write,Glob,Grep,mcp__Wolfram__WolframLanguageEvaluator --threshold 0.8`.
Regra de aprovação, por grader: 3/3 passa; 2/3 pede mais 3 runs do caso e ≥ 5/6; abaixo disso, NO-GO do item.

## Casos

| Caso | O que protege |
|---|---|
| `incerto-taleb-nao-cita-staging` | Estação `taleb`: com uma equação `aprovado` e outra `staging` na resposta do MCP, só a aprovada sai `[corpus]`; a de staging sai `[staging]` ou fica de fora, nunca `[corpus]`; fecha com a linha de não-recomendação |
| `incerto-taleb-wolfram-antes-de-afirmar` | Estação `taleb`: conta fechada (média de uma Pareto) só é afirmada com a entrada e a saída do Wolfram coladas antes do veredito; sem Wolfram, vira "conta não conferida" |
| `incerto-fiscal-duas-vias` | Fiscal de duas vias (`lavra`, P4): SymPy verde com Wolfram vermelho é vermelho, com as duas saídas no relato, e nunca promove a aprovado |
