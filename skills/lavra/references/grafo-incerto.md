# Grafo do Incerto — modelo, gate de aprovação e Cypher canônico (dono único)

Esta reference é **dona única** do modelo do grafo do Incerto: rótulos, chaves, propriedades, relações,
o que cada escritor grava e o Cypher canônico de cada `MERGE`. Dois scripts escrevem no grafo, e só eles:
`skills/lavra/scripts/ingerir_trechos.py` (`:Trecho`, `:Documento`, `PERTENCE_A`) e
`skills/lavra/scripts/aprovar_onda.py` (todo o resto, com o gate do fiscal). Quem lê (estação `taleb`,
MCP `consulta_incerto`) filtra por `corpus` e, para afirmar `[corpus]`, por `status = 'aprovado'`.

## Regras de todo nó e toda aresta

- **`corpus`**: a partição. `'incerto'` no AuraDB; `'incerto-teste'` nos testes (`--corpus`). Toda chave de
  `MERGE` começa por `corpus`, e toda aresta escrita leva `corpus` como propriedade.
- **`status`**: `'aprovado'` ou `'staging'`. Só `aprovar_onda.py` grava `'aprovado'`, e só para o que passou
  no gate abaixo. O que não passou é gravado assim mesmo, com `status: 'staging'` e `pendencias` (lista de
  textos: o que falta), para que o especialista possa citá-lo como `[staging]` — nunca como `[corpus]`.
- **`fonte`**: **uma propriedade texto** com o JSON canônico de `{documento, topico}`
  (`json.dumps(..., sort_keys=True, ensure_ascii=False)`), ex.: `{"documento": "Kelly.pdf.md", "topico":
  "Aposta binária"}`. O Neo4j não guarda mapa como propriedade, e uma propriedade só deixa a regra
  verificável numa consulta: `MATCH (n {corpus: 'incerto'}) WHERE n.fonte IS NULL RETURN count(n)` tem de
  dar 0 (idem para arestas curadas). `documento` e `topico` são os de `conferidos/<onda>/` (o mesmo
  `topico` que o recorte e a extração calculam). `:Documento` cita a si mesmo, com `topico: null`.
- **Arestas derivadas** (`DEFINE`, `MENCIONA`) levam, além disso, `origem: 'derivada'` e `script` (o nome
  do script que as calculou); curadas não levam `origem`.
- Propriedade composta (`momento_fechado`, `substituicao`) é gravada como JSON canônico em texto, pelo
  mesmo motivo de `fonte`.

**Exceção declarada — camada de evidência.** `:Trecho` e `PERTENCE_A` (de `ingerir_trechos.py`) não levam
`status` nem `fonte`: o trecho É a fonte (`documento`, `topico`, `parte` são a chave dele), e ele entra
pelo portão do PO dos `conferidos/`, não pelo fiscal. `:Documento` é criado pela ingestão só com
`{corpus, nome}`; `aprovar_onda.py` faz `MERGE` na mesma chave e completa `status` e `fonte`.

## Nós

| Rótulo | Chave do `MERGE` | Propriedades | Escritor |
|---|---|---|---|
| `:Documento` | `{corpus, nome}` | `status`, `fonte` (`{"documento": nome, "topico": null}`) | ingestão (chave); aprovação (`status`, `fonte`) |
| `:Trecho` | `{corpus, documento, topico, parte}` | `texto` (verbatim), `onda`, `ordem`, `embedding_gemini`, `junta`, `cabecalho` | ingestão |
| `:Equacao` | `{corpus, nome}` | `latex`, `sympy_srepr`, `forma` (`algebrica`\|`funcional`\|`perda`), `momento_fechado` (JSON ou ausente), `hipoteses`, `faixa_validade` (lista das condições declaradas em `validades-`), `onda`, `ordem`, `status`, `fonte`, `pendencias`, `aceites_po` | aprovação |
| `:Variavel` | `{corpus, nome}` | `simbolo`, `tipo` (`variavel`\|`parametro`\|`constante`), `status`, `fonte` | aprovação |
| `:Conceito` | `{corpus, nome}` | `tipo` (`fenomeno`\|`principio`\|`falacia`\|`regime`), `definicao`, `sinonimos` (lista), `onda`, `status`, `fonte` | aprovação (decisão `conceito`) |
| `:Heuristica` | `{corpus, nome}` | `enunciado`, `condicao`, `onda`, `status`, `fonte` | aprovação (decisão `heuristica`) |
| `:Metodo` | `{corpus, nome}` | `tipo` (`estimador`\|`diagnostico`\|`alocacao`), `status`, `fonte` | reservado — sem escritor na 0.1.0 |

