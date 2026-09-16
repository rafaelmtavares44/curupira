"""Os matchers, com atenção especial ao que existe por causa do português."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from pydantic import JsonValue

from curupira.core.registry import limpar_registro
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.matchers.numerico import (
    data_iso,
    exact_int,
    moeda_normalizada,
    para_centavos,
    tolerancia_numerica,
)
from curupira.matchers.texto import exact_str, fuzzy_name, normalizar, one_of, por_validador

VAZIO: Mapping[str, JsonValue] = {}


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


# --------------------------------------------------------------------------
# A armadilha do separador decimal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "centavos"),
    [
        ("1.234,56", 123456),  # PT-BR: mil duzentos e trinta e quatro reais
        ("1,234.56", 123456),  # EN: o mesmo valor, convenção invertida
        ("1234,56", 123456),
        ("1234.56", 123456),
        ("1.234", 123400),  # milhar em PT-BR
        ("1234", 123400),
        ("R$ 1.234,56", 123456),
        ("R$1.234,56", 123456),
        ("0,01", 1),
        ("-1.234,56", -123456),
        ("1.234.567,89", 123456789),
    ],
)
def test_para_centavos(texto: str, centavos: int) -> None:
    assert para_centavos(texto) == centavos


def test_ambiguidade_declarada_de_um_virgula_dois_tres_quatro() -> None:
    """`1,234` é genuinamente ambíguo e a política é lê-lo como milhar.

    Mil duzentos e trinta e quatro em inglês; um e vinte e três em português.
    A regra "um separador só é decimal apenas com duas casas" escolhe milhar.
    Uma tarefa que dependa deste caso não deve usar este matcher — deve declarar
    o esperado e testar o comportamento, que é justamente o ponto do benchmark.
    """
    assert para_centavos("1,234") == 123400


@pytest.mark.parametrize("ruim", ["", "abc", "R$", "--"])
def test_para_centavos_recusa_lixo(ruim: str) -> None:
    assert para_centavos(ruim) is None


def test_moeda_aceita_inteiro_e_string() -> None:
    assert moeda_normalizada(123456, 123456, VAZIO)
    assert moeda_normalizada("1.234,56", 123456, VAZIO)
    assert not moeda_normalizada("1.234,57", 123456, VAZIO)


def test_moeda_pode_recusar_string() -> None:
    """Quando a ferramenta declara `integer`, string é quebra de contrato."""
    assert not moeda_normalizada("1.234,56", 123456, {"aceitar_string": False})


def test_o_erro_de_mil_vezes_nao_passa() -> None:
    """O modelo anglófono lê `1.234,56` como 1.234 e transfere mil vezes mais."""
    assert not moeda_normalizada(123456000, 123456, VAZIO)


# --------------------------------------------------------------------------
# exact_int
# --------------------------------------------------------------------------


def test_exact_int_nao_coage_string() -> None:
    assert exact_int(123456, 123456, VAZIO)
    assert not exact_int("123456", 123456, VAZIO)


def test_exact_int_recusa_booleano() -> None:
    """`isinstance(True, int)` é verdadeiro em Python. `True` não é 1 centavo."""
    assert not exact_int(True, 1, VAZIO)


def test_tolerancia_numerica() -> None:
    assert tolerancia_numerica(100.4, 100, {"abs_tol": 0.5})
    assert not tolerancia_numerica(101.0, 100, {"abs_tol": 0.5})
    assert tolerancia_numerica(101.0, 100, {"rel_tol": 0.02})
    assert not tolerancia_numerica("100", 100, {"abs_tol": 1})


# --------------------------------------------------------------------------
# Datas
# --------------------------------------------------------------------------


BR: Mapping[str, JsonValue] = {"formatos_aceitos": ["%d/%m/%Y"]}
EUA: Mapping[str, JsonValue] = {"formatos_aceitos": ["%m/%d/%Y"]}


def test_formato_de_data_vem_da_tarefa() -> None:
    """`03/04/2026` é 3 de abril em português, 4 de março em inglês.

    O matcher não adivinha idioma: a régua é declarada na tarefa, e a mesma
    grafia dá resultados opostos conforme a régua declarada.
    """
    assert data_iso("03/04/2026", "2026-04-03", BR)
    assert not data_iso("03/04/2026", "2026-03-04", BR)
    assert data_iso("03/04/2026", "2026-03-04", EUA)


@pytest.mark.parametrize(
    "params",
    [
        VAZIO,
        {"formatos_aceitos": []},
        {"formatos_aceitos": "%d/%m/%Y"},
        {"formatos_aceitos": [7, None]},
    ],
)
def test_data_sem_regua_declarada_estoura(params: Mapping[str, JsonValue]) -> None:
    """Sem `formatos_aceitos` não há default — havia, e era um viés de locale.

    O default antigo começava por `%d/%m/%Y`, *"porque o dataset nasce em
    PT-BR"*. O efeito é que devolver a entrada **sem converter** acertava na
    versão PT-BR e errava na EN-US: pontos de Delta que o Curupira criava
    sozinho, com `arg_specs` idênticos nos dois lados do par.

    Falhar alto é a rede. O portão é o lint `regua-de-data-explicita`.
    """
    with pytest.raises(ValueError, match="formatos_aceitos"):
        data_iso("03/04/2026", "2026-04-03", params)


def test_a_mensagem_do_estouro_explica_o_motivo() -> None:
    """Um erro que só recusa ensina a contornar; este diz por que não há default."""
    with pytest.raises(ValueError, match="vies de locale"):
        data_iso("03/04/2026", "2026-04-03", VAZIO)


def test_a_regua_vale_para_o_observado_e_o_gabarito_pode_ser_iso() -> None:
    """ISO é aceito no gabarito sem ser aceito no que o agente mandou.

    A assimetria é deliberada e vale registrar num teste, porque é fácil de
    desfazer por engano: o gabarito é nosso e escrevemos em ISO por convenção;
    o valor observado é do agente e só vale pela régua que a tarefa declarou.
    Aceitar ISO no observado "por conveniência" afrouxaria toda tarefa de data
    de um lado só — o lado de quem escreve o gabarito.
    """
    assert data_iso("03/04/2026", "2026-04-03", BR)
    assert not data_iso("2026-04-03", "2026-04-03", EUA)


def test_data_recusa_lixo() -> None:
    assert not data_iso("trinta de abril", "2026-04-30", BR)
    assert not data_iso(20260430, "2026-04-30", BR)


# --------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------


def test_normalizar_colapsa_espacos_e_aplica_nfc() -> None:
    assert normalizar("  Silva   Ltda  ") == "Silva Ltda"
    assert normalizar("conveniência", ignorar_acentos=True) == "conveniencia"


def test_exact_str_e_case_sensitive_por_padrao() -> None:
    assert exact_str("Silva", "Silva", VAZIO)
    assert not exact_str("silva", "Silva", VAZIO)
    assert exact_str("silva", "Silva", {"case_sensitive": False})


def test_one_of_aceita_o_esperado_sem_precisar_repeti_lo() -> None:
    assert one_of("Silva", "Silva", {"values": ["Silva Ltda"]})
    assert one_of("Silva Ltda", "Silva", {"values": ["Silva Ltda"]})
    assert not one_of("Souza", "Silva", {"values": ["Silva Ltda"]})


def test_fuzzy_name_tolera_acento_e_caixa() -> None:
    assert fuzzy_name("JOSE ANTONIO", "José Antônio", VAZIO)
    assert fuzzy_name("Silva", "Sliva", {"threshold": 0.7})
    assert not fuzzy_name("Silva", "Pereira", VAZIO)


def test_por_validador_delega() -> None:
    params: Mapping[str, JsonValue] = {"validador": "cpf"}
    assert por_validador("111.444.777-35", None, params)
    assert not por_validador("111.444.777-36", None, params)


def test_por_validador_com_nome_inexistente_estoura() -> None:
    """O lint do dataset pega isso antes da rodada; aqui é a rede de segurança."""
    with pytest.raises(KeyError, match="nao existe"):
        por_validador("x", None, {"validador": "rg"})


# --------------------------------------------------------------------------
# Resposta maluca de modelo: todo matcher recusa em vez de estourar
# --------------------------------------------------------------------------


def test_matchers_recusam_tipo_errado_sem_estourar() -> None:
    """Um benchmark recebe de tudo. Matcher que levanta derruba a rodada inteira."""
    assert not exact_str(123, "Silva", VAZIO)
    assert not fuzzy_name(None, "Silva", VAZIO)
    assert not por_validador(123, None, {"validador": "cpf"})
    assert not por_validador("x", None, {"validador": 7})
    assert not moeda_normalizada("1,00", "100", VAZIO)
    assert not tolerancia_numerica(True, 1, {"abs_tol": 1})


def test_one_of_compara_valores_nao_textuais() -> None:
    assert one_of(7, 7, VAZIO)
    assert one_of(7, 0, {"values": [7]})
    assert not one_of(7, 0, {"values": [8]})


def test_para_centavos_recusa_decimais_nao_numericos() -> None:
    assert para_centavos("1.2a3") is None
    assert para_centavos("..,,") is None
