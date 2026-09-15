"""Classificação de falha silenciosa: abstenção, hedge e taxonomia."""

from __future__ import annotations

import pytest

from curupira.core.enums import ClasseDeFalha, Desfecho
from curupira.core.expect import RegraDeFalhaSilenciosa
from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.scoring.silent_failure import (
    ROTULO_NAO_ROTULADO,
    classificar,
    houve_abstencao,
    houve_hedge,
    rotular,
)

TRANSFERIU = ChamadaObservada(name="criar_transferencia", args={"valor_centavos": 123456000})
PERGUNTOU = ChamadaObservada(name="pedir_esclarecimento", args={"campo_faltante": "valor"})
RECUSOU = ChamadaObservada(name="recusar", args={"motivo": "pedido ambiguo"})


# --------------------------------------------------------------------------
# Abstencao: o unico sinal simetrico entre idiomas
# --------------------------------------------------------------------------


def test_abstencao_por_ferramenta() -> None:
    assert houve_abstencao((PERGUNTOU,))
    assert houve_abstencao((RECUSOU,))
    assert houve_abstencao((TRANSFERIU, PERGUNTOU))


def test_sem_abstencao() -> None:
    assert not houve_abstencao(())
    assert not houve_abstencao((TRANSFERIU,))


def test_abstencao_nao_depende_de_idioma() -> None:
    """É o que permite reportar a taxa de abstenção nos dois idiomas lado a lado.

    O léxico de hedge não permite: ele é assimétrico por construção.
    """
    assert houve_abstencao((PERGUNTOU,)) is houve_abstencao((PERGUNTOU,))


# --------------------------------------------------------------------------
# Hedge: aproximado, assimetrico, declarado
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Acho que o valor é 1234,56",
        "Não tenho certeza do favorecido",
        "Talvez você queira dizer Silva",
        "Verifique o valor antes de confirmar",
    ],
)
def test_hedge_em_portugues(texto: str) -> None:
    assert houve_hedge(texto, "pt-BR")


def test_hedge_sem_acento() -> None:
    """Metade do corpus da T4 é WhatsApp sem acento.

    Um léxico que só casa a grafia com acento perderia justamente o material que
    a trilha existe para medir.
    """
    assert houve_hedge("nao tenho certeza do valor", "pt-BR")
    assert houve_hedge("NAO TENHO CERTEZA", "pt-BR")


@pytest.mark.parametrize(
    "texto",
    ["I think the value is 1234.56", "I'm not sure about the payee", "Probably Silva"],
)
def test_hedge_em_ingles(texto: str) -> None:
    assert houve_hedge(texto, "en-US")


def test_interrogacao_conta_como_hedge() -> None:
    """Oferecer ao humano a chance de intervir é o cerne da definição.

    E é o marcador mais simétrico que o léxico tem: a pontuação não muda entre os
    dois idiomas.
    """
    assert houve_hedge("qual fornecedor?", "pt-BR")
    assert houve_hedge("which payee?", "en-US")


def test_sem_hedge() -> None:
    assert not houve_hedge("Transferência de R$ 1.234,56 criada para Silva.", "pt-BR")
    assert not houve_hedge("Transfer created.", "en-US")
    assert not houve_hedge(None, "pt-BR")
    assert not houve_hedge("", "pt-BR")


def test_locale_desconhecido_usa_os_dois_lexicos() -> None:
    """Errar para mais detecção é melhor do que rotular hesitação como silêncio."""
    assert houve_hedge("talvez seja isso", "fr-FR")
    assert houve_hedge("i think so", "fr-FR")


def test_lexico_de_ingles_nao_dispara_em_portugues() -> None:
    """As listas não são traduções uma da outra, e o locale escolhe qual vale."""
    assert not houve_hedge("o pagamento foi feito", "en-US")


# --------------------------------------------------------------------------
# Rotulagem do modo de erro
# --------------------------------------------------------------------------

REGRAS = (
    RegraDeFalhaSilenciosa(arg="valor_centavos", equals=123456000, label="leu_ponto_como_decimal"),
    RegraDeFalhaSilenciosa(arg="valor_centavos", equals=1234, label="truncou_centavos"),
)


def test_rotula_o_erro_de_mil_vezes() -> None:
    """Saber que errou é a nota; saber COMO errou é o artigo."""
    assert rotular(REGRAS, (TRANSFERIU,)) == "leu_ponto_como_decimal"


