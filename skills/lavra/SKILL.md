---
name: lavra
description: >
  Rito por onda do Incerto: leva os PDFs de uma fonte no bucket (originais/<fonte>/) até um corpus conferido, recortado, ingerido no Neo4j, extraído em equações, fiscalizado em duas vias (SymPy e Wolfram) e aprovado pelo PO — em oito passos na ordem, cada um com o comando exato e a condição de parada, e com a decisão do PO antes de todo passo que gasta modelo ou escreve no Aura. Use quando o PO pedir para "rodar uma onda", "converter os PDFs do Taleb", conferir ou aprovar uma onda do mineiro, recortar ou ingerir os conferidos, rodar a rodada do fiscal ou montar o bloco de decisão da rodada, ou quando aparecer o comando /lavra. Não converte PDF (isso é do mineiro), não define o modelo do grafo (grafo-incerto.md) nem o protocolo Wolfram (fiscal.md): conduz a ordem e as decisões.
metadata:
  version: "0.1.0-dev"
---

# Lavra — uma onda, do original ao aprovado

Você conduz uma **onda**: uma execução de conversão de um lote de originais (ex.: `2026-10-TALEB-1`, fonte
`TALEB`) até o grafo do Incerto. O trabalho é de ordem e de decisão, não de conteúdo: cada passo roda um
script que é dono do seu contrato, e esta estação só diz **em que ordem**, **o que confere antes de seguir**
e **onde o PO decide**. Nada aqui redefine o que os donos já definem:

- `references/extracao-nuvem.md` — layout do bucket, o que o `mineiro` grava, o portão do PO (dono único);
- `references/grafo-incerto.md` — modelo do grafo, gate do fiscal, tipos de decisão e seus campos (dono único);
- `references/fiscal.md` — protocolo da prova Wolfram: código, veredito, registro verbatim (dono único);
- `references/devolucao.md` — formato do bloco de decisão único da rodada (dono único).

Comunicação exclusivamente em português do Brasil. Os arquivos de trabalho da onda moram em
`_esteira/incerto/` (`trechos-`, `equacoes-`, `derivacoes-`, `validades-`, `fiscal-`, `provas-`,
`decisoes-<onda>.jsonl`); o corpus, em `gs://jazida-bucket` (montado em `<corpus>`, ex.: `/mnt/corpus`).

**Gasto e escrita são do PO.** Copiar originais, disparar a conversão (gasta modelo), ingerir (gasta Vertex e
escreve no Aura) e aprovar com `--executar` (escreve no Aura) só acontecem depois que o PO decidiu, num bloco
de decisão com o que vai custar ou ser gravado. Sem a decisão, o passo não roda — e não é simulado.

## Rito

### 1. Copiar os originais

Os PDFs da fonte entram em `originais/<fonte>/`, que é imutável e é o árbitro de tudo o que vem depois.
**Decisão do PO antes**: a onda que esses originais alimentam vai custar modelo, e o bloco leva a lista de
arquivos, a origem e o destino. A cópia **nunca move**: a pasta de origem fica como registro.

```
gcloud storage cp --no-clobber <origem>/<nome>.pdf gs://jazida-bucket/originais/<fonte>/
gcloud storage ls -l gs://jazida-bucket/originais/<fonte>/
```

**Pare se** algum arquivo da lista não aparece no `ls` de destino, ou se já existia em `originais/<fonte>/`
com outro conteúdo: `originais/` nunca é reescrito; correção é decisão do PO.

### 2. Disparar a conversão

O `mineiro` converte `originais/<fonte>/` em `extraidos/<onda>/` pelo workflow `.github/workflows/conversao.yml`
(`workflow_dispatch`, entradas `onda` e `origem`, padrão `TALEB`). **Decisão do PO antes**: disparar gasta
modelo; quem dispara é o PO, com o nome da onda, a fonte, o número de documentos e páginas e a estimativa
de tempo no bloco (a onda `2026-09-PSX-1` do Jazida, 43 artigos, levou 2,6 h de parede).

