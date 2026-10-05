<!-- copiado de mabritta1984/Lastro@1676115 jazida/skills/lavra/references/extracao-nuvem.md -->
# Extração na nuvem — o que o `mineiro` entrega e como o Incerto consome (dono único deste contrato)

Esta reference é **dona única** de três coisas: o layout do bucket do corpus, o que o Incerto exige do
que o `mineiro` grava em `extraidos/<onda>/`, e o **portão do PO** entre `extraidos/` e `conferidos/`.
Ela **não descreve o conversor**: como o PDF vira Markdown (modelo, prompt, parâmetros, extrator) é do
`mineiro` (`mabritta1984/mineiro`, `docs/deploy-cloud-run.md` e `config-cloud.yaml` de lá). O Incerto
consome o resultado pelo bucket, sem importar nada dele, e nada de conversor, extrator de PDF ou prompt
de conversão entra neste plugin.

Adapta, para a nuvem, o contrato de extração do Lastro (`plugin/skills/curadoria/references/extracao.md`,
lido como texto, nunca importado): o original é o árbitro, o extraído é a projeção textual dele, e o
resultado é rascunho até o PO conferir. Perda declarada é aceitável; perda silenciosa não.

## Layout do bucket (`gs://jazida-bucket`)

```
originais/<fonte>/<nome>.<ext>            ← imutável; versionamento do bucket ligado; o árbitro
extraidos/<onda>/                         ← saída do mineiro, uma pasta por onda; rascunho
    <nome>.<ext>.md
    <nome>.<ext>.report.json
    <nome>.<ext>.assets/fig_N.png
    lote-<data>.md
    manifesto.json                        ← escrito pelo Incerto no portão (conferir_onda.py --aprovar)
conferidos/<onda>/                        ← o que o PO aprovou; a única entrada do recorte (V5)
    <nome>.<ext>.md, .report.json, .assets/, manifesto.json
_esteira/                                 ← área de trabalho (sondas, provas); nunca é fonte
```

- **`<fonte>`** agrupa originais de uma mesma procedência (ex.: `TALEB`); **`<onda>`** nomeia uma execução
  de conversão (ex.: `2026-10-TALEB-1`). Nome de onda e de fonte: letras, dígitos, `.`, `_` e `-`, sem
  `/`, sem `..` e **sem vírgula** (a vírgula separa os `--args` do `gcloud run jobs execute`).
- **Nome com extensão de origem.** O extraído de `Relatorios.pdf` é `Relatorios.pdf.md`, nunca
  `Relatorios.md`: `Relatorios.pdf` e `Relatorios.xlsx` não podem colidir. O leitor recusa `.md` sem a
  extensão de origem no nome.
- **`originais/` nunca é reescrito.** Correção de conversão é onda nova (ou `rerender` do `mineiro`),
  nunca edição à mão em `extraidos/` nem em `conferidos/`.
- O versionamento do bucket está ligado (soft delete de 7 dias): cópia para `conferidos/` é cópia; o
  portão **não apaga** `extraidos/<onda>/`, que continua sendo o registro do que o conversor entregou.

## O que o `mineiro` grava

**Por documento** (em `extraidos/<onda>/`):

