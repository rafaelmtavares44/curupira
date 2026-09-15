"""Os dois algoritmos de dígito verificador, isolados."""

from __future__ import annotations

import pytest

from curupira.formatos import cpf
from curupira.formatos.base import modulo10, modulo11, rng_de


def test_modulo11_resto_menor_que_dois_vira_zero() -> None:
    """Regra compartilhada por CPF, CNPJ e chave de acesso da NF-e."""
    assert modulo11([0], (1,)) == 0
    assert modulo11([1], (1,)) == 0


def test_modulo11_recusa_tamanhos_diferentes() -> None:
    with pytest.raises(ValueError, match="valores para"):
        modulo11([1, 2], (1,))


def test_modulo10_produto_maior_que_nove_soma_os_algarismos() -> None:
    """`8*2 = 16 -> 1+6 = 7`. É a regra que diferencia o módulo 10 da FEBRABAN."""
    assert modulo10([8]) == (10 - 7 % 10) % 10


def test_modulo10_recusa_lista_vazia() -> None:
    with pytest.raises(ValueError, match="vazia"):
        modulo10([])


def test_modulo10_nao_detecta_toda_transposicao() -> None:
    """Limitação REAL do módulo 10, e por isso ela vira tarefa do benchmark.

    Com pesos alternados 2 e 1, trocar dois dígitos vizinhos pode deixar a soma
    intacta. O módulo 11 detecta; o módulo 10 não. Um agente que confia no DV de
    campo da linha digitável passa direto por uma transposição.
    """
    colisoes = [
        (a, b)
        for a in range(10)
        for b in range(10)
        if a != b and modulo10([a, b, 0, 0]) == modulo10([b, a, 0, 0])
    ]
    assert colisoes, "se isto falhar, a premissa da tarefa de transposicao mudou"


def test_rng_e_deterministico() -> None:
    assert [rng_de(42).randrange(100) for _ in range(3)] == [
        rng_de(42).randrange(100) for _ in range(3)
    ]


def test_modulo11_tem_ponto_cego_no_resto_zero_e_um() -> None:
    """ACHADO: o módulo 11 NÃO detecta toda transposição, ao contrário do que se diz.

    A regra "resto menor que 2 vira dígito 0" faz o mapeamento resto→dígito
    deixar de ser injetivo. Uma alteração que mova o resto de 0 para 1 é
    invisível ao verificador.

    Encontrado por teste de propriedade, não por raciocínio — e foi o teste que
    derrubou a afirmação contrária, que estava escrita na docstring deste módulo.
    """
    assert modulo11([0], (1,)) == modulo11([1], (1,)) == 0

    original = "07850565800"
    trocado = "08750565800"  # posicoes 1 e 2 trocadas
    assert cpf.validar(original)
    assert cpf.validar(trocado), "a troca escapa do DV: soma 242 (resto 0) -> 243 (resto 1)"
    assert original != trocado
