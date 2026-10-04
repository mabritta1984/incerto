# -*- coding: utf-8 -*-
"""Carga de módulo do Incerto por caminho (adaptado de jazida/build/testes/_carga.py, copiado de
mabritta1984/Lastro@1676115). A raiz é o repositório; nada fora dele é carregado."""
import importlib.util, os, sys
sys.dont_write_bytecode = True
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def carregar(rel):
    """`rel` relativo à raiz do repositório (ex.: 'skills/lavra/scripts/nucleo.py')."""
    nome = "incerto_" + rel.replace("/", "_").replace(".py", "")
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, *rel.split("/")))
    if spec is None:
        raise FileNotFoundError(rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[nome] = mod
    return mod