- `:Equacao.nome` é o do candidato (`<documento>#<ordem>`); `sympy_srepr` é o `srepr` da extração.
  `hipoteses` (hipóteses em texto) e `:Variavel.tipo` não têm decisão na 0.1.0 e ficam ausentes.
- `:Variavel.nome` é o nome semântico (o símbolo até o PO renomear, decisão `renomear_variavel`); duas
  equações que dão o mesmo nome a uma variável usam o mesmo nó. `simbolo` é o primeiro símbolo (ordem de
  bytes) com que a onda a viu; os símbolos de cada equação ficam em `USA.simbolos`. `fonte` é a do
  primeiro uso gravado (de preferência por equação aprovada). O `status` é recalculado no fim de cada
  aprovação: `'aprovado'` se alguma `:Equacao` aprovada a `USA` por aresta aprovada, em qualquer onda.
  Variável que nenhuma equação usa mais (renomeada) é apagada.
- `:Conceito` e `:Heuristica` vêm de decisão do PO, que é a autoridade: entram `'aprovado'`.

## Relações

| Relação | De → para | Chave do `MERGE` | Propriedades | Gate / origem |
|---|---|---|---|---|
| `PERTENCE_A` | `:Trecho` → `:Documento` | par | — | ingestão (estrutural) |
| `USA` | `:Equacao` → `:Variavel` | par + `corpus` | `papel` (`definida`: o símbolo é o lado esquerdo `Equality(Symbol(...), …)` do `srepr`; senão `entrada`), `simbolos`, `status`, `fonte` | status da equação |
| `DEFINIDA_POR` | `:Variavel` → `:Equacao` | par + `corpus` | `status`, `fonte` | quando `USA.papel = 'definida'`; status da equação |
| `DERIVA_DE` | filha → mãe (`:Equacao`) | par + `corpus` | `passo`, `simbolo` (o `alvo` isolado), `substituicao` (JSON), `verificado_por` (só as vias cuja linha deu verde: `"sympy@1.14.0"` pela P2, `"wolfram"` pela P4; vazio em staging), `status`, `fonte` (a da filha), `pendencias`, `aceites_po` (nomes das provas que passaram por aceite do PO — `aceitar_indeterminado` —, nunca em `verificado_por`) | P2 **e** P4 + as duas pontas aprovadas |
| `VALIDA_SOB` | `:Equacao` → `:Variavel` | par + `corpus` + `condicao` | `condicao` (relacional sobre os símbolos), `status`, `fonte` (a da equação), `pendencias`, `aceites_po` | P3 + equação aprovada |
| `EXPRESSA` | `:Equacao` → `:Conceito` | par + `corpus` | `status`, `fonte` | reservado — sem escritor na 0.1.0 |
| `SUSTENTA` | `:Heuristica` → `:Conceito` \| `:Equacao` | par + `corpus` | `status` (o do alvo), `fonte` (a da heurística) | decisão `heuristica` |
| `APLICA` | `:Metodo` → `:Equacao` | par + `corpus` | `ordem`, `status`, `fonte` | reservado — sem escritor na 0.1.0 |
| `MEDE` | `:Metodo` → `:Conceito` | par + `corpus` | `status`, `fonte` | reservado — sem escritor na 0.1.0 |
| `DEFINE` | `:Documento` → `:Conceito` | par + `corpus` + `topico` | `topico`, `origem: 'derivada'`, `script`, `status`, `fonte` | derivada — sem escritor na 0.1.0 |
| `MENCIONA` | `:Trecho` → `:Conceito` | par + `corpus` | `ocorrencias`, `origem: 'derivada'`, `script`, `status`, `fonte` | derivada **por nome, nunca por símbolo** — sem escritor na 0.1.0 |
| `DIVERGE_DE` | `:Equacao`\|`:Conceito` → mesmo rótulo | par + `corpus` | `nota`, `decisao_po`, `status`, `fonte` | reservado — sem escritor na 0.1.0 |