| Artefato | O que é | O Incerto usa? |
|---|---|---|
| `<nome>.<ext>.md` | projeção textual do original: Markdown, equação em `$$…$$`, diagrama em ` ```mermaid `, figura como `![](<nome>.<ext>.assets/fig_N.png)` seguida de descrição de modelo | sim — é o texto que o recorte (V5) lê |
| `<nome>.<ext>.report.json` | relatório do documento, item a item | sim — é a fonte de toda conta do relatório de fidelidade |
| `<nome>.<ext>.assets/` | imagens recortadas do original | copiadas com o documento para `conferidos/`; o contrato não as lê |

**Por lote**: `lote-<data>.md`, resumo legível da execução. **É informativo e nunca é somado**: o
`rerender` do `mineiro` regrava os `.report.json` mas não o `lote-*.md` (achado de 27/09 na onda
`2026-09-PSX-1`: o lote mostra Mermaid 0/133 e os relatórios, 129/133). Toda conta vem dos `summary` e
`items` dos `.report.json`, nunca do `lote-*.md`.

### Estrutura do `.report.json` (a parte que o contrato lê)

Chaves de topo: `source` (caminho do original no job, ex.: `/mnt/corpus/originais/TALEB/<nome>.pdf`),
`generated_at`, `summary`, `items`. `generated_at` é timestamp de execução: **não entra** em nada
citável nem no manifesto (determinismo).

Cada item de `items` tem `item_id`, `kind` (`text`, `table`, `formula`, `picture`), `route`
(`passthrough`, `equation`, `mermaid`, `describe`, `skip`, …), `approved`, `fallback`, `attempts`
(cada um com `feedback`), `final` (o trecho que foi para o `.md`), `metrics`, `provider`, `model`,
`model_version`, `tokens`, `cost_usd`.

`summary` traz `itens`, `aprovados`, `fallbacks`, `segundos` (tempo de modelo), `segundos_parede`,
`tokens` (`prompt`, `output`, `thoughts`, `total`), `model_versions`, `erros`, `parse` (engine,
`paginas_falhas`, `paginas_sem_texto`, `avisos`), `custo_estimado_usd` (só quando a `config` do
`mineiro` tem preços em `prices`; sem preço, `cost_usd` é `null` e o custo é **não informado**, nunca
zero) e `equacoes`:

| Campo de `summary.equacoes` | Leitura |
|---|---|
| `equacoes_detectadas` | equações na rota `equation`, sem as descartadas |
| `via_parse`, `via_gemini`, `via_codeformula` | de onde veio o LaTeX aceito |
| `fallback_imagem`, `texto_mantido`, `descritas`, `com_erro` | equação que **não** virou LaTeX: perda declarada no `.md` |
| `latex_invalido_1a_tentativa`, `latex_invalido_final` | LaTeX recusado pelo validador; o final tem de ser 0 |
| `validador` | `"katex"` quando o KaTeX validou; `"pylatexenc"` quando só a estrutura foi conferida; `null` quando nenhuma equação passou pelo validador |

## Contrato de consumo — o que o leitor exige de cada documento

O leitor (`skills/lavra/scripts/conferir_onda.py`) reprova o documento, com o motivo, quando:

1. **Falta o par**: `.md` sem `.report.json` ou o inverso, ou nome sem a extensão de origem.
2. **Relatório ilegível**: JSON inválido, sem `source`, `summary` ou `items`, ou `summary.itens`
   diferente do número de itens.
3. **Equação sem KaTeX**: `summary.equacoes.validador` diferente de `"katex"` com
   `equacoes_detectadas > 0`. `null` só é aceito com `equacoes_detectadas == 0` (achado de 27/09: na
   onda PSX, `"katex"` nos 31 documentos com equação e `null` nos 12 sem). O `pylatexenc` confere só a
   estrutura e deixaria passar LaTeX que o SymPy não parseia.
4. **LaTeX inválido no fim**: `summary.equacoes.latex_invalido_final > 0`.
5. **Perda silenciosa**: item com `approved: false` e `fallback: false`, ou item em fallback cujo
   `final` não está no `.md` verbatim ou não traz a marca `[fallback]`.
6. **Página vazia sem marca**: `summary.parse.paginas_sem_texto > 0` (ver a rota abaixo).

O que **não** reprova, e aparece no relatório como **perda declarada**, por rota: item em fallback com a
marca `> ⚠️ [fallback] …` no ponto do `.md` onde o conteúdo estava (diagrama não convertido, equação
mantida como imagem ou texto), e página que o parse não converteu (`summary.parse.paginas_falhas`, rota
`parse`), que o `mineiro` marca no `.md` com a mesma nota.

### PDF sem camada de texto

A onda roda com `parsing.engine: gemini_pdf` (a `config-cloud.yaml` do `mineiro`): o modelo lê a imagem
de cada página, e página escaneada é convertida como qualquer outra — não há OCR à parte (Document AI
fica fora da 0.1.0). Se uma onda rodar com o engine `docling` sem OCR, página sem camada de texto sai
**vazia e sem marca no ponto**; o `mineiro` só a conta em `summary.parse.paginas_sem_texto` e nos
`avisos`. Para o Incerto isso é perda silenciosa: o documento é reprovado e volta para uma onda nova com
`gemini_pdf`. Se nem o modelo ler a página, ela sai como `[fallback]` (perda declarada) e o original
continua sendo a fonte daquele trecho.

## Relatório de fidelidade e manifesto

`conferir_onda.py` lê `extraidos/<onda>/` (disco: o bucket montado em `/mnt/corpus` no job, ou uma
cópia local; a leitura direta de `gs://` fica fora, decisão 3a do PO de 28/09) e imprime, no formato de tabela dos verificadores do Lastro:

- **resumo**: documentos (aptos, reprovados), itens (aprovados, fallbacks), tokens, tempo de modelo e de
  parede, custo (ou "não informado");
- **por rota**: itens, fallbacks e não aprovados de cada `route`, mais a linha `parse` (páginas);
- **equações**: detectadas, origem do LaTeX, perdas, validador por documento e parseáveis pelo SymPy
  (`n/total`, medido pela função de parse do `extrair_equacoes.py` (Task 8), com a definição de
  "parseável" da decisão 2 do PO de 28/09; "não medido" só se o import dele ou do `sympy` falhar);
- **perdas declaradas**: documento, item, rota e o `feedback` da última tentativa (ex.: `finishReason=MAX_TOKENS`);
- **veredito por documento**: apto ou reprovado, com os motivos.

O **manifesto da onda** é `manifesto.json` (`json.dumps(sort_keys=True, ensure_ascii=False)`, sem
timestamp), escrito pelo portão em `extraidos/<onda>/` e copiado para `conferidos/<onda>/`. Por
documento: `documento`, `veredito` (`apto`, `reprovado`, `recusado_pelo_po`), `motivos`, `perdas`
(item, rota, motivo), `sha256_md`, `sha256_report`, `original` (o `source` do relatório),
`sha256_original` (quando o original é legível no mesmo disco; senão `null`), `engine`,
`model_versions`, `validador`, `equacoes_detectadas`. Por onda: `onda`, `ferramenta` (`mineiro`) e os
totais do resumo. O `mineiro` não grava a versão do prompt nem o hash do original no relatório: o
manifesto registra o que existe e deixa `null` no que não existe, sem inventar.

