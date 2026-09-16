"""A referência de teste da errata aponta para um teste que existe.

Antes disto, `test_ref` era texto livre que ninguém conferia. A errata exige
"o teste que reproduz o defeito" justamente para separar *"esta tarefa tem
gabarito errado"* de *"o modelo X vai mal nessa tarefa"* — e uma exigência que
não é verificada não separa nada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from curupira.core.referencia import partes, problema

RAIZ = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# A forma da referência
# --------------------------------------------------------------------------


def test_referencia_bem_formada_separa_em_caminho_e_nome() -> None:
    assert partes("tests/test_x.py::test_y") == ("tests/test_x.py", "test_y")


def test_espacos_em_volta_sao_tolerados() -> None:
    """Colar de um relatório do pytest costuma trazer espaço junto."""
    assert partes(" tests/test_x.py :: test_y ") == ("tests/test_x.py", "test_y")


@pytest.mark.parametrize(
    ("referencia", "por_que"),
    [
        ("tests/test_x.py", "falta o nome do teste"),
        ("test_y", "falta o arquivo"),
        ("tests/test_x.py::Classe::test_y", "classe de teste nao e aceita"),
        ("tests/test_x.txt::test_y", "o arquivo precisa ser .py"),
        ("tests/test_x.py::nao eh identificador", "o nome precisa ser identificador"),
        ("tests/test_x.py::", "nome vazio"),
    ],
)
def test_forma_invalida_e_recusada(referencia: str, por_que: str) -> None:
    assert partes(referencia) is None, por_que


# --------------------------------------------------------------------------
# A existência do teste
# --------------------------------------------------------------------------


def test_teste_que_existe_nao_gera_problema() -> None:
    """Auto-referente de propósito: este arquivo é a própria evidência."""
    assert (
        problema(RAIZ, "tests/test_referencia.py::test_teste_que_existe_nao_gera_problema") is None
    )


def test_arquivo_inexistente_e_acusado() -> None:
    falha = problema(RAIZ, "tests/test_que_nunca_existiu.py::test_x")
    assert falha is not None
    assert "nao existe" in falha


def test_arquivo_existe_mas_o_teste_nao() -> None:
    """O caso mais comum de verdade: o teste foi renomeado e a errata ficou para trás."""
    falha = problema(RAIZ, "tests/test_referencia.py::test_apagado_faz_tempo")
    assert falha is not None
    assert "nao define" in falha


def test_forma_invalida_explica_o_formato_esperado(tmp_path: Path) -> None:
    """Mensagem que só recusa faz o autor chutar; esta mostra a forma certa."""
    falha = problema(tmp_path, "isto nao e uma referencia")
    assert falha is not None
    assert "tests/arquivo.py::nome_do_teste" in falha


def test_teste_assincrono_tambem_conta(tmp_path: Path) -> None:
    """O projeto usa `pytest-asyncio`; recusar `async def` seria falso negativo."""
    (tmp_path / "test_async.py").write_text(
        "async def test_algo() -> None:\n    pass\n", encoding="utf-8"
    )
    assert problema(tmp_path, "test_async.py::test_algo") is None


def test_arquivo_com_sintaxe_quebrada_e_acusado_sem_estourar(tmp_path: Path) -> None:
    """Um `.py` inválido no repositório não pode derrubar o comando."""
    (tmp_path / "test_quebrado.py").write_text("def test_x(:\n", encoding="utf-8")

    falha = problema(tmp_path, "test_quebrado.py::test_x")

    assert falha is not None
    assert "nao pode ser lido como Python" in falha