```
gh workflow run conversao.yml -f onda=<onda> -f origem=<fonte>
gh run watch
```

**Pare se** o run falhar ou passar do `timeout-minutes` do workflow: relate o log ao PO e não redispare
sem decisão dele. Nome de onda ou de fonte fora de `^[A-Za-z0-9][A-Za-z0-9._-]*$` (ou com `..`) é recusado
pelo próprio workflow.

### 3. Portão

Nada sai de `extraidos/<onda>/` sem o PO. Primeiro só ler e relatar:

```
python3 skills/lavra/scripts/conferir_onda.py --raiz <corpus> --onda <onda>
```

Entregue ao PO o relatório de fidelidade inteiro (resumo, por rota, equações e parseáveis, perdas
declaradas, veredito por documento) e as amostras dirigidas que ele pedir do `.md` contra o original. Com as
recusas decididas por ele:

```
python3 skills/lavra/scripts/conferir_onda.py --raiz <corpus> --onda <onda> --aprovar --recusar <nome>=<motivo>
```

(`--recusar` repetível, um por documento apto que o PO deixa de fora; sem recusa, só `--aprovar`.)

**Pare se** a saída for 2 (erro de uso ou conflito com `conferidos/`: divergência é decisão do PO, nunca
sobrescrita) ou se o PO não aprovou. Saída 1 (algum reprovado ou recusado) segue só com os aptos; o
reprovado fica em `extraidos/` e volta por onda nova ou `rerender` do `mineiro`.

### 4. Recortar, ingerir e extrair

Os três leem `<corpus>/conferidos/<onda>/` e nada mais. Recorte verbatim em trechos citáveis:

```
python3 skills/lavra/scripts/recortar_trechos.py --raiz <corpus> --onda <onda> --saida _esteira/incerto/trechos-<onda>.jsonl
```

Ingestão no Neo4j — **decisão do PO antes**: gasta Vertex (um embedding por trecho) e escreve no AuraDB de
produção (`corpus: 'incerto'`). O bloco leva o número de trechos e o banco de destino. O state é amarrado ao
corpus e torna a ingestão retomável; depois, conferir:

```
python3 skills/lavra/scripts/ingerir_trechos.py --entrada _esteira/incerto/trechos-<onda>.jsonl
python3 skills/lavra/scripts/ingerir_trechos.py --verificar
```

Candidatos a `:Equacao` em staging (se o recorte usou `--nivel N`, a extração usa o mesmo `--nivel N`: o
tópico citado tem de ser o de um trecho, e ela recusa nível diferente do manifesto do recorte):

```
python3 skills/lavra/scripts/extrair_equacoes.py --raiz <corpus> --onda <onda> --saida _esteira/incerto/equacoes-<onda>.jsonl
```

