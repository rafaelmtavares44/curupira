"""O esqueleto importa inteiro e as pontas soltas estão declaradas como tal."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.metadata import distribution

import pytest

import curupira
from curupira.formatos.boleto import validar as validar_linha_digitavel


def _todos_os_modulos() -> list[str]:
    nomes = [curupira.__name__]
    for info in pkgutil.walk_packages(curupira.__path__, prefix="curupira."):
        nomes.append(info.name)
    return sorted(nomes)


@pytest.mark.parametrize("nome", _todos_os_modulos())
def test_modulo_importa(nome: str) -> None:
    """Nenhum módulo do pacote quebra no import."""
    importlib.import_module(nome)


def test_nao_ha_litellm_entre_as_dependencias() -> None:
    """ADR 0002: `litellm` não é dependência deste projeto, nem como extra."""
    requisitos = distribution("curupira").requires or []
    assert not any("litellm" in r.lower() for r in requisitos)


def test_stub_falha_alto_e_nao_devolve_valor_errado() -> None:
    """Um stub tem que estourar, não devolver `None` e contaminar um relatório.

    Aponta de propósito para uma ponta solta ainda aberta. Quando `validar` do
    boleto for implementado, este teste falha e obriga a escolher outro alvo — ou
    a apagar o teste, se não sobrar stub nenhum.

    A auto-destruição é o recurso, não o defeito: o teste vira um lembrete que
    não dá para ignorar. Alvos já aposentados por terem sido implementados:
    `cep.validar` (Entrega 6).
    """
    with pytest.raises(NotImplementedError):
        validar_linha_digitavel("0" * 47)
