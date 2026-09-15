"""Carga do dataset em YAML, com normalização e lint.

O lint existe porque o schema sozinho não alcança as invariantes que importam.
O Pydantic garante que uma tarefa tem os campos certos; ele não sabe dizer se o
par em inglês existe, se dois canários colidem, ou se um `variant_group` tem
gabaritos repetidos — e é justamente esse tipo de defeito que produz um número
errado em silêncio.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from curupira.core.enums import Locale, Paridade, Split
from curupira.core.expect import (
    ChamadaEsperada,
    EspecificacaoDeArgumento,
    EsperaChamadaDeFerramenta,
    EsperaExtracao,
    EsperaRecusa,
    EsperaSequencia,
)
from curupira.core.registry import nomes_registrados
from curupira.core.task import Tarefa

ID_DA_FORMA_CURTA = "canonica"
"""Id da alternativa que a forma curta do YAML gera."""

RACIONAL_DA_FORMA_CURTA = "Forma curta do YAML: uma unica alternativa aceitavel."
"""Racional que a forma curta gera.

Entra no hash, como tudo mais. Escrever `accept:` a mao com ESTE id e ESTE
racional produz exatamente o mesmo hash da forma curta; escrever com outro
racional produz outro hash, e esta certo que produza — e outra tarefa.
"""

MINIMO_DE_MEMBROS_DO_GRUPO = 2
"""Grupo de variantes com um membro so nao distingue competencia de sorte."""

FERRAMENTAS_DE_ABSTENCAO = frozenset({"pedir_esclarecimento", "recusar"})
"""Tornam a abstencao detectavel por AST, sem juiz e sem lexico de hedge."""


class Severidade(StrEnum):
    """Gravidade de um problema encontrado pelo lint."""

    ERRO = "erro"
    AVISO = "aviso"


class ProblemaDeLint(BaseModel):
    """Um problema encontrado no dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severidade: Severidade
    regra: str
    task_id: str | None
    mensagem: str

    def __str__(self) -> str:
        """Linha legível para o terminal."""
        alvo = self.task_id or "(dataset)"
        return f"[{self.severidade}] {self.regra} · {alvo}: {self.mensagem}"


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------


def _normalizar_expect(bruto: dict[str, Any], origem: Path) -> dict[str, Any]:
    """Promove a forma curta `calls:` para a forma canônica `accept:`.

    Args:
        bruto: o mapeamento vindo do YAML.
        origem: o arquivo, para a mensagem de erro.

    Returns:
        O mapeamento com `expect.accept` preenchido.

    Raises:
        ValueError: se o YAML trouxer as duas grafias ao mesmo tempo.
    """
    espera = bruto.get("expect")
    if not isinstance(espera, dict) or espera.get("kind") != "tool_call":
        return bruto

    tem_calls = "calls" in espera
    tem_accept = "accept" in espera
    if tem_calls and tem_accept:
        msg = (
            f"{origem}: `expect` traz `calls` e `accept` ao mesmo tempo. "
            "Sao duas grafias da mesma coisa; escolha uma."
        )
        raise ValueError(msg)
    if not tem_calls:
        return bruto

    espera = dict(espera)
    alternativa = {
        "id": ID_DA_FORMA_CURTA,
        "calls": espera.pop("calls"),
        "rationale": RACIONAL_DA_FORMA_CURTA,
    }
    espera["accept"] = [alternativa]
    resultado = dict(bruto)
    resultado["expect"] = espera
    return resultado


def carregar_tarefa(caminho: Path) -> Tarefa:
    """Carrega e valida uma tarefa de um arquivo YAML.

    Args:
        caminho: o arquivo YAML da tarefa.

    Returns:
        A tarefa validada.

    Raises:
        ValueError: se o YAML não descrever um mapeamento.
        ValidationError: se a tarefa não obedecer ao schema.
    """
    bruto = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    if not isinstance(bruto, dict):
        msg = f"{caminho}: o YAML nao descreve um mapeamento de tarefa"
        # TRY004 sugere TypeError por causa do isinstance. Aqui o defeito e de
        # CONTEUDO do arquivo, nao de tipo de argumento: ValueError e o certo.
        raise ValueError(msg)  # noqa: TRY004
    return Tarefa.model_validate(_normalizar_expect(bruto, caminho))


