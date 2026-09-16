"""Fábricas de tarefas para os testes.

Constroem o **mapeamento bruto** (o que sairia do YAML), não o modelo já
validado. Assim os testes exercitam o caminho real: normalização mais validação.
"""

from __future__ import annotations

from typing import Any

MENSAGEM_PT = "faz uma transferencia de 1.234,56 pro Silva"
MENSAGEM_EN = "make a transfer of 1,234.56 to Silva"

MENSAGEM_POR_IDIOMA: dict[str, str] = {"pt-BR": MENSAGEM_PT, "en-US": MENSAGEM_EN}
"""As duas versoes de um par strict tem que diferir de fato.

O lint `par-idiomas-diferentes` recusa um par com a mesma mensagem nos dois
idiomas, e com razao: par identico contribui com zero para o Delta por
construcao. A fabrica tem que produzir dado que passa nas proprias regras do
projeto, senao ela ensina o defeito.
"""

FERRAMENTA_TRANSFERENCIA: dict[str, Any] = {
    "name": "criar_transferencia",
    "description": "Cria uma transferencia bancaria.",
    "parameters": {
        "type": "object",
        "properties": {
            "valor_centavos": {"type": "integer"},
            "favorecido": {"type": "string"},
        },
        "required": ["valor_centavos", "favorecido"],
    },
}

FERRAMENTAS_DE_ABSTENCAO: list[dict[str, Any]] = [
    {
        "name": "pedir_esclarecimento",
        "description": "Use quando faltar informacao.",
        "parameters": {
            "type": "object",
            "properties": {"campo_faltante": {"type": "string"}},
            "required": ["campo_faltante"],
        },
    },
    {
        "name": "recusar",
        "description": "Use quando nao for possivel executar.",
        "parameters": {
            "type": "object",
            "properties": {"motivo": {"type": "string"}},
            "required": ["motivo"],
        },
    },
]


def tarefa_bruta(
    *,
    task_id: str = "t2-fab-0001",
    canary: str = "fab00001-curupira-nao-treinar-neste-dado",
    locale: str = "pt-BR",
    parity: str = "br_only",
    pair_id: str | None = None,
    valor: int = 123456,
    forma_curta: bool = False,
    mensagem: str | None = None,
    **extras: Any,
) -> dict[str, Any]:
    """Monta o mapeamento bruto de uma tarefa de tool calling.

    Args:
        task_id: id da tarefa.
        canary: o canary_guid.
        locale: idioma.
        parity: grau de paridade.
        pair_id: id do par, quando houver.
        valor: o `valor_centavos` esperado — muda o gabarito.
        forma_curta: usa `calls:` em vez de `accept:`.
        mensagem: a mensagem do usuário. Sem argumento, usa a do idioma.
        **extras: campos adicionais mesclados no topo.

    Returns:
        O mapeamento pronto para `carregar_tarefa` ou `Tarefa.model_validate`.
    """
    chamada = {
        "name": "criar_transferencia",
        "args": {"valor_centavos": valor, "favorecido": "Silva"},
        "arg_specs": {
            "valor_centavos": {"matcher": "exact_int"},
            "favorecido": {"matcher": "fuzzy_name", "params": {"threshold": 0.9}},
        },
    }
    if forma_curta:
        expect: dict[str, Any] = {"kind": "tool_call", "calls": [chamada]}
    else:
        expect = {
            "kind": "tool_call",
            "accept": [
                {
                    "id": "canonica",
                    "calls": [chamada],
                    "rationale": "Forma curta do YAML: uma unica alternativa aceitavel.",
                }
            ],
        }

    bruto: dict[str, Any] = {
        "id": task_id,
        "schema_version": 1,
        "task_version": 1,
        "track": "t2_formats",
        "locale": locale,
        "split": "public",
        "difficulty": 2,
        "tags": ["fabrica"],
        "parity": parity,
        "generated_from": "pt-BR",
        "canary_guid": canary,
        "context": {
            "tools": [FERRAMENTA_TRANSFERENCIA, *FERRAMENTAS_DE_ABSTENCAO],
        },
        "input": {"user_message": mensagem or MENSAGEM_POR_IDIOMA.get(locale, MENSAGEM_PT)},
        "expect": expect,
    }
    if pair_id is not None:
        bruto["pair_id"] = pair_id
    bruto.update(extras)
    return bruto


def par_strict(
    pair_id: str = "fab-0001", *, valor: int = 123456, family_id: str | None = "fab-familia"
) -> list[dict[str, Any]]:
    """Monta um par strict completo, PT-BR e EN-US.

    Args:
        pair_id: o id do par.
        valor: o gabarito, idêntico nos dois idiomas.
        family_id: a família das duas versões. `None` monta um par sem família
            declarada, que é o caso que o lint avisa.

    Returns:
        Os dois mapeamentos brutos.
    """
    notas = "So o idioma muda; identificadores mantidos identicos de proposito."
    return [
        tarefa_bruta(
            task_id=f"{pair_id}-pt",
            canary=f"{pair_id}-pt-curupira-nao-treinar",
            locale="pt-BR",
            parity="strict",
            pair_id=pair_id,
            valor=valor,
            parity_notes=notas,
            family_id=family_id,
        ),
        tarefa_bruta(
            task_id=f"{pair_id}-en",
            canary=f"{pair_id}-en-curupira-nao-treinar",
            locale="en-US",
            parity="strict",
            pair_id=pair_id,
            valor=valor,
            parity_notes=notas,
            family_id=family_id,
        ),
    ]
