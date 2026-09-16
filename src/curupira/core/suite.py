"""Suíte congelada e errata.

A suíte é o mecanismo principal de comparabilidade: `suites/v0.1.yaml` lista id +
`task_version` + `sha256` de cada tarefa, com `frozen_at`. Tarefa nova nunca
entra em suíte congelada; vai para a próxima. A v0.1 continua rodável para
sempre.

A errata resolve o engessamento sem quebrar a suíte: a suíte **não muda um byte**
e a errata, append-only, lista as tarefas defeituosas. O runner continua rodando
tarefas com errata e gravando o resultado; quem exclui é o agregador, que imprime
os dois números — com e sem errata.

Duas travas contra abuso, que são o ponto:

1. Errata exige defeito demonstrável, com teste que o reproduz. "O modelo X vai
   mal nessa tarefa" não é defeito.
2. **Teto de 5%.** Passando disso, a suíte está morta, não remendada: encerra-se
   e corta-se a próxima. Sem o teto, errata vira edição silenciosa com outro nome.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from curupira import __version__
from curupira.core.enums import Locale, Paridade
from curupira.core.hashing import hash_da_tarefa
from curupira.core.io import gravar_texto
from curupira.core.task import Tarefa

_CFG = ConfigDict(extra="forbid", frozen=True)

TETO_DE_ERRATA = 0.05
"""Fração máxima de tarefas com errata antes de a suíte ser declarada morta."""

MINIMO_DE_ERRATAS_TOLERADAS = 2
"""Piso absoluto, para que o teto não estrangule suíte pequena.

Cinco por cento de quatro tarefas é 0,2: **uma** errata mataria a suíte v0.1.
Isso transformaria o mecanismo desenhado para evitar recongelamento na razão
para recongelar — exatamente o que aconteceu três vezes entre as Entregas 9 e 11.