`VALIDA_SOB` aponta as variáveis cujos símbolos a condição cita (tokens `NAME` da condição que são
símbolos da equação, traduzidos pelo nome da variável); uma condição sobre `alpha` e `L` gera duas
arestas com a mesma `condicao`. Condição que não cita variável da equação não gera aresta (aviso no plano).

Reaprovar a onda **substitui** as arestas que saem das equações dela (`USA`, `VALIDA_SOB`, `DERIVA_DE`,
`DEFINIDA_POR` que chega nelas) e os `SUSTENTA` das heurísticas dela, e **rebaixa** — nunca apaga — todo
nó `{corpus, onda}` da onda (`:Equacao`, `:Conceito`, `:Heuristica`) que o plano atual não grava (equação
que saiu de `equacoes-`, conceito ou heurística cuja decisão saiu de `decisoes-`): `status: 'staging'`,
`pendencias: ["fora da rodada atual"]`. Nada de uma rodada anterior sobrevive como `aprovado`. Só a
variável órfã é apagada.

**A `onda` do nó é confiável porque é conferida.** `carregar_onda` recusa, antes de abrir o banco, todo
candidato cuja `onda` difira de `--onda`. E, como `:Equacao` é chaveada por `{corpus, nome}` (sem a onda),
antes de qualquer escrita a aprovação consulta as equações do plano já no banco e **recusa sem gravar
nada** se alguma estiver em outra onda, nomeando nome e onda: o PO resolve renomeando na rodada.

## Gate do fiscal (`aprovar_onda.decidir`, função pura)

Entradas: `equacoes-<onda>.jsonl`, `derivacoes-`, `validades-`, `fiscal-<onda>.jsonl` (linhas do
`fiscal.py`, com as chaves estruturadas) e `decisoes-<onda>.jsonl`. **Todas** as linhas do fiscal de um
item têm de passar; uma linha passa se é `verde`, ou `indeterminado` com aceite exato do PO. `vermelho`
nunca passa, com ou sem decisão. Item sem linha do fiscal fica em staging ("sem prova").

| Item | Linhas que contam (todas) | Linha que tem de existir |
|---|---|---|
| `:Equacao` | P1 `{equacao}`; toda P3 `{equacao, condicao}` sobre ela; toda P4 de momento `{equacao}` sobre ela | P1; uma P3 por condição de `validades-`; P4 de momento se tem `momento_fechado` **ou** se o `srepr` aplica `E`/`Var` |
| `DERIVA_DE` | P2 `{mae, filha, simbolo, substituicao}` da linha de derivação; P4 `{mae, filha}` | as duas; e mãe e filha aprovadas |
| `VALIDA_SOB` | P3 `{equacao, condicao}` | a P3; e a equação aprovada |

Equação cujo `srepr` aplica `Function('E')` ou `Function('Var')` (marcação explícita, `\mathbb{E}[X] = …`)
afirma um momento fechado: sem `momento_fechado` declarado, o fiscal dá P4 `indeterminado` "aplica E/Var sem
momento_fechado declarado" (`{equacao}`), e ela fica em staging até o PO declarar o momento (que a via
Wolfram prova) ou aceitar a linha. O plano impresso traz, ao lado de cada item, o LaTeX de origem e o
`srepr` das equações envolvidas.

Antes do gate, `aprovar_onda.py` refaz o fiscal (`fiscal.provas`) sobre os arquivos atuais e compara com
`fiscal-<onda>.jsonl`; se diferirem (candidato reextraído, derivação mudada, momento aplicado, prova
Wolfram nova), recusa: o fiscal está desatualizado.

## Decisões do PO (`decisoes-<onda>.jsonl`)

Uma decisão por linha. Todas são validadas antes de qualquer escrita; **tipo desconhecido, chave a mais ou
a menos, valor vazio ou repetição recusam a execução inteira**.

