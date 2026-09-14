"""O hash de conteúdo: determinístico, sensível ao que importa, cego ao resto."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

from curupira.core.hashing import bytes_canonicos, hash_da_tarefa
from curupira.core.loader import carregar_tarefa
from curupira.core.task import Tarefa
from tests.fabricas import tarefa_bruta


def _tarefa(**kwargs: Any) -> Tarefa:
    return Tarefa.model_validate(tarefa_bruta(**kwargs))


def test_formato_do_hash() -> None:
    valor = hash_da_tarefa(_tarefa())
    assert len(valor) == 64
    assert valor == valor.lower()
    assert set(valor) <= set("0123456789abcdef")


def test_determinismo() -> None:
    """Duas serializações da mesma tarefa produzem o mesmo hash."""
    assert hash_da_tarefa(_tarefa()) == hash_da_tarefa(_tarefa())


def test_mudanca_semantica_muda_o_hash() -> None:
    """Se o gabarito muda, o hash muda. É a razão de o hash existir."""
    assert hash_da_tarefa(_tarefa(valor=123456)) != hash_da_tarefa(_tarefa(valor=123400))


def test_mudanca_de_dificuldade_muda_o_hash() -> None:
    assert hash_da_tarefa(_tarefa()) != hash_da_tarefa(_tarefa(difficulty=4))


def test_parity_notes_muda_o_hash() -> None:
    """Escolha conservadora, declarada: NADA é excluído do hash.

    Corrigir um typo numa nota de paridade obriga a subir `task_version`. O custo
    é real; a alternativa — manter uma lista de campos "não semânticos" — é uma
    lista que alguém estende até cobrir algo que importava.
    """
    a = hash_da_tarefa(_tarefa(parity_notes="so o idioma muda"))
    b = hash_da_tarefa(_tarefa(parity_notes="so o idioma muda."))
    assert a != b


def test_forma_curta_e_expansao_explicita_hasheiam_igual(tmp_path: Path) -> None:
    """A forma curta é açúcar sintático, não outra tarefa.

    Depois da carga as duas viram o mesmo objeto, então o hash é o mesmo — e o
    dataset pode usar a grafia curta sem virar um segundo formato de dados.
    """
    curta = tmp_path / "curta.yaml"
    longa = tmp_path / "longa.yaml"
    curta.write_text(yaml.safe_dump(tarefa_bruta(forma_curta=True)), encoding="utf-8")
    longa.write_text(yaml.safe_dump(tarefa_bruta(forma_curta=False)), encoding="utf-8")

    assert hash_da_tarefa(carregar_tarefa(curta)) == hash_da_tarefa(carregar_tarefa(longa))


def test_formatacao_do_yaml_nao_muda_o_hash(tmp_path: Path) -> None:
    """Reidentar, reordenar chaves ou comentar não invalida uma suíte."""
    bruto = tarefa_bruta()
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(yaml.safe_dump(bruto, sort_keys=True), encoding="utf-8")
    b.write_text(
        "# um comentario no topo\n"
        + yaml.safe_dump(bruto, sort_keys=False, default_flow_style=False, indent=4),
        encoding="utf-8",
    )
    assert hash_da_tarefa(carregar_tarefa(a)) == hash_da_tarefa(carregar_tarefa(b))


def test_nfc_iguala_acento_decomposto() -> None:
    """A razão de existir da normalização, num dataset em português.

    "transferência" digitado no macOS chega decomposto (NFD) e no Windows
    composto (NFC): bytes diferentes, mesmo texto. Sem NFC, a mesma tarefa
    hashearia diferente conforme a máquina em que foi editada, e a suíte acusaria
    adulteração onde houve apenas um checkout.
    """
    texto = "transferência de conveniência"
    composto = unicodedata.normalize("NFC", texto)
    decomposto = unicodedata.normalize("NFD", texto)
    assert composto != decomposto, "o teste so vale se as duas formas diferem"

    a = _tarefa(input={"user_message": composto})
    b = _tarefa(input={"user_message": decomposto})
    assert hash_da_tarefa(a) == hash_da_tarefa(b)


def test_bytes_canonicos_sao_utf8_compacto_e_ordenado() -> None:
    bruto = bytes_canonicos(_tarefa())
    texto = bruto.decode("utf-8")
    assert ", " not in texto, "separadores compactos"
    assert texto.index('"canary_guid"') < texto.index('"context"'), "chaves ordenadas"


def test_nan_e_recusado() -> None:
    """NaN não é JSON válido e destruiria o determinismo do hash."""
    bruto = tarefa_bruta()
    bruto["expect"]["accept"][0]["calls"][0]["args"]["valor_centavos"] = float("nan")
    tarefa = Tarefa.model_validate(bruto)

    with pytest.raises(ValueError, match="not JSON compliant"):
        bytes_canonicos(tarefa)
