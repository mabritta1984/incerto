# -*- coding: utf-8 -*-
# copiado de mabritta1984/Lastro@1676115 jazida/build/testes/_banco.py
"""Apoio aos testes que precisam de Neo4j de verdade (Incerto).

`@precisa_neo4j` roda o teste só quando NEO4J_TESTE_URI existe — no CI, o service container `neo4j:5` de
`.github/workflows/testes.yml`. Nunca aponte estas variáveis para o AuraDB do corpus: os testes gravam e
apagam nós `corpus: 'incerto-teste'`. Variáveis: NEO4J_TESTE_URI (base da Query API, ex.: http://localhost:7474),
NEO4J_TESTE_USUARIO, NEO4J_TESTE_SENHA, NEO4J_TESTE_DATABASE (opcional), NEO4J_TESTE_BOLT (opcional).
"""
import os
import unittest
from _carga import carregar

AURA = ".databases.neo4j.io"


def _uri():
    uri = os.environ.get("NEO4J_TESTE_URI", "").strip()
    return "" if AURA in uri else uri          # trava: o Aura nunca é banco de teste


precisa_neo4j = unittest.skipUnless(_uri(), "NEO4J_TESTE_URI ausente (ou apontando para o Aura) — "
                                            "teste de banco real só roda contra o service container")


def cred_de_teste():
    """Credencial no formato do núcleo, montada das variáveis NEO4J_TESTE_* (nunca das NEO4J_* da sessão)."""
    cred = {"NEO4J_QUERY_URL": _uri(),
            "NEO4J_URI": os.environ.get("NEO4J_TESTE_BOLT", "bolt://localhost:7687"),
            "NEO4J_USERNAME": os.environ.get("NEO4J_TESTE_USUARIO", "neo4j"),
            "NEO4J_PASSWORD": os.environ.get("NEO4J_TESTE_SENHA", "")}
    if os.environ.get("NEO4J_TESTE_DATABASE"):
        cred["NEO4J_DATABASE"] = os.environ["NEO4J_TESTE_DATABASE"]
    return cred


PARTICAO = "incerto-teste"
_APAGAR = "MATCH (n {corpus: $corpus}) DETACH DELETE n"


def limpar_banco_de_teste(cred, db):
    """Apaga só os nós da partição `incerto-teste`. Par de `banco_de_teste()`: registre com addCleanup."""
    carregar("skills/lavra/scripts/nucleo.py").query_api(cred, db, _APAGAR, {"corpus": PARTICAO})


def banco_de_teste():
    """(cred, db) do banco de teste, já limpo. Não registra nada global: quem chama faz
    `self.addCleanup(limpar_banco_de_teste, cred, db)` logo depois (padrão: setUp)."""
    cred = cred_de_teste()
    db = cred.get("NEO4J_DATABASE") or os.environ.get("NEO4J_TESTE_DATABASE") or "neo4j"
    limpar_banco_de_teste(cred, db)
    return cred, db