| `tipo` | Campos | Efeito |
|---|---|---|
| `renomear_variavel` | `equacao`, `simbolo`, `nome` | a variável daquele símbolo naquela equação passa a ser `:Variavel {nome}` |
| `conceito` | `nome`, `tipo_conceito` (`fenomeno`\|`principio`\|`falacia`\|`regime`), `definicao`, `sinonimos` (lista), `fonte` | `:Conceito` aprovado (`tipo` = `tipo_conceito`: o `tipo` da linha é o da decisão) |
| `heuristica` | `nome`, `enunciado`, `condicao`, `fonte`, `sustenta` (nomes de conceito decidido ou equação da onda) | `:Heuristica` aprovada e um `SUSTENTA` por nome, com o status do alvo |
| `aceitar_indeterminado` | `prova` + **exatamente** as chaves estruturadas da linha: P1 `equacao`; P2 `mae`, `filha`, `simbolo`, `substituicao`; P3 `equacao`, `condicao`; P4 `mae`, `filha` ou `equacao` | aquela linha `indeterminado` passa a passar; nada mais (sem curinga) |
| `momento_fechado` | `equacao`, `momento_fechado` (`{"media": "...", ...}`) | aplicado ao candidato por `--aplicar-momentos`, **antes do fiscal** |

Rito do momento fechado: decisão em `decisoes-` → `aprovar_onda.py --onda <onda> --aplicar-momentos`
(regrava `equacoes-<onda>.jsonl`, chaves ordenadas, `\n`) → `fiscal.py` → prova Wolfram do momento
(`references/fiscal.md`) → `fiscal.py` → `aprovar_onda.py`. Na aprovação, decisão de momento que não está
no candidato recusa a execução.

## CLI

```
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda>                  # imprime o plano; nada gravado
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda> --executar       # grava
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda> --aplicar-momentos
    [--corpus incerto] [--raiz-esteira _esteira/incerto] [--database <db>]
```

Sem `--executar` o banco nem é aberto. Com ele, a ordem é: recusar colisão de nome com outra onda →
rebaixar os nós da onda fora do plano → limpar as arestas da onda → nós → arestas → variáveis órfãs →
status das variáveis.

## Cypher canônico

Todo `MERGE` vai em lote (`UNWIND $linhas`) por `nucleo.query_com_retentativa`, com valores só em
parâmetros. As constantes de `aprovar_onda.py` são estas.

Ingestão (`ingerir_trechos.py`):

```cypher
UNWIND $linhas AS l
MERGE (d:Documento {corpus: $corpus, nome: l.documento})
MERGE (t:Trecho {corpus: $corpus, documento: l.documento, topico: l.topico, parte: l.parte})
SET t.texto = l.texto, t.onda = l.onda, t.ordem = l.ordem, t.embedding_gemini = l.embedding,
    t.junta = l.junta, t.cabecalho = l.cabecalho
MERGE (t)-[:PERTENCE_A]->(d)
```

Aprovação — colisão com outra onda (recusa se devolver linha) e rebaixamento:

```cypher
MATCH (e:Equacao {corpus: $corpus}) WHERE e.nome IN $nomes AND e.onda <> $onda
RETURN e.nome, e.onda ORDER BY e.nome

MATCH (n {corpus: $corpus, onda: $onda}) WHERE n:Equacao OR n:Conceito OR n:Heuristica
RETURN [r IN labels(n) WHERE r IN ['Equacao', 'Conceito', 'Heuristica']][0], n.nome ORDER BY n.nome
// o que não está no plano (aprovar_onda.a_rebaixar) vai em $linhas [{rotulo, nome}]:
UNWIND $linhas AS l
MATCH (n {corpus: $corpus, onda: $onda, nome: l.nome})
WHERE l.rotulo IN labels(n)
SET n.status = 'staging', n.pendencias = [$pendencia]          // "fora da rodada atual"
```

Aprovação — limpeza das arestas da onda (três comandos):

```cypher
MATCH (e:Equacao {corpus: $corpus, onda: $onda})-[r:USA|VALIDA_SOB|DERIVA_DE]->() DELETE r
MATCH ()-[r:DEFINIDA_POR]->(e:Equacao {corpus: $corpus, onda: $onda}) DELETE r
MATCH (h:Heuristica {corpus: $corpus, onda: $onda})-[r:SUSTENTA]->() DELETE r
```

