# Dados BR — SGS do Banco Central e COTAHIST da B3

Dono único do contrato de dados do mercado brasileiro. Código: `skills/taleb/scripts/dados_br.py`. Tudo
que sai daqui é `[externo]`. Testes nunca tocam a rede; o cache fica em `dados/` (conteúdo fora do git).

## Hosts a liberar na política de rede do ambiente

O PO precisa permitir estes dois hosts (HTTPS, porta 443); sem eles o ambiente devolve HTTP 000.

| Host | Para quê |
|---|---|
| `api.bcb.gov.br` | séries do SGS (`sgs()` baixa daqui) |
| `bvmf.bmfbovespa.com.br` | ZIP anual do COTAHIST (download manual, ver abaixo) |

## Séries do SGS (`SERIES`)

| Nome | Código | Série |
|---|---|---|
| `selic_diaria` | 11 | taxa Selic diária (% a.d.) |
| `cdi_diaria` | 12 | taxa CDI diária (% a.d.) |
| `selic_meta` | 432 | meta da taxa Selic (% a.a.) |
| `ipca_mensal` | 433 | IPCA, variação mensal (%) |
| `ptax_venda` | 1 | dólar americano (venda), PTAX |
| `ibovespa` | 7 | índice Ibovespa |

URL: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<codigo>/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`.
A resposta é uma lista de `{"data": "dd/mm/aaaa", "valor": "0.055131"}`; o `valor` vem como **string** e a
data como `dd/mm/aaaa`. A API recusa janelas diárias maiores que 10 anos; `sgs()` divide o pedido em
janelas de até 10 anos, concatena em ordem de data e remove datas repetidas. HTTP diferente de 200 ou
corpo que não é lista levanta `DadosIndisponiveis` (a mensagem traz o código da série e a URL).

Cache: `dados/sgs-<codigo>-<inicio ISO>-<fim ISO>.json`, um arquivo por pedido, gravado de forma
determinística (`sort_keys`, `ensure_ascii=False`, `\n`). Para atualizar, apague o arquivo.

## Layout do COTAHIST (registro de 245 caracteres, latin-1)

Posições 1-based, inclusivas. Linha `00` é cabeçalho, `99` é rodapé; só `01` (negociação) é lida.
Preços e volume são inteiros com **2 decimais implícitos** (`0000000003250` = 32,50); `cotahist_ler` divide por 100.

| Campo | Posições | Tipo | Observação |
|---|---|---|---|
| `TIPREG` | 1–2 | texto | `00` cabeçalho, `01` negociação, `99` rodapé |
| `DATA` | 3–10 | `aaaammdd` | data do pregão |
| `CODBDI` | 11–12 | texto | código BDI |
| `CODNEG` | 13–24 | texto | ticker (preenchido com espaços) |
| `TPMERC` | 25–27 | texto | `010` vista, `020` fracionário, etc. |
| `NOMRES` | 28–39 | texto | nome resumido |
| `ESPECI` | 40–49 | texto | especificação (ex.: `PN N2`) |
| `PREABE` | 57–69 | preço | abertura |
| `PREMAX` | 70–82 | preço | máxima |
| `PREMIN` | 83–95 | preço | mínima |
| `PREMED` | 96–108 | preço | média |
| `PREULT` | 109–121 | preço | último (fechamento) |
| `VOLTOT` | 171–188 | valor | volume financeiro total |

`cotahist_ler(caminho, tickers=None)` aceita `.txt` ou `.zip` (lê o primeiro membro). `tickers` filtra por
`CODNEG` exato; **não filtra `TPMERC`**: o mercado fracionário (ticker terminado em `F`, `020`) vem como
ticker próprio, e quem quiser só o mercado à vista filtra `tpmerc == "010"`. O COTAHIST não ajusta
proventos nem desdobramentos: retornos de longo prazo precisam desse tratamento antes de virarem
evidência de cauda.

## Baixar o COTAHIST à mão (rede bloqueada)

1. Em uma máquina com acesso, baixe `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A<ano>.ZIP`
   (`cotahist_url(ano)` devolve a URL), por exemplo `COTAHIST_A2025.ZIP`.
2. Coloque o ZIP em `dados/` (não vai para o git), sem descompactar.
3. Rode `python3 skills/taleb/scripts/dados_br.py --cotahist dados/COTAHIST_A2025.ZIP --ticker PETR4`.

O mesmo vale para uma série do SGS: baixe a URL acima, grave o JSON como
`dados/sgs-<codigo>-<inicio ISO>-<fim ISO>.json` no formato do cache (lista de `["aaaa-mm-dd", valor]`) e a
chamada com o mesmo intervalo o usa sem tocar a rede. Período cujo fim é hoje ou depois nunca vai ao cache
(nem gravado nem lido): o dia corrente ainda não fechou, e a série congelaria incompleta — peça até ontem.
