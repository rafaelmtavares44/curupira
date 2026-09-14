"""O canário de segredo: a prova das barreiras 3, 4 e 5 de SECURITY.md.

Um teste, várias barreiras, e — o que mais importa — ele pega a regressão que um
contribuidor futuro vai introduzir sem querer. Toda garantia vem com o teste que
a comprova; esta é a garantia que mais dói perder.

A barreira 5 (cache) ganha seu teste quando o cache for implementado na v0.1.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from curupira.core.enums import CamadaDePontuacao, Desfecho
from curupira.core.result import IdentidadeDoAgente, RespostaCrua, ResultadoDeRodada
from curupira.security import (
    MARCA_REDIGIDO,
    FiltroDeRedacao,
    FormatadorDeRedacao,
    carregar_chave,
    instalar_redacao,
    redigir,
    registrar_segredo,
)
from curupira.security.redaction import _REGISTRO

CANARIO = "sk-curupira-canary-NAO-DEVE-VAZAR-8f2c1e40"  # pragma: allowlist secret


def test_redige_texto_simples() -> None:
    registrar_segredo(CANARIO)
    assert redigir(f"chave={CANARIO} fim") == f"chave={MARCA_REDIGIDO} fim"


def test_sem_segredo_registrado_texto_passa_intacto() -> None:
    assert redigir(f"chave={CANARIO}") == f"chave={CANARIO}"


def test_segredo_curto_e_recusado() -> None:
    """Redigir um segredo de 3 letras destruiria log legítimo. Recusar é melhor."""
    with pytest.raises(ValueError, match="menos de"):
        registrar_segredo("abc")


def test_prefixo_nao_deixa_sufixo_exposto() -> None:
    """Segredos são aplicados do mais longo para o mais curto."""
    curto = "sk-curupira-canary"
    registrar_segredo(curto)
    registrar_segredo(CANARIO)
    assert CANARIO not in redigir(f"vazou {CANARIO}")


def test_formatador_redige_mensagem_argumentos_e_traceback(tmp_path: Path) -> None:
    """O mecanismo primário: cobre msg, args e traceback de uma só vez."""
    registrar_segredo(CANARIO)
    arquivo = tmp_path / "curupira.log"

    handler = logging.FileHandler(arquivo, encoding="utf-8")
    handler.setFormatter(FormatadorDeRedacao("%(levelname)s %(message)s"))
    logger = logging.getLogger("teste.formatador")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    logger.debug("chave direto na mensagem: %s", CANARIO)
    logger.info("chave interpolada: " + CANARIO)  # noqa: G003
    try:
        raise RuntimeError(f"estourou com {CANARIO}")
    except RuntimeError:
        logger.exception("falhou")

    handler.close()
    conteudo = arquivo.read_bytes()
    assert CANARIO.encode() not in conteudo, "o canario vazou para o arquivo de log"
    assert MARCA_REDIGIDO.encode() in conteudo


def test_limite_conhecido_filtro_nao_cobre_traceback(tmp_path: Path) -> None:
    """Limitação DECLARADA do mecanismo subsidiário, fixada em teste.

    O `FiltroDeRedacao` atua antes da formatação, então não alcança o traceback.
    Este teste existe para que a limitação não vire surpresa: se alguém um dia a
    corrigir, o teste falha e obriga a atualizar a docstring do módulo.
    """
    registrar_segredo(CANARIO)
    arquivo = tmp_path / "so-filtro.log"

    handler = logging.FileHandler(arquivo, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("teste.filtro")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.addFilter(FiltroDeRedacao())
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    logger.debug("mensagem com %s", CANARIO)  # coberto
    try:
        raise RuntimeError(f"estourou com {CANARIO}")
    except RuntimeError:
        logger.exception("falhou")  # NAO coberto pelo filtro

    handler.close()
    texto = arquivo.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    assert MARCA_REDIGIDO in linhas[0], "o filtro deveria cobrir msg e args"
    assert CANARIO in texto, "limitacao declarada: o filtro nao alcanca o traceback"


def _resultado_minimo() -> ResultadoDeRodada:
    return ResultadoDeRodada(
        task_id="t2-money-0001",
        task_version=1,
        task_hash="0" * 64,
        suite_id="v0.1",
        agent=IdentidadeDoAgente(
            agent_id="agente-teste",
            model="modelo-teste",
            adapter_version="0.1.0",
            prompt_template_id="p0",
            temperature=0.0,
        ),
        repetition=0,
        timestamp=datetime.now(UTC),
        latency_ms=10,
        curupira_version="0.1.0.dev0",
        outcome=Desfecho.PASSOU,
        scoring_layer=CamadaDePontuacao.AST,
        raw=RespostaCrua(text="ok"),
    )


def test_resultado_recusa_campo_extra() -> None:
    """Barreira 4: nenhum campo do resultado é capaz de guardar um header."""
    base = _resultado_minimo().model_dump()
    base["authorization"] = f"Bearer {CANARIO}"
    with pytest.raises(ValidationError):
        ResultadoDeRodada.model_validate(base)


def test_resultado_serializado_nao_contem_canario() -> None:
    """Barreira 4, versão positiva: varre o JSON inteiro do resultado."""
    registrar_segredo(CANARIO)
    dump = _resultado_minimo().model_dump_json()
    assert CANARIO not in dump


def test_filtro_redige_argumentos_em_dicionario() -> None:
    """`record.args` pode ser dict quando se usa `%(chave)s` no formato."""
    registrar_segredo(CANARIO)
    filtro = FiltroDeRedacao()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chave=%(k)s n=%(n)d",
        args={"k": CANARIO, "n": 1},
        exc_info=None,
    )
    assert filtro.filter(record) is True
    assert isinstance(record.args, dict)
    assert record.args["k"] == MARCA_REDIGIDO
    assert record.args["n"] == 1


def test_filtro_preserva_args_nao_textuais() -> None:
    registrar_segredo(CANARIO)
    filtro = FiltroDeRedacao()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="%s %d",
        args=(CANARIO, 42),
        exc_info=None,
    )
    filtro.filter(record)
    assert record.args == (MARCA_REDIGIDO, 42)


def test_filtro_com_msg_nao_textual_nao_quebra() -> None:
    """`logger.info(objeto)` e valido: o filtro tem que deixar passar."""
    registrar_segredo(CANARIO)
    filtro = FiltroDeRedacao()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=1234,
        args=None,
        exc_info=None,
    )
    assert filtro.filter(record) is True
    assert record.msg == 1234


def test_instalar_redacao_protege_handler_ja_existente(tmp_path: Path) -> None:
    """O caso real: um logger ja configurado por outra parte do sistema."""
    registrar_segredo(CANARIO)
    arquivo = tmp_path / "instalado.log"

    logger = logging.getLogger("teste.instalar")
    logger.handlers.clear()
    logger.filters.clear()
    handler = logging.FileHandler(arquivo, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    instalar_redacao(logger)
    logger.warning("vazando %s", CANARIO)
    try:
        raise RuntimeError(f"e no traceback tambem: {CANARIO}")
    except RuntimeError:
        logger.exception("falhou")

    handler.close()
    conteudo = arquivo.read_text(encoding="utf-8")
    assert CANARIO not in conteudo
    assert "WARNING | vazando" in conteudo, "o formato original foi preservado"


def test_instalar_redacao_sem_handler_nao_quebra() -> None:
    logger = logging.getLogger("teste.sem.handler")
    logger.handlers.clear()
    logger.filters.clear()
    instalar_redacao(logger)
    assert any(isinstance(f, FiltroDeRedacao) for f in logger.filters)


def test_registro_e_imutavel_durante_a_redacao() -> None:
    """Regressao: `redigir` iterava um `set` mutavel e podia estourar em concorrencia.

    Iterar um `set` enquanto outra thread insere levanta `RuntimeError` — dentro
    do caminho de log, que e o pior lugar possivel. O registro agora e uma tupla
    trocada por rebind, e `redigir` captura a referencia uma vez.
    """
    registrar_segredo(CANARIO)
    instantaneo = _REGISTRO.segredos
    assert isinstance(instantaneo, tuple)

    registrar_segredo("outro-segredo-bem-comprido-12345")
    assert _REGISTRO.segredos is not instantaneo, "o registro foi trocado, nao mutado"
    assert instantaneo == (CANARIO,), "o instantaneo antigo nao mudou"


def test_registro_ordena_do_mais_longo_para_o_mais_curto() -> None:
    registrar_segredo("sk-curupira-canary")
    registrar_segredo(CANARIO)
    comprimentos = [len(s) for s in _REGISTRO.segredos]
    assert comprimentos == sorted(comprimentos, reverse=True)


def test_registrar_o_mesmo_segredo_duas_vezes_e_idempotente() -> None:
    registrar_segredo(CANARIO)
    registrar_segredo(CANARIO)
    assert _REGISTRO.segredos == (CANARIO,)


def test_carregar_chave_registra_no_mesmo_passo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fecha a janela: nao ha como obter a chave sem que ela fique registrada."""
    monkeypatch.setenv("CURUPIRA_CHAVE_DE_TESTE", CANARIO)
    chave = carregar_chave("CURUPIRA_CHAVE_DE_TESTE")

    assert isinstance(chave, SecretStr)
    assert chave.get_secret_value() == CANARIO
    assert repr(chave) == "SecretStr('**********')", "SecretStr mascara em repr"
    assert redigir(f"log {CANARIO}") == f"log {MARCA_REDIGIDO}", "ja esta registrada"


def test_carregar_chave_ausente_estoura(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURUPIRA_CHAVE_DE_TESTE", raising=False)
    with pytest.raises(KeyError):
        carregar_chave("CURUPIRA_CHAVE_DE_TESTE")


def test_carregar_chave_vazia_estoura(monkeypatch: pytest.MonkeyPatch) -> None:
    """Variavel presente porem vazia e o caso que passa despercebido."""
    monkeypatch.setenv("CURUPIRA_CHAVE_DE_TESTE", "")
    with pytest.raises(KeyError):
        carregar_chave("CURUPIRA_CHAVE_DE_TESTE")