Acima de quarenta tarefas o piso deixa de valer e o teto relativo volta a
mandar: 5% de sessenta são três, e três gabaritos errados num piloto de sessenta
é motivo legítimo para encerrar a suíte em vez de remendá-la.
"""


class EntradaDeSuite(BaseModel):
    """Uma tarefa congelada numa suíte."""

    model_config = _CFG

    task_id: str
    task_version: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Suite(BaseModel):
    """Uma suíte congelada.

    `delta_subset` é a lista explícita dos `pair_id` que entram no Delta PT-BR.
    Ela é derivada no congelamento e **gravada no arquivo**: derivar toda vez
    deixaria a base do Delta mudar junto com o dataset, que é exatamente o que
    congelar existe para impedir.
    """

    model_config = _CFG

    id: str
    frozen_at: datetime
    curupira_version: str
    entries: tuple[EntradaDeSuite, ...] = Field(min_length=1)
    delta_subset: tuple[str, ...] = ()


class EntradaDeErrata(BaseModel):
    """Uma tarefa marcada como defeituosa. Append-only: nunca se remove."""

    model_config = _CFG

    task_id: str
    task_version: int = Field(ge=1)
    date: date
    defect: str
    """Descrição do defeito. Gabarito errado, tarefa ambígua, matcher que aceita
    resposta incorreta. Desempenho ruim de um modelo NÃO é defeito."""

    test_ref: str
    """Caminho do teste que reproduz o defeito. Sem teste, não entra."""

    replaced_by: str | None = None
    """Id da tarefa que corrige esta, quando existir.

    Corrigir uma tarefa congelada **cria uma tarefa nova**, e este campo liga as
    duas. Sem ele, a história do defeito se perde: o leitor vê uma tarefa
    excluída e não sabe se ela foi consertada ou abandonada. As duas ficam na
    mesma `family_id`, então o bootstrap continua tratando-as como uma
    observação só — que é o que elas são.
    """


class Errata(BaseModel):
    """A errata de uma suíte, versionada."""

    model_config = _CFG

    suite_id: str
    revision: int = Field(ge=0)
    entries: tuple[EntradaDeErrata, ...] = ()


def congelar(tarefas: Sequence[Tarefa], *, suite_id: str) -> Suite:
    """Congela um conjunto de tarefas numa suíte.

    O `delta_subset` sai dos pares que realmente qualificam: `parity: strict`,
    com as duas versões presentes. Um par que não fecha simplesmente não entra —
    o Delta é calculado sobre o que existe, não sobre o que se pretendia.

    Args:
        tarefas: as tarefas a congelar.
        suite_id: o identificador da suíte, ex.: `v0.1`.

    Returns:
        A suíte congelada.

    Raises:
        ValueError: se a lista de tarefas estiver vazia.
    """
    if not tarefas:
        msg = "nao da para congelar uma suite vazia"
        raise ValueError(msg)

    entradas = tuple(
        EntradaDeSuite(
            task_id=tarefa.id,
            task_version=tarefa.task_version,
            sha256=hash_da_tarefa(tarefa),
        )
        for tarefa in sorted(tarefas, key=lambda t: t.id)
    )
    return Suite(
        id=suite_id,
        frozen_at=datetime.now(UTC),
        curupira_version=__version__,
        entries=entradas,
        delta_subset=_derivar_delta_subset(tarefas),
    )


def _derivar_delta_subset(tarefas: Sequence[Tarefa]) -> tuple[str, ...]:
    """Pares strict com as duas versões presentes."""
    por_par: dict[str, set[Locale]] = {}
    for tarefa in tarefas:
        if tarefa.parity is Paridade.STRICT and tarefa.pair_id is not None:
            por_par.setdefault(tarefa.pair_id, set()).add(tarefa.locale)
    return tuple(
        sorted(
            pair_id
            for pair_id, locales in por_par.items()
            if locales == {Locale.PT_BR, Locale.EN_US}
        )
    )


def gravar_suite(suite: Suite, caminho: Path) -> None:
    """Grava a suíte em YAML.

    Args:
        suite: a suíte congelada.
        caminho: o arquivo de destino.
    """
    gravar_texto(
        caminho,
        yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
    )


def carregar_suite(caminho: Path) -> Suite:
    """Carrega uma suíte congelada do disco.

    Args:
        caminho: arquivo YAML da suíte.

    Returns:
        A suíte validada.
    """
    return Suite.model_validate(yaml.safe_load(caminho.read_text(encoding="utf-8")))


def carregar_errata(caminho: Path) -> Errata:
    """Carrega a errata de uma suíte.

    Args:
        caminho: arquivo YAML da errata.

    Returns:
        A errata validada.
    """
    return Errata.model_validate(yaml.safe_load(caminho.read_text(encoding="utf-8")))


SUFIXO_DA_ERRATA = ".errata.yaml"


def carregar_suites(destino: Path) -> list[Suite]:
    """Carrega todas as suítes congeladas de um diretório.

    Args:
        destino: o diretório das suítes.

    Returns:
        As suítes, ordenadas por id. Vazio quando o diretório não existe — um
        dataset ainda sem suíte nenhuma é estado legítimo, não erro.
    """
    if not destino.is_dir():
        return []
    arquivos = sorted(
        caminho for caminho in destino.glob("*.yaml") if not caminho.name.endswith(SUFIXO_DA_ERRATA)
    )
    return sorted((carregar_suite(caminho) for caminho in arquivos), key=lambda s: s.id)


def verificar_suite(suite: Suite, tarefas: Mapping[str, Tarefa]) -> list[str]:
    """Confere o dataset atual contra os hashes congelados na suíte.

    Se alguém alterar uma tarefa sem subir `task_version`, a rodada **falha** em
    vez de produzir número errado em silêncio.

    Args:
        suite: a suíte congelada.
        tarefas: mapa de `task_id` para a tarefa carregada agora.

    Returns:
        Lista de mensagens de divergência. Vazia significa suíte íntegra.
    """
    problemas: list[str] = []
    for entrada in suite.entries:
        tarefa = tarefas.get(entrada.task_id)
        if tarefa is None:
            problemas.append(f"{entrada.task_id}: esta na suite '{suite.id}' e sumiu do dataset")
            continue
        atual = hash_da_tarefa(tarefa)
        if atual == entrada.sha256:
            continue
        if tarefa.task_version == entrada.task_version:
            problemas.append(
                f"{entrada.task_id}: conteudo mudou e task_version continua "
                f"{entrada.task_version}. Isso e edicao silenciosa: suba a versao."
            )
        else:
            problemas.append(
                f"{entrada.task_id}: a suite congelou a versao {entrada.task_version} "
                f"e o dataset esta na {tarefa.task_version}. A suite '{suite.id}' roda "
                "a versao congelada; a nova vai para a proxima suite."
            )
    return problemas


def suite_esta_morta(suite: Suite, errata: Errata) -> bool:
    """Diz se a errata passou do teto de 5% e a suíte deve ser encerrada.

    Args:
        suite: a suíte congelada.
        errata: a errata vigente.

    Returns:
        `True` se a fração de tarefas com errata excede `TETO_DE_ERRATA`.
    """
    afetadas = {entrada.task_id for entrada in errata.entries}
    # `Suite.entries` tem min_length=1, entao nao ha divisao por zero a defender.
    congeladas = {entrada.task_id for entrada in suite.entries}
    quantas = len(afetadas & congeladas)
    tolerado = max(TETO_DE_ERRATA * len(congeladas), MINIMO_DE_ERRATAS_TOLERADAS)
    return quantas > tolerado