Registre em `docs/oficina/onda-<onda>.md` o que o PO precisa ver da onda: tempos, tokens, custo (ou "não
informado"), trechos, equações parseáveis sobre o total e cada perda declarada com o motivo.

**Pare se** o recorte abortar (tópico acima de `--teto-chars`) ou recusar a saída já existente, se a ingestão
sair com 1 (linha recusada) ou o `--verificar` sair com 1 (duplicata, embedding fora da dimensão, índice
`trecho_*_incerto` ausente ou com o nome tomado por outro índice do banco compartilhado), ou se a extração
recusar sobrescrever `equacoes-<onda>.jsonl` com conteúdo diferente ou um `--nivel` diferente do
recorte.

### 5. Aplicar os momentos

Momento fechado é decisão do PO (`momento_fechado` em `_esteira/incerto/decisoes-<onda>.jsonl`, formato em
`references/devolucao.md`) e entra no candidato **antes do fiscal**, porque a P4 e a `impressao` da prova
Wolfram leem o momento do candidato:

```
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda> --aplicar-momentos
```

Na primeira rodada, os momentos são os que o PO declarou ao escolher as equações da rodada; nas seguintes,
os que vieram no bloco do passo 7.

**Pare se** a aplicação recusar (decisão malformada, momento de equação desconhecida): a mensagem vai ao PO
e nada foi regravado.

### 6. Rodada do fiscal

Com as equações escolhidas para a rodada, escreva `_esteira/incerto/derivacoes-<onda>.jsonl` (`filha`, `mae`,
`alvo`, `substituicao`, `passo`) e `_esteira/incerto/validades-<onda>.jsonl` (`equacao`, `condicao`), cada
linha lida da fonte — derivação e domínio que o trecho dá, nunca os que "deveriam" valer. Então a via SymPy:

```
python3 skills/lavra/scripts/fiscal.py --onda <onda>
```

Todo P4 vermelho "sem prova Wolfram" é a lista de trabalho da segunda via. Para cada item, siga
`references/fiscal.md`: monte o código a partir do `srepr`, rode pelo MCP do Wolfram
(`WolframLanguageEvaluator`) — **quem roda é você, nenhum script chama o Wolfram** —, salve o código e a
saída **verbatim** em `_esteira/incerto/wolfram-<onda>/` e registre:

```
python3 skills/lavra/scripts/registrar_prova.py --onda <onda> --prova P2 --mae <mãe> --filha <filha> --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado
python3 skills/lavra/scripts/registrar_prova.py --onda <onda> --prova momento --equacao <nome> --codigo <arquivo.wl> --saida <arquivo.txt> --veredito verde|vermelho|indeterminado
```

(`--substituir` só para refazer uma prova desatualizada.) Depois, o fiscal de novo, agora com a P4 juntando
as duas vias (as provas vêm de `_esteira/incerto/provas-<onda>.jsonl`; `--provas-wolfram <jsonl>` só se foram
registradas em outro arquivo, nos dois scripts):

```
python3 skills/lavra/scripts/fiscal.py --onda <onda>
```

**Pare se** o fiscal recusar as provas (linha malformada ou chave repetida) ou o registrador recusar
(derivação não declarada, equação desconhecida). Wolfram indisponível não para a rodada: a prova não é
registrada, o item fica P4 vermelho "sem prova Wolfram" e vai ao bloco do passo 7 como vermelho.

### 7. Bloco de decisão único

Um bloco por rodada ao PO, no formato de `references/devolucao.md`: renomeações, rótulos, conceitos,
heurísticas, momentos, indeterminados a aceitar (cada um com as chaves estruturadas exatas da sua linha de
`_esteira/incerto/fiscal-<onda>.jsonl`) e vermelhos (só nota; vermelho nunca promove). As respostas do PO
viram linhas de `_esteira/incerto/decisoes-<onda>.jsonl`, transcritas sem interpretação; confira a
transcrição com o ensaio do passo 8:

```
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda>
```

**Pare se** o PO não respondeu ao bloco inteiro. Se a resposta trouxe momento novo ou mudou derivação,
validade ou candidato, volte ao passo 5: o fiscal ficou desatualizado.

### 8. Aprovar

Primeiro o ensaio — imprime o plano (o que vai `aprovado`, o que fica em `staging` com `pendencias`) sem
abrir o banco:

```
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda>
```

O plano vai ao PO. **Decisão do PO antes** de gravar: `--executar` escreve no AuraDB de produção.

```
python3 skills/lavra/scripts/aprovar_onda.py --onda <onda> --executar
```

**Pare se** o ensaio ou a execução recusarem: fiscal desatualizado (volte ao passo 6), decisão malformada
ou momento decidido fora do candidato (volte ao passo 7), equação do plano já gravada em outra onda
(renomear é decisão do PO na rodada) ou rótulo já usado por outra equação do corpus (outro rótulo, na
rodada). Nada foi gravado em nenhum desses casos.

## Limites

- Não converte PDF, não edita `extraidos/` nem `conferidos/` à mão: correção de conversão é onda nova ou
  `rerender` do `mineiro`.
- Não grava no grafo por fora de `ingerir_trechos.py` e `aprovar_onda.py`; não promove nada que o gate não
  promoveu. Vermelho nunca promove, com ou sem decisão.
- Não decide pelo PO: momento, conceito, heurística, renomeação e aceite de indeterminado são dele, um a um,
  no bloco único da rodada.
- Não roda nem simula passo de gasto ou de escrita sem a decisão do PO.

## Referências

- `references/extracao-nuvem.md` — bucket, `mineiro`, portão do PO.
- `references/grafo-incerto.md` — modelo do grafo, gate e esquema das decisões.
- `references/fiscal.md` — protocolo da prova Wolfram.
- `references/devolucao.md` — o bloco de decisão único da rodada.

<!-- bloco:regras-do-incerto:inicio (gerado de regras-do-incerto.md — edite a fonte e rode build/injetar_regras.py --write) -->
## Regras do Incerto (comuns a skills, agentes e scripts)

**Autoridade.** Comunicação em português do Brasil; o **PO humano é a autoridade final**. Contradição,
dúvida ou achado que mude o modelo do grafo vira **bloco de decisão único** ao PO, nunca mudança
silenciosa.

**Escritor único.** Só `aprovar_onda.py` e `ingerir_trechos.py` escrevem no grafo do Incerto. Todo nó e
toda aresta levam `corpus: 'incerto'`; o Lastro e o Jazida nunca escrevem nele e o Incerto nunca
escreve no grafo deles.

**Nada sem fonte.** Todo nó e toda aresta curada cita `(documento, tópico)` dos `conferidos/`; aresta
derivada leva `origem: 'derivada'` e o script que a gravou. Equação sem fonte não entra nem em staging.

**Equação é nó; fórmula em texto livre não é.** A forma canônica é o `srepr` do SymPy mais o LaTeX de
origem. "Parseável" significa `parse_latex(strict=True)`, normalização de símbolos compostos e
conferência dos símbolos contra o LaTeX; o que falha é ⚠️ com o LaTeX preservado — perda declarada fica
em staging com forma `perda`, nunca aprovada.

**Fiscal de duas vias.** `DERIVA_DE` e `:Equacao` com momento fechado só saem de staging com a prova
SymPy verde **e** a prova Wolfram verde e concordante. Divergência entre as vias é vermelho, com as
duas saídas no relato; prova vermelha é pauta da rodada, não bloqueio silencioso.

**Wolfram pelo agente.** A via Wolfram é executada pelo agente, com as ferramentas MCP do Wolfram, e o
resultado é registrado na prova. Nenhum script chama o Wolfram; a rede só é tocada pelos hosts de Dados
BR, pelo Vertex e pelo Neo4j.

**Dados BR.** Séries do mercado brasileiro só dos hosts `api.bcb.gov.br` e `bvmf.bmfbovespa.com.br`,
com cache em `dados/`. Testes **nunca** tocam a rede.

**Sem import cruzado.** Nenhum `import` nem `spec_from_file_location` aponta para `Lastro`, `jazida`,
`plugin` ou `mineiro`. O que foi copiado leva no cabeçalho
`# copiado de mabritta1984/Lastro@1676115 <caminho>`.

**Credencial.** `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `INCERTO_*` e `VERTEX_*` vêm do
ambiente ou de `~/.lastro/credencial.txt`; Vertex com token OAuth do ambiente, nunca chave de API.
Nenhuma chave de conta de serviço em repositório ou imagem.

**Nunca recomendação de ativo.** O veredito do especialista descreve exposição, convexidade e risco de
cauda; jamais manda comprar, vender ou manter um ativo.

**Marcação de procedência.** Toda afirmação do especialista sai marcada `[corpus]` (veio do grafo
aprovado), `[staging]` (veio de staging, ainda sem aprovação) ou `[externo]` (veio de fora do
corpus, como os dados BR ou o cálculo Wolfram).

**Determinismo.** Separador `/`, `newline="\n"`, ordenação por bytes,
`json.dumps(sort_keys=True, ensure_ascii=False)`, nunca timestamp de execução no que é citável;
amostragens com `random.Random(semente)` explícita.
<!-- bloco:regras-do-incerto:fim -->