def carregar_diretorio(raiz: Path) -> Iterator[Tarefa]:
    """Carrega recursivamente todas as tarefas sob um diretório.

    A ordem é a alfabética dos caminhos, de propósito: carga determinística
    significa suíte congelada determinística.

    Args:
        raiz: diretório raiz (normalmente `tasks/`).

    Yields:
        Cada tarefa validada.
    """
    for caminho in sorted(raiz.rglob("*.yaml")):
        yield carregar_tarefa(caminho)


# --------------------------------------------------------------------------
# Lint
# --------------------------------------------------------------------------


def _erro(regra: str, task_id: str | None, mensagem: str) -> ProblemaDeLint:
    return ProblemaDeLint(
        severidade=Severidade.ERRO, regra=regra, task_id=task_id, mensagem=mensagem
    )


def _aviso(regra: str, task_id: str | None, mensagem: str) -> ProblemaDeLint:
    return ProblemaDeLint(
        severidade=Severidade.AVISO, regra=regra, task_id=task_id, mensagem=mensagem
    )


def _lint_unicidade(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """Ids e canários são únicos em todo o dataset.

    Canário duplicado arruína o detector de contaminação: se o modelo souber o
    GUID, você não sabe qual das tarefas vazou.
    """
    problemas: list[ProblemaDeLint] = []
    por_id: defaultdict[str, list[str]] = defaultdict(list)
    por_canario: defaultdict[str, list[str]] = defaultdict(list)
    for tarefa in tarefas:
        por_id[tarefa.id].append(tarefa.id)
        por_canario[tarefa.canary_guid].append(tarefa.id)

    problemas.extend(
        _erro("id-unico", ident, f"o id aparece {len(ocorrencias)} vezes no dataset")
        for ident, ocorrencias in sorted(por_id.items())
        if len(ocorrencias) > 1
    )
    problemas.extend(
        _erro(
            "canario-unico",
            None,
            f"o canary_guid '{guid}' e compartilhado por {sorted(ids)}",
        )
        for guid, ids in sorted(por_canario.items())
        if len(ids) > 1
    )
    return problemas


def _lint_proveniencia(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """As tarefas nascem em PT-BR; o par em inglês é derivado delas."""
    return [
        _erro(
            "nasce-em-pt-br",
            tarefa.id,
            f"generated_from e '{tarefa.generated_from}'; o Curupira nao traduz "
            "o BFCL, as tarefas nascem em portugues",
        )
        for tarefa in tarefas
        if tarefa.generated_from is not Locale.PT_BR
    ]


def _lint_paridade(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """`parity: strict` é o que entra no Delta, então é o que mais se verifica."""
    problemas: list[ProblemaDeLint] = []
    pares: defaultdict[str, list[Tarefa]] = defaultdict(list)
    for tarefa in tarefas:
        if tarefa.pair_id is not None:
            pares[tarefa.pair_id].append(tarefa)

    for tarefa in tarefas:
        if tarefa.parity is not Paridade.STRICT:
            continue
        if tarefa.pair_id is None:
            problemas.append(
                _erro("strict-tem-par", tarefa.id, "parity strict exige pair_id preenchido")
            )
            continue
        if not tarefa.parity_notes:
            problemas.append(
                _erro(
                    "strict-declara-o-que-mudou",
                    tarefa.id,
                    "parity strict exige parity_notes dizendo exatamente o que muda "
                    "entre as versoes; sem isso o Delta e uma afirmacao do autor "
                    "sobre o proprio trabalho",
                )
            )

    for pair_id, membros in sorted(pares.items()):
        problemas.extend(_lint_um_par(pair_id, membros))
    return problemas


def _lint_um_par(pair_id: str, membros: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """Verifica um par EN/PT: existe, é completo e é comparável."""
    problemas: list[ProblemaDeLint] = []
    strict = [t for t in membros if t.parity is Paridade.STRICT]
    if not strict:
        return problemas

    locales = {t.locale for t in membros}
    if locales != {Locale.PT_BR, Locale.EN_US}:
        problemas.append(
            _erro(
                "par-completo",
                strict[0].id,
                f"o par '{pair_id}' tem apenas {sorted(locales)}; strict exige as "
                "duas versoes, senao o par nao entra no Delta",
            )
        )
        return problemas

    if len({t.difficulty for t in membros}) > 1:
        problemas.append(
            _erro(
                "par-mesma-dificuldade",
                strict[0].id,
                f"o par '{pair_id}' tem dificuldades diferentes; se a dificuldade "
                "muda, a paridade e localized, nao strict",
            )
        )
    if len({t.track for t in membros}) > 1:
        problemas.append(
            _erro("par-mesma-trilha", strict[0].id, f"o par '{pair_id}' cruza trilhas")
        )
    if len({t.expect.kind for t in membros}) > 1:
        problemas.append(
            _erro(
                "par-mesmo-tipo-de-espera",
                strict[0].id,
                f"o par '{pair_id}' espera comportamentos de tipos diferentes",
            )
        )
    if len({t.input.user_message for t in membros}) == 1:
        problemas.append(
            _erro(
                "par-idiomas-diferentes",
                strict[0].id,
                f"as duas versoes do par '{pair_id}' tem a MESMA mensagem de usuario. "
                "Ou a traducao ficou pendente, ou o par nao deveria ser strict. Par "
                "identico contribui com zero para o Delta por construcao — e zero e "
                "exatamente a direcao que favorece quem publica o numero",
            )
        )
    return problemas


def _chamadas_esperadas(tarefa: Tarefa) -> Iterable[ChamadaEsperada]:
    """Enumera toda `ChamadaEsperada` alcançável a partir da tarefa.

    Cobre `tool_call` (T1, T2) **e** `sequence` (T6). Esquecer a segunda deixaria
    as tarefas multi-turno fora de toda verificação de matcher e de ferramenta —
    justamente as mais complexas, que são as que mais erram.
    """
    espera = tarefa.expect
    if isinstance(espera, EsperaChamadaDeFerramenta):
        for alternativa in espera.accept:
            yield from alternativa.calls
    elif isinstance(espera, EsperaSequencia):
        for passo in espera.steps:
            yield passo.call


def _specs_da_tarefa(tarefa: Tarefa) -> Iterable[tuple[str, EspecificacaoDeArgumento]]:
    """Enumera todo `EspecificacaoDeArgumento` alcançável a partir da tarefa."""
    if isinstance(tarefa.expect, EsperaExtracao):
        yield from tarefa.expect.fields.items()
        return
    for chamada in _chamadas_esperadas(tarefa):
        yield from chamada.arg_specs.items()


def _lint_registro(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """Todo matcher e validador citado no YAML existe no código Python."""
    matchers, validadores = nomes_registrados()
    problemas: list[ProblemaDeLint] = []
    for tarefa in tarefas:
        for campo, spec in _specs_da_tarefa(tarefa):
            if spec.matcher not in matchers:
                problemas.append(
                    _erro(
                        "matcher-registrado",
                        tarefa.id,
                        f"o campo '{campo}' usa o matcher '{spec.matcher}', que nao "
                        "esta registrado em curupira.matchers",
                    )
                )
            nome = spec.params.get("validador")
            if spec.matcher == "por_validador" and (
                not isinstance(nome, str) or nome not in validadores
            ):
                problemas.append(
                    _erro(
                        "validador-registrado",
                        tarefa.id,
                        f"o campo '{campo}' usa por_validador com validador "
                        f"'{nome}', que nao esta registrado em curupira.formatos",
                    )
                )
    return problemas


def _lint_ferramentas(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """As ferramentas citadas existem, e as de abstenção estão oferecidas."""
    problemas: list[ProblemaDeLint] = []
    for tarefa in tarefas:
        oferecidas = {f.name for f in tarefa.context.tools}
        citadas = {chamada.name for chamada in _chamadas_esperadas(tarefa)}
        if isinstance(tarefa.expect, EsperaRecusa):
            # Uma ferramenta proibida que nao existe torna a T5 impossivel de
            # falhar: o ataque "nunca vence" porque nao havia o que chamar, e a
            # tarefa passa sempre sem medir nada.
            citadas |= set(tarefa.expect.forbidden_calls)

        problemas.extend(
            _erro(
                "ferramenta-existe",
                tarefa.id,
                f"o expect cita '{nome}', que nao esta em context.tools",
            )
            for nome in sorted(citadas - oferecidas)
        )

        faltando = FERRAMENTAS_DE_ABSTENCAO - oferecidas
        if faltando:
            problemas.append(
                _aviso(
                    "abstencao-oferecida",
                    tarefa.id,
                    f"sem {sorted(faltando)} em context.tools a abstencao deixa de "
                    "ser detectavel por AST e vira lexico de hedge, que nao e "
                    "equivalente entre idiomas",
                )
            )
    return problemas


def _lint_variantes(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """Grupo de variantes só mede "acertou por sorte" se o gabarito variar."""
    problemas: list[ProblemaDeLint] = []
    grupos: defaultdict[str, list[Tarefa]] = defaultdict(list)
    for tarefa in tarefas:
        if tarefa.variant_group is not None:
            grupos[tarefa.variant_group].append(tarefa)

    for nome, membros in sorted(grupos.items()):
        if len(membros) < MINIMO_DE_MEMBROS_DO_GRUPO:
            problemas.append(
                _aviso(
                    "grupo-tem-membros",
                    membros[0].id,
                    f"o grupo '{nome}' tem um membro so; consistencia_de_grupo nao "
                    "mede nada com um membro",
                )
            )
            continue
        locales = {t.locale for t in membros}
        if len(locales) > 1:
            problemas.append(
                _erro(
                    "grupo-por-locale",
                    membros[0].id,
                    f"o grupo '{nome}' mistura {sorted(locales)}; grupo de variantes "
                    "e escopado por idioma, comparar idiomas e trabalho do pair_id",
                )
            )
        gabaritos = {json.dumps(t.expect.model_dump(mode="json"), sort_keys=True) for t in membros}
        if len(gabaritos) < len(membros):
            problemas.append(
                _erro(
                    "grupo-gabaritos-distintos",
                    membros[0].id,
                    f"o grupo '{nome}' tem membros com o mesmo gabarito; variantes "
                    "com a mesma resposta nao distinguem competencia de sorte",
                )
            )
    return problemas


def _lint_split(tarefas: Sequence[Tarefa]) -> list[ProblemaDeLint]:
    """Held-out vive em repositório privado separado. Nunca aqui."""
    return [
        _erro(
            "held-out-fora-do-publico",
            tarefa.id,
            "tarefa marcada como held_out dentro do dataset publico; o held-out "
            "vive em repositorio privado separado, e so o manifesto (id, trilha, "
            "hash) aparece no publico",
        )
        for tarefa in tarefas
        if tarefa.split is Split.HELD_OUT
    ]


_REGRAS = (
    _lint_unicidade,
    _lint_proveniencia,
    _lint_paridade,
    _lint_registro,
    _lint_ferramentas,
    _lint_variantes,
    _lint_split,
)


def lint_do_dataset(tarefas: Sequence[Tarefa], *, estrito: bool = False) -> list[ProblemaDeLint]:
    """Verifica as invariantes do dataset que o schema sozinho não pega.

    Args:
        tarefas: as tarefas carregadas.
        estrito: se verdadeiro, avisos são promovidos a erro.

    Returns:
        Lista de problemas, ordenada por severidade e depois por regra. Vazia
        significa dataset íntegro.
    """
    problemas: list[ProblemaDeLint] = []
    for regra in _REGRAS:
        problemas.extend(regra(tarefas))

    if estrito:
        problemas = [p.model_copy(update={"severidade": Severidade.ERRO}) for p in problemas]
    problemas.sort(key=lambda p: (p.severidade is not Severidade.ERRO, p.regra, p.task_id or ""))
    return problemas


def tem_erro(problemas: Iterable[ProblemaDeLint]) -> bool:
    """Diz se algum problema é de severidade erro.

    Args:
        problemas: a lista devolvida pelo lint.

    Returns:
        `True` se houver ao menos um erro.
    """
    return any(p.severidade is Severidade.ERRO for p in problemas)
