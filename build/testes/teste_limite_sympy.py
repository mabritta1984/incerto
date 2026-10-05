# -*- coding: utf-8 -*-
"""limite_sympy.py — limite de tempo de parede do trabalho do SymPy (dono único): o limite vem do ambiente
(`INCERTO_LIMITE_SYMPY_S`, padrão 10 s, valor inválido é ValueError no uso), a função roda num processo
filho persistente que é morto (e a memória dele devolvida) quando o tempo esgota, e o próximo uso sobe outro."""
import os
import threading
import time
import unittest
from unittest import mock
from _carga import carregar

LS = carregar("skills/lavra/scripts/limite_sympy.py")


def _dobro(x):
    return 2 * x


def _pid():
    return os.getpid()


def _dorme(segundos):
    time.sleep(segundos)
    return "acordou"


def _falha(texto):
    raise KeyError(texto)


class TesteLimite(unittest.TestCase):
    def test_padrao_e_10_s(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(LS.AMBIENTE, None)
            self.assertEqual(LS.limite_s(), 10.0)

    def test_ambiente_sobrepoe(self):
        with mock.patch.dict(os.environ, {LS.AMBIENTE: "2.5"}):
            self.assertEqual(LS.limite_s(), 2.5)

    def test_valor_invalido_e_value_error_no_uso(self):
        for valor in ("abc", "0", "-1", "nan", "inf", "", " "):
            with mock.patch.dict(os.environ, {LS.AMBIENTE: valor}):
                with self.assertRaises(ValueError, msg=repr(valor)):
                    LS.limite_s()
                with self.assertRaises(ValueError, msg=repr(valor)):
                    LS.executar(_dobro, 1)


class TesteExecutar(unittest.TestCase):
    def tearDown(self):
        LS.encerrar()

    def test_devolve_o_valor_de_um_processo_filho_persistente(self):
        self.assertEqual(LS.executar(_dobro, 21), 42)
        pid = LS.executar(_pid)
        self.assertNotEqual(pid, os.getpid())
        self.assertEqual(LS.executar(_pid), pid)             # persistente: o mesmo filho atende a próxima chamada

    def test_excecao_do_filho_sobe_com_o_tipo(self):
        with self.assertRaises(KeyError):
            LS.executar(_falha, "x")
        self.assertEqual(LS.executar(_dobro, 2), 4)          # o filho sobrevive à exceção

    def test_tempo_esgotado_mata_o_filho_e_o_proximo_uso_sobe_outro(self):
        filho = LS.executar(_pid)
        with mock.patch.dict(os.environ, {LS.AMBIENTE: "0.3"}):
            LS.executar(_dorme, 0)                           # aquece o filho de `_dorme`
            inicio = time.monotonic()
            with self.assertRaises(LS.TempoEsgotado) as ctx:
                LS.executar(_dorme, 30)
            self.assertLess(time.monotonic() - inicio, 3)
        self.assertEqual(str(ctx.exception), "tempo esgotado no SymPy (0.3 s)")
        self.assertEqual(LS.executar(_pid), filho)           # cada função tem o seu filho: o de `_pid` segue vivo
        self.assertEqual(LS.executar(_dorme, 0), "acordou")  # o de `_dorme` foi morto e outro subiu

    def test_filho_morto_no_tempo_esgotado_nao_existe_mais(self):
        with mock.patch.dict(os.environ, {LS.AMBIENTE: "0.3"}):
            pid = LS.executar(_pid_ou_dorme, 0)
            with self.assertRaises(LS.TempoEsgotado):
                LS.executar(_pid_ou_dorme, 30)
        with self.assertRaises(ProcessLookupError):         # morto e recolhido: a memória dele voltou ao sistema
            os.kill(pid, 0)
        self.assertNotEqual(LS.executar(_pid_ou_dorme, 0), pid)

    def test_funciona_fora_da_thread_principal(self):
        saida = {}

        def rodar():
            with mock.patch.dict(os.environ, {LS.AMBIENTE: "0.3"}):
                try:
                    LS.executar(_dorme, 30)
                except LS.TempoEsgotado as e:
                    saida["erro"] = str(e)
            saida["valor"] = LS.executar(_dobro, 5)

        t = threading.Thread(target=rodar)
        t.start()
        t.join(20)
        self.assertFalse(t.is_alive())
        self.assertEqual(saida, {"erro": "tempo esgotado no SymPy (0.3 s)", "valor": 10})


def _pid_ou_dorme(segundos):
    if not segundos:
        return os.getpid()
    time.sleep(segundos)


if __name__ == "__main__":
    unittest.main()
