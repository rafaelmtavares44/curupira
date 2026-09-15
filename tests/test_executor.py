"""O runner: escritor único, recusas prévias, cache e seed honesta.

O teste que importa mais aqui é `test_escrita_concorrente_nao_corrompe_o_bruto`.
A corrupção que ele previne é silenciosa: linhas intercaladas só aparecem na hora
de agregar, depois de a API já ter sido paga.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from curupira.adapters.anthropic import AdaptadorAnthropic
from curupira.adapters.base import (
    AdaptadorDeModelo,
    ErroDoProvedor,
    Mensagem,
    ParametrosDeAmostragem,
    RequisicaoPreparada,
)
from curupira.adapters.falso import AdaptadorFalso, Politica
from curupira.core.registry import limpar_registro
from curupira.core.result import ExecucaoCrua, IdentidadeDoAgente, RespostaCrua
from curupira.core.suite import Suite, congelar
from curupira.core.task import DefinicaoDeFerramenta, Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from curupira.runner.executor import (
    NOME_DO_BRUTO,
    ContextoDaRodada,
    ErroDeSeguranca,
    executar_repeticao,
    executar_suite,
    identidade,
    ler_bruto,
    montar_mensagens,
    seed_da_repeticao,
)
from curupira.security import esquecer_segredos, registrar_segredo
from tests.fabricas import par_strict, tarefa_bruta

CHAVE = SecretStr("")
PARAMETROS = ParametrosDeAmostragem()


def _sem_rede(request: httpx.Request) -> httpx.Response:
    """Transporte que nunca sai da maquina. Nenhum teste do runner toca a rede."""
    del request
    return httpx.Response(200, json={"content": []})


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


@pytest.fixture
def tarefas() -> dict[str, Tarefa]:
    return {
        bruto["id"]: Tarefa.model_validate(bruto)
        for bruto in (*par_strict("par-a"), *par_strict("par-b"))
    }


@pytest.fixture
def suite(tarefas: dict[str, Tarefa]) -> Suite:
    return congelar(list(tarefas.values()), suite_id="v-teste")


def _contexto(**extras: Any) -> ContextoDaRodada:
    base: dict[str, Any] = {
        "suite_id": "v-teste",
        "agent_id": "agente-de-teste",
        "modelo": "falso-1",
    }
    base.update(extras)
    return ContextoDaRodada(**base)


async def _rodar(
    suite: Suite,
    tarefas: dict[str, Tarefa],
    destino: Path,
    *,
    adaptador: AdaptadorDeModelo | None = None,
    contexto: ContextoDaRodada | None = None,
    repeticoes: int = 1,
    concorrencia: int = 1,
) -> list[ExecucaoCrua]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_sem_rede)) as cliente:
        bruto = await executar_suite(
            suite,
            tarefas,
            adaptador or AdaptadorFalso(),
            PARAMETROS,
            contexto=contexto or _contexto(),
            chave=CHAVE,
            cliente=cliente,
            repeticoes=repeticoes,
            saida=destino,
            concorrencia=concorrencia,
        )
    return ler_bruto(bruto)


# --------------------------------------------------------------------------
# Funcoes puras
# --------------------------------------------------------------------------


def test_montar_mensagens_usa_a_mensagem_literal() -> None:
    """Nada de instrução nossa no prompt: seria uma variável nossa no número."""
    tarefa = Tarefa.model_validate(tarefa_bruta())
    (mensagem,) = montar_mensagens(tarefa)
    assert mensagem == Mensagem(role="user", content=tarefa.input.user_message)


def test_seed_da_repeticao() -> None:
    assert seed_da_repeticao(None, 3) is None
    assert seed_da_repeticao(10, 3) == 13


def test_identidade_marca_seed_nao_aplicada() -> None:
    """A Anthropic não aceita seed; registrar como aplicada seria mentira."""
    parametros = ParametrosDeAmostragem(seed=7)
    anthropic = identidade(_contexto(), AdaptadorAnthropic(), parametros)
    falso = identidade(_contexto(), AdaptadorFalso(), parametros)
    assert anthropic.seed == 7
    assert anthropic.seed_aplicada is False
    assert falso.seed_aplicada is True


def test_identidade_sem_seed_nunca_declara_aplicada() -> None:
    assert identidade(_contexto(), AdaptadorFalso(), PARAMETROS).seed_aplicada is False


def test_modelo_recusa_seed_aplicada_sem_seed() -> None:
    with pytest.raises(ValueError, match="mentiria"):
        IdentidadeDoAgente(
            agent_id="a",
            model="m",
            adapter_version="0.1.0",
            prompt_template_id="cru-v1",
            temperature=0.0,
            seed=None,
            seed_aplicada=True,
        )


# --------------------------------------------------------------------------
# Uma repeticao
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execucao_grava_o_corpo_literal() -> None:
    """Sem o corpo enviado, ninguém pode conferir o que chegou ao modelo."""
    tarefa = Tarefa.model_validate(tarefa_bruta())
    async with httpx.AsyncClient() as cliente:
        execucao = await executar_repeticao(
            tarefa,
            AdaptadorFalso(),
            PARAMETROS,
            contexto=_contexto(),
            chave=CHAVE,
            cliente=cliente,
            repeticao=0,
        )
    corpo = json.loads(execucao.request_body)
    assert corpo["messages"][0]["content"] == tarefa.input.user_message
    assert corpo["tools"][0]["input_schema"]["properties"]["valor_centavos"]["type"] == "integer"
    assert execucao.cost_brl == 0.0


@pytest.mark.asyncio
async def test_execucao_com_erro_do_provedor_vira_linha_de_erro() -> None:
    """Um 529 não é erro do agente; vira `erro`, e o agregador o exclui."""

    class Quebrado:
        nome = "quebrado"
        versao = "0.0.1"
        suporta_seed = False

        def preparar(
            self,
            *,
            modelo: str,
            mensagens: tuple[Mensagem, ...],
            ferramentas: tuple[DefinicaoDeFerramenta, ...],
            parametros: ParametrosDeAmostragem,
            system: str | None = None,
        ) -> RequisicaoPreparada:
            del modelo, mensagens, ferramentas, parametros, system
            return RequisicaoPreparada(url="memory://x", corpo={})

        async def completar(
            self,
            requisicao: RequisicaoPreparada,
            *,
            chave: SecretStr,
            cliente: httpx.AsyncClient,
        ) -> RespostaCrua:
            del requisicao, chave, cliente
            raise ErroDoProvedor("quebrado", 529, "overloaded")

    tarefa = Tarefa.model_validate(tarefa_bruta())
    async with httpx.AsyncClient() as cliente:
        execucao = await executar_repeticao(
            tarefa,
            Quebrado(),
            PARAMETROS,
            contexto=_contexto(),
            chave=CHAVE,
            cliente=cliente,
            repeticao=0,
        )
    assert execucao.raw is None
    assert execucao.erro is not None
    assert "529" in execucao.erro


def test_execucao_exige_um_entre_resposta_e_erro() -> None:
    campos: dict[str, Any] = {
        "task_id": "t",
        "task_version": 1,
        "task_hash": "0" * 64,
        "suite_id": "v",
        "agent": IdentidadeDoAgente(
            agent_id="a",
            model="m",
            adapter_version="0",
            prompt_template_id="cru-v1",
            temperature=0.0,
        ),
        "repetition": 0,
        "timestamp": "2026-09-14T00:00:00Z",
        "latency_ms": 1,
        "curupira_version": "0",
        "request_body": "{}",
    }
    with pytest.raises(ValueError, match="exatamente um"):
        ExecucaoCrua(**campos)
    with pytest.raises(ValueError, match="exatamente um"):
        ExecucaoCrua(**campos, raw=RespostaCrua(text="oi"), erro="tambem um erro")


@pytest.mark.asyncio
async def test_corpo_com_segredo_para_a_rodada() -> None:
    """Redigir aqui esconderia um defeito de adaptador atrás de artefato limpo."""
    segredo = "segredo-que-jamais-deveria-ir-no-corpo"
    registrar_segredo(segredo)

    class Vazador(AdaptadorFalso):
        def preparar(
            self,
            *,
            modelo: str,
            mensagens: tuple[Mensagem, ...],
            ferramentas: tuple[DefinicaoDeFerramenta, ...],
            parametros: ParametrosDeAmostragem,
            system: str | None = None,
        ) -> RequisicaoPreparada:
            del modelo, mensagens, ferramentas, parametros, system
            return RequisicaoPreparada(url="memory://x", corpo={"authorization": segredo})

    try:
        tarefa = Tarefa.model_validate(tarefa_bruta())
        async with httpx.AsyncClient() as cliente:
            with pytest.raises(ErroDeSeguranca, match="segredo registrado"):
                await executar_repeticao(
                    tarefa,
                    Vazador(),
                    PARAMETROS,
                    contexto=_contexto(),
                    chave=CHAVE,
                    cliente=cliente,
                    repeticao=0,
                )
    finally:
        esquecer_segredos()


# --------------------------------------------------------------------------
# A suite inteira
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rodada_grava_uma_linha_por_repeticao(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    execucoes = await _rodar(suite, tarefas, tmp_path / "rodada", repeticoes=3)
    assert len(execucoes) == len(tarefas) * 3
    assert {e.repetition for e in execucoes} == {0, 1, 2}
    assert all(e.suite_id == "v-teste" for e in execucoes)


@pytest.mark.asyncio
async def test_escrita_concorrente_nao_corrompe_o_bruto(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    """O requisito do escritor único, verificado onde ele quebraria.

    Com append direto de várias corrotinas, linhas se intercalam e o JSON de
    alguma delas deixa de parsear. `ler_bruto` valida linha a linha, então a
    corrupção vira falha aqui — e não meses depois, na agregação.
    """
    destino = tmp_path / "rodada"
    execucoes = await _rodar(suite, tarefas, destino, repeticoes=5, concorrencia=8)
    bruto = (destino / NOME_DO_BRUTO).read_text(encoding="utf-8")
    linhas = [linha for linha in bruto.splitlines() if linha.strip()]
    assert len(linhas) == len(execucoes) == len(tarefas) * 5
    for linha in linhas:
        json.loads(linha)


@pytest.mark.asyncio
async def test_hash_divergente_impede_a_rodada(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    """Falha antes de pagar: número errado em silêncio é o pior resultado."""
    alvo = next(iter(tarefas))
    tarefas[alvo] = tarefas[alvo].model_copy(update={"difficulty": 5})
    with pytest.raises(ValueError, match="edicao silenciosa"):
        await _rodar(suite, tarefas, tmp_path / "rodada")


@pytest.mark.asyncio
async def test_tarefa_ausente_impede_a_rodada(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    del tarefas[next(iter(tarefas))]
    with pytest.raises(ValueError, match="sumiu do dataset"):
        await _rodar(suite, tarefas, tmp_path / "rodada")


@pytest.mark.asyncio
async def test_multiturno_impede_a_rodada(tmp_path: Path) -> None:
    """Descobrir isso na tarefa 200 custaria as outras 199."""
    bruto = tarefa_bruta()
    bruto["input"]["followup_turns"] = [{"message": "e agora?"}]
    tarefa = Tarefa.model_validate(bruto)
    tarefas = {tarefa.id: tarefa}
    suite = congelar([tarefa], suite_id="v-teste")
    with pytest.raises(ValueError, match="followup_turns"):
        await _rodar(suite, tarefas, tmp_path / "rodada")


@pytest.mark.asyncio
async def test_parametros_absurdos_sao_recusados(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match=">= 1"):
        await _rodar(suite, tarefas, tmp_path / "rodada", repeticoes=0)
    with pytest.raises(ValueError, match=">= 1"):
        await _rodar(suite, tarefas, tmp_path / "rodada", concorrencia=0)


@pytest.mark.asyncio
async def test_cache_e_usado_na_segunda_rodada(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    contexto = _contexto(cache=tmp_path / "cache")
    primeira = await _rodar(suite, tarefas, tmp_path / "r1", contexto=contexto)
    segunda = await _rodar(suite, tarefas, tmp_path / "r2", contexto=contexto)
    assert not any(e.do_cache for e in primeira)
    assert all(e.do_cache for e in segunda)
    assert all(e.latency_ms == 0 for e in segunda)
    assert [e.raw for e in primeira] == [e.raw for e in segunda]


@pytest.mark.asyncio
async def test_rodada_recusa_bruto_preexistente(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    """Duas rodadas no mesmo diretório fundiriam os brutos em silêncio.

    O escritor abre em append — de propósito, para nunca truncar o que já foi
    pago — e essa escolha só é segura se ninguém puder apontar duas rodadas para
    o mesmo lugar.
    """
    destino = tmp_path / "rodada"
    await _rodar(suite, tarefas, destino)
    with pytest.raises(ValueError, match="ja existe"):
        await _rodar(suite, tarefas, destino)


@pytest.mark.asyncio
async def test_sem_cache_nada_e_persistido(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    await _rodar(suite, tarefas, tmp_path / "rodada")
    assert not (tmp_path / "cache").exists()


@pytest.mark.asyncio
async def test_a_falha_de_uma_corrotina_nao_trava_o_escritor(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    """Sem a sentinela no `finally`, o erro de verdade viraria um travamento."""
    registrar_segredo("segredo-que-jamais-deveria-ir-no-corpo")

    class Vazador(AdaptadorFalso):
        def preparar(
            self,
            *,
            modelo: str,
            mensagens: tuple[Mensagem, ...],
            ferramentas: tuple[DefinicaoDeFerramenta, ...],
            parametros: ParametrosDeAmostragem,
            system: str | None = None,
        ) -> RequisicaoPreparada:
            del modelo, mensagens, ferramentas, parametros, system
            return RequisicaoPreparada(
                url="memory://x", corpo={"a": "segredo-que-jamais-deveria-ir-no-corpo"}
            )

    try:
        async with asyncio.timeout(20):
            with pytest.raises(ErroDeSeguranca):
                await _rodar(suite, tarefas, tmp_path / "rodada", adaptador=Vazador())
    finally:
        esquecer_segredos()


@pytest.mark.asyncio
async def test_politica_nunca_chama_nao_produz_chamada(
    suite: Suite, tarefas: dict[str, Tarefa], tmp_path: Path
) -> None:
    """A linha de base trivial precisa rodar no mesmo caminho da rodada real."""
    execucoes = await _rodar(
        suite,
        tarefas,
        tmp_path / "rodada",
        adaptador=AdaptadorFalso(Politica.NUNCA_CHAMA),
    )
    assert all(e.raw is not None and e.raw.tool_calls == () for e in execucoes)
