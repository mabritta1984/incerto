#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Limite de tempo de parede do trabalho do SymPy — dono único; `extrair_equacoes.py` e `fiscal.py` o importam.

Um SymPy que não volta para a esteira inteira (a eq. 2.7 de *Statistical Consequences of Fat Tails*,
`\\int_0^\\infty e^{\\varepsilon x} dF(x) = +\\infty`, fica avaliando a integral para sempre dentro do
`parse_latex`). Perda declarada é sempre aceitável; travar, não. Por isso o trabalho do SymPy roda aqui:

  `executar(funcao, *args)` → `funcao(*args)` num processo FILHO persistente (um por `funcao`); se a resposta
  não vier em `limite_s()` segundos (tempo de parede), o filho é morto (SIGKILL) e recolhido — a memória de
  um parse descontrolado volta ao sistema — e sobe `TempoEsgotado`; o próximo uso abre outro filho. Exceção
  da `funcao` no filho sobe igual no chamador (com o tipo; a que não atravessa o pickle sobe como
  `RuntimeError` com o tipo e a mensagem). Filho que morre sem responder sobe `ProcessoPerdido`.

`limite_s()`: `INCERTO_LIMITE_SYMPY_S` do ambiente (segundos, float finito > 0), lido a cada uso; ausente →
`LIMITE_PADRAO_S` (10 s); qualquer outro valor (vazio inclusive) → `ValueError` no uso.

Por que processo filho com `fork`, e não `signal.setitimer`: o alarme só funciona na thread principal, e a
exceção que ele levanta no meio do SymPy é engolida pelos `except Exception` do caminho (medido: na eq. 2.7
o alarme vira a perda `strict`, um motivo falso); e não devolve a memória de nada. O `fork` funciona de
qualquer thread (o filho nasce só com a thread que o criou), herda os módulos já carregados (o `sympy`, os
vizinhos carregados por caminho nos testes) sem pickle de função nem `sys.path`, e matar o filho interrompe
qualquer laço, em Python ou em C. Filho persistente, não um por chamada: a extração e o portão chamam o
parse ~950 vezes por onda; o custo por chamada é uma ida e volta por pipe. Cuidado do `fork`: o chamador
não deve ter outras threads segurando travas no momento em que o filho nasce (a esteira é de uma thread
só). Só biblioteca padrão: o `sympy` é importado pelas funções dos dois scripts, dentro do filho.
"""
import math
import multiprocessing
import os
import pickle
import signal
import threading

AMBIENTE = "INCERTO_LIMITE_SYMPY_S"
LIMITE_PADRAO_S = 10.0


class TempoEsgotado(Exception):
    """O SymPy não respondeu em `limite` segundos; o filho foi morto."""

    def __init__(self, limite):
        super().__init__("tempo esgotado no SymPy (%g s)" % limite)
        self.limite = limite


class ProcessoPerdido(RuntimeError):
    """O filho do SymPy morreu sem responder (morto de fora, sem memória, …)."""


def limite_s():
    """Segundos de parede por chamada: `INCERTO_LIMITE_SYMPY_S` ou 10; ValueError se inválido."""
    texto = os.environ.get(AMBIENTE)
    if texto is None:
        return LIMITE_PADRAO_S
    try:
        valor = float(texto)
    except ValueError:
        valor = float("nan")
    if not math.isfinite(valor) or valor <= 0:
        raise ValueError("%s=%r: use segundos, número finito > 0 (padrão %g)" % (AMBIENTE, texto, LIMITE_PADRAO_S))
    return valor


def _transportavel(e):
    """A exceção `e`, se atravessa o pickle; senão uma do mesmo tipo só com a mensagem; senão RuntimeError."""
    for candidata in (lambda: e, lambda: type(e)(str(e))):
        try:
            c = candidata()
            pickle.loads(pickle.dumps(c))
            return c
        except Exception:
            pass
    return RuntimeError("%s: %s" % (type(e).__name__, e))


def _laco(funcao, conexao):
    """Corpo do filho: atende `args` pelo pipe até o pai fechá-lo (ou matá-lo)."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)            # o Ctrl-C é do pai, que mata o filho
    while True:
        try:
            seq, args = conexao.recv()
        except (EOFError, OSError):
            return
        try:
            resposta = (seq, "ok", funcao(*args))
        except BaseException as e:
            resposta = (seq, "erro", _transportavel(e))
        try:
            conexao.send(resposta)
        except Exception as e:                               # resultado que não atravessa o pickle
            conexao.send((seq, "erro", RuntimeError("resposta do SymPy não transportável: %s: %s" % (type(e).__name__, e))))


class _Filho:
    def __init__(self, funcao):
        self.funcao = funcao
        self.trava = threading.Lock()
        self.processo = self.conexao = None
        self.seq = 0                                         # número do pedido; o filho o devolve na resposta

    def _abrir(self):
        ctx = multiprocessing.get_context("fork")
        pai, filho = ctx.Pipe()
        processo = ctx.Process(target=_laco, args=(self.funcao, filho), name="incerto-sympy", daemon=True)
        processo.start()
        filho.close()
        self.processo, self.conexao = processo, pai

    def fechar(self):
        if self.processo is None:
            return
        processo, conexao, self.processo, self.conexao = self.processo, self.conexao, None, None
        if processo.is_alive():
            processo.kill()
        processo.join()
        processo.close()
        conexao.close()

    def chamar(self, args, limite):
        with self.trava:
            if self.processo is None or not self.processo.is_alive():
                self.fechar()
                self._abrir()
            self.seq += 1
            seq = self.seq
            try:
                self.conexao.send((seq, args))
                esgotou = not self.conexao.poll(limite)
                if not esgotou:
                    seq_resposta, estado, valor = self.conexao.recv()
            except (EOFError, OSError):                      # o filho morreu entre `is_alive()` e o envio/a leitura
                self.fechar()
                raise ProcessoPerdido("o processo do SymPy morreu sem responder")
            except BaseException:                            # interrupção/timeout externo: a resposta ficaria pendente
                self.fechar()                                # e a próxima chamada leria a desta; mata e descarta
                raise
            if esgotou:
                self.fechar()
                raise TempoEsgotado(limite)
            if seq_resposta != seq:                          # resposta de outro pedido: nunca a entrega
                self.fechar()
                raise ProcessoPerdido("resposta do SymPy fora de sequência (pedido %d, resposta %r)" % (seq, seq_resposta))
        if estado == "erro":
            raise valor
        return valor


_FILHOS = {}
_TRAVA = threading.Lock()
_DONO = os.getpid()


def _filho(funcao):
    global _FILHOS, _DONO
    with _TRAVA:
        if os.getpid() != _DONO:                             # este processo nasceu de um fork: os filhos não são dele
            _FILHOS, _DONO = {}, os.getpid()
        if funcao not in _FILHOS:
            _FILHOS[funcao] = _Filho(funcao)
        return _FILHOS[funcao]


def executar(funcao, *args):
    """`funcao(*args)` no filho persistente de `funcao`, sob `limite_s()`; `TempoEsgotado` se passar dele."""
    limite = limite_s()
    return _filho(funcao).chamar(args, limite)


def encerrar():
    """Mata e recolhe todos os filhos (o próximo `executar` abre outro)."""
    with _TRAVA:
        filhos = list(_FILHOS.values()) if os.getpid() == _DONO else []
        _FILHOS.clear()
    for f in filhos:
        with f.trava:
            f.fechar()