## Portão do PO

Extração é o estágio em que o erro entra em silêncio e com boa aparência; por isso nada sai de
`extraidos/` sem o PO.

1. **Conferir**: `python3 skills/lavra/scripts/conferir_onda.py --raiz <corpus> --onda <onda>` só lê e
   relata. O PO lê o relatório e, por amostragem dirigida, o `.md` contra o original: tabelas célula a
   célula, ordem de leitura, títulos (a unidade de citação) e as perdas declaradas.
2. **Aprovar**: `--aprovar` grava o `manifesto.json` e copia cada documento **apto** (`.md`,
   `.report.json`, `.assets/`) para `conferidos/<onda>/`. `--recusar <nome>=<motivo>` (repetível)
   deixa um documento apto de fora por decisão do PO, com o motivo no manifesto.
3. **Reprovado fica em `extraidos/`** com os motivos no manifesto e não é recortado; o assunto dele
   continua respondido pelo original. Volta pelo `mineiro` (onda nova ou `rerender`) e passa de novo
   pelo portão.
4. **`conferidos/` não se reescreve**: se um arquivo de documento já copiado difere do que o portão
   copiaria, ou se um documento já copiado ficaria de fora (reprovado ou recusado agora), o portão para
   antes de escrever qualquer coisa e relata; a divergência é decisão do PO, não sobrescrita. O
   `manifesto.json` é o registro da conferência e é regravado a cada `--aprovar` (o versionamento do
   bucket guarda os anteriores): documento reprovado que volta apto depois do `rerender` entra assim.

### Reparo de páginas (emenda)

O `mineiro` reconverte só documentos inteiros. Quando uma faixa de páginas se perde (nota
`> ⚠️ [fallback] páginas A-B não convertida(s) …` no `.md`, `summary.parse.paginas_falhas` e a mensagem em
`summary.erros`), o PO pode converter só aquelas páginas como sub-PDF numa onda própria
(`extraidos/<onda>-reparo-<sigla>/<nome>_pA-B.pdf`, numerado de 1 a N) e emendá-las antes do portão
(decisão do PO de 05/10, Dynamic_Hedging.pdf pp. 321–340 da onda 2026-10-TALEB-1):
`python3 skills/lavra/scripts/emendar_paginas.py --raiz <corpus> --onda <onda> --documento <nome.pdf>
--onda-reparo <onda> --documento-reparo <nome_pA-B.pdf> --paginas A-B`. A nota vira o `.md` do reparo entre
`<!-- reparo: páginas A-B, onda <onda-reparo>, relatório sha256 <…> -->` e `<!-- fim do reparo: páginas A-B -->`;
os assets vão para `<nome>.assets/` com o prefixo `reparo-pA-B-` (referências reescritas; colisão recusa); o
registro (faixa, onda e documento do reparo, sha256 do relatório e do `.md` do reparo, sha256 do `.md` alvo
antes e depois, os `items` com ids prefixados, `summary.equacoes` e as mensagens de `erros` resolvidas) vai
para o sidecar `<nome>.reparos.json`. O `.report.json` do `mineiro` nunca muda (procedência). A emenda recusa,
sem gravar nada, se não houver exatamente uma nota para a faixa, se o reparo tiver `paginas_falhas` > 0 ou
outro número de páginas (quando o relatório o informa), se o reparo não passar nas regras deste contrato, ou
se a faixa já tiver sido reparada (não se reaplica). O portão lê o sidecar: o `.md` tem de ser o de depois do
último reparo (senão, "md alterado fora do reparo", inapto); as páginas reparadas saem de `paginas_falhas`
e a mensagem resolvida sai das perdas; itens e equações do reparo entram nas regras de perda silenciosa e
nas contagens; o relatório ganha a seção "Reparos"; o `--aprovar` copia o sidecar e os assets emendados.
Os marcadores são comentários HTML: não viram tópico no recorte nem equação na extração, e as equações do
reparo entram na ordem do `.md` emendado (`<documento>#<ordem>`). Perda de sumário (ex.: SCFT pp. 7–14) não
se emenda: continua perda declarada.

## Executar uma onda

A conversão é o Cloud Run Job `mineiro-onda` (projeto `jazida`, `us-central1`), disparado pelo workflow
`.github/workflows/conversao.yml` do monorepo (`workflow_dispatch` com `onda` e `origem`, autenticação
por Workload Identity Federation, sem chave). Rodar uma onda gasta modelo: disparar é decisão do PO.

## Fronteiras

Esta reference é dona de **como o extraído chega aos `conferidos/`**. Não é dona do conversor
(`mineiro`), do recorte em `:Trecho` (V5, `recortar_trechos.py`) nem do que vira nó: equação que o
SymPy não parseia é perda declarada com o LaTeX preservado, nunca nó (regras do Incerto).