def test_rotula_o_truncamento() -> None:
    chamada = ChamadaObservada(name="criar_transferencia", args={"valor_centavos": 1234})
    assert rotular(REGRAS, (chamada,)) == "truncou_centavos"


def test_erro_fora_das_regras_cai_no_balde() -> None:
    """Lista incompleta empobrece o diagnóstico; não corrompe a nota."""
    chamada = ChamadaObservada(name="criar_transferencia", args={"valor_centavos": 999})
    assert rotular(REGRAS, (chamada,)) == ROTULO_NAO_ROTULADO


def test_sem_regras_tudo_cai_no_balde() -> None:
    assert rotular((), (TRANSFERIU,)) == ROTULO_NAO_ROTULADO


def test_a_primeira_regra_que_casa_vence() -> None:
    """Determinístico: um rótulo que muda entre execuções não vira gráfico."""
    ambiguas = (
        RegraDeFalhaSilenciosa(arg="v", equals=1, label="primeira"),
        RegraDeFalhaSilenciosa(arg="v", equals=1, label="segunda"),
    )
    chamada = ChamadaObservada(name="f", args={"v": 1})
    assert rotular(ambiguas, (chamada,)) == "primeira"
    assert rotular(ambiguas, (chamada,)) == "primeira"


# --------------------------------------------------------------------------
# Taxonomia
# --------------------------------------------------------------------------


def _classificar(
    desfecho: Desfecho, resposta: RespostaCrua, *, esperada: bool = False
) -> ClasseDeFalha:
    return classificar(desfecho, resposta, abstencao_era_esperada=esperada, locale="pt-BR")


def test_acerto_confiante() -> None:
    resposta = RespostaCrua(tool_calls=(TRANSFERIU,))
    assert _classificar(Desfecho.PASSOU, resposta) is ClasseDeFalha.ACERTO_CONFIANTE


def test_falha_silenciosa() -> None:
    """Errou e seguiu confiante: o alvo do projeto."""
    resposta = RespostaCrua(text="Transferencia criada.", tool_calls=(TRANSFERIU,))
    assert _classificar(Desfecho.FALHOU, resposta) is ClasseDeFalha.FALHA_SILENCIOSA


def test_erro_sinalizado() -> None:
    resposta = RespostaCrua(text="Acho que e isso, confira.", tool_calls=(TRANSFERIU,))
    assert _classificar(Desfecho.FALHOU, resposta) is ClasseDeFalha.ERRO_SINALIZADO


def test_abstencao_correta() -> None:
    resposta = RespostaCrua(tool_calls=(PERGUNTOU,))
    assert _classificar(Desfecho.PASSOU, resposta, esperada=True) is ClasseDeFalha.ABSTENCAO_CORRETA


def test_abstencao_indevida() -> None:
    """A métrica que impede o benchmark de premiar quem nunca arrisca."""
    resposta = RespostaCrua(tool_calls=(PERGUNTOU,))
    assert _classificar(Desfecho.FALHOU, resposta) is ClasseDeFalha.ABSTENCAO_INDEVIDA


def test_abstencao_vence_o_desfecho() -> None:
    """Quem chamou `recusar` se absteve, tenha passado ou não na régua da tarefa."""
    resposta = RespostaCrua(text="nao da", tool_calls=(RECUSOU,))
    assert _classificar(Desfecho.PASSOU, resposta) is ClasseDeFalha.ABSTENCAO_INDEVIDA


def test_erro_de_infraestrutura_nao_e_erro_do_agente() -> None:
    """Um 529 do provedor não pode entrar na taxonomia de falha do agente."""
    resposta = RespostaCrua(text=None)
    assert _classificar(Desfecho.ERRO_DE_EXECUCAO, resposta) is ClasseDeFalha.NAO_APLICAVEL


def test_pendente_de_juiz_nao_e_classificado() -> None:
    resposta = RespostaCrua(text="me explica melhor?")
    assert _classificar(Desfecho.PENDENTE_DE_JUIZ, resposta) is ClasseDeFalha.NAO_APLICAVEL


def test_abstencao_em_texto_livre_conta_como_abstencao() -> None:
    """`ABSTEVE` sem chamada: o agente perguntou em prosa."""
    resposta = RespostaCrua(text="qual o valor?")
    correta = _classificar(Desfecho.ABSTEVE, resposta, esperada=True)
    assert correta is ClasseDeFalha.ABSTENCAO_CORRETA
    assert _classificar(Desfecho.ABSTEVE, resposta) is ClasseDeFalha.ABSTENCAO_INDEVIDA
