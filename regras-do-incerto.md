# regras-do-incerto — fonte única (v0.1.0-dev)

Este arquivo é a **casa única** das regras comuns às skills, agentes e scripts do Incerto. Ele **não é
lido em runtime**: a seção entre os marcadores abaixo é **injetada** por `build/injetar_regras.py`
(reuso direto do injetor do Lastro) em cada consumidor — hoje o `README.md`; depois, cada
`skills/*/SKILL.md` e a docstring de `mcp/consulta_incerto.py`. Edite **aqui**, rode
`python3 build/injetar_regras.py --write --raiz . --bloco-obrigatorio regras-do-incerto` e confira com
`--check`. Origem: "Global Constraints" do plano
`docs/superpowers/plans/2026-10-04-incerto-0.1.0-bifurcacao-da-jazida.md`.

<!-- bloco:regras-do-incerto:inicio (dono deste bloco — edite aqui) -->
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
conferência dos símbolos contra o LaTeX; o que falha é ⚠️ com o LaTeX preservado — perda declarada,
nunca nó.

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