Nós:

```cypher
UNWIND $linhas AS l
MERGE (d:Documento {corpus: $corpus, nome: l.nome})
SET d.status = l.status, d.fonte = l.fonte

UNWIND $linhas AS l
MERGE (e:Equacao {corpus: $corpus, nome: l.nome})
SET e.latex = l.latex, e.sympy_srepr = l.sympy_srepr, e.forma = l.forma, e.momento_fechado = l.momento_fechado,
    e.hipoteses = l.hipoteses, e.faixa_validade = l.faixa_validade, e.onda = l.onda, e.ordem = l.ordem,
    e.status = l.status, e.fonte = l.fonte, e.pendencias = l.pendencias, e.aceites_po = l.aceites_po

UNWIND $linhas AS l
MERGE (v:Variavel {corpus: $corpus, nome: l.nome})
ON CREATE SET v.simbolo = l.simbolo, v.fonte = l.fonte, v.status = l.status

UNWIND $linhas AS l
MERGE (c:Conceito {corpus: $corpus, nome: l.nome})
SET c.tipo = l.tipo, c.definicao = l.definicao, c.sinonimos = l.sinonimos, c.onda = $onda, c.status = l.status,
    c.fonte = l.fonte

UNWIND $linhas AS l
MERGE (h:Heuristica {corpus: $corpus, nome: l.nome})
SET h.enunciado = l.enunciado, h.condicao = l.condicao, h.onda = $onda, h.status = l.status, h.fonte = l.fonte
```

Arestas:

```cypher
UNWIND $linhas AS l
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MERGE (e)-[r:USA {corpus: $corpus}]->(v)
SET r.papel = l.papel, r.simbolos = l.simbolos, r.status = l.status, r.fonte = l.fonte

UNWIND $linhas AS l
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MERGE (v)-[r:DEFINIDA_POR {corpus: $corpus}]->(e)
SET r.status = l.status, r.fonte = l.fonte

UNWIND $linhas AS l
MATCH (f:Equacao {corpus: $corpus, nome: l.filha})
MATCH (m:Equacao {corpus: $corpus, nome: l.mae})
MERGE (f)-[r:DERIVA_DE {corpus: $corpus}]->(m)
SET r.passo = l.passo, r.simbolo = l.simbolo, r.substituicao = l.substituicao, r.verificado_por = l.verificado_por,
    r.status = l.status, r.fonte = l.fonte, r.pendencias = l.pendencias, r.aceites_po = l.aceites_po

UNWIND $linhas AS l
MATCH (e:Equacao {corpus: $corpus, nome: l.equacao})
MATCH (v:Variavel {corpus: $corpus, nome: l.variavel})
MERGE (e)-[r:VALIDA_SOB {corpus: $corpus, condicao: l.condicao}]->(v)
SET r.status = l.status, r.fonte = l.fonte, r.pendencias = l.pendencias, r.aceites_po = l.aceites_po

UNWIND $linhas AS l
MATCH (h:Heuristica {corpus: $corpus, nome: l.heuristica})
MATCH (x:Conceito {corpus: $corpus, nome: l.alvo})          // (x:Equacao …) no lote das equações
MERGE (h)-[r:SUSTENTA {corpus: $corpus}]->(x)
SET r.status = l.status, r.fonte = l.fonte
```

Variáveis, no fim:

```cypher
MATCH (v:Variavel {corpus: $corpus})
WHERE NOT EXISTS { MATCH (:Equacao)-[:USA]->(v) }
DETACH DELETE v

MATCH (v:Variavel {corpus: $corpus})
SET v.status = CASE WHEN EXISTS { MATCH (:Equacao {corpus: $corpus, status: 'aprovado'})
                                  -[:USA {corpus: $corpus, status: 'aprovado'}]->(v) }
                    THEN 'aprovado' ELSE 'staging' END
```

Conferência (o que os testes do CI rodam na partição `incerto-teste`):

```cypher
MATCH (n {corpus: $corpus}) WHERE n.fonte IS NULL RETURN count(n)            // 0 (fora da camada de evidência)
MATCH ()-[r {corpus: $corpus}]->() WHERE r.fonte IS NULL RETURN count(r)     // 0
```
