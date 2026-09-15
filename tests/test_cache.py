"""O cache de resposta: chave, isolamento e tolerância a corrupção."""

from __future__ import annotations

from pathlib import Path

from curupira.core.result import ChamadaObservada, RespostaCrua
from curupira.runner.cache import caminho_da_entrada, chave_de_cache, gravar, ler

RESPOSTA = RespostaCrua(
    text=None,
    tool_calls=(ChamadaObservada(name="f", args={"v": 1}, raw_arguments='{"v": 1}'),),
    finish_reason="tool_use",
    prompt_tokens=10,
    completion_tokens=5,
)

BASE = {
    "task_id": "t2-fab-0001",
    "modelo": "modelo-x",
    "corpo_literal": '{"a":1}',
    "temperatura": 0.0,
    "seed": None,
    "repeticao": 0,
}


def _chave(**mudancas: object) -> str:
    argumentos = {**BASE, **mudancas}
    return chave_de_cache(**argumentos)  # type: ignore[arg-type]


def test_chave_e_estavel() -> None:
    assert _chave() == _chave()
    assert len(_chave()) == 64


def test_a_repeticao_muda_a_chave() -> None:
    """Sem isto, as k repetições colapsariam num acerto de cache só.

    E a taxa de não-determinismo — o detector principal de "acertou por sorte" —
    passaria a medir zero por construção.
    """
    assert _chave(repeticao=0) != _chave(repeticao=1)


def test_temperatura_e_seed_mudam_a_chave() -> None:
    assert _chave(temperatura=0.7) != _chave()
    assert _chave(seed=1) != _chave()


def test_modelo_muda_a_chave() -> None:
    assert _chave(modelo="outro") != _chave()


def test_a_tarefa_muda_a_chave() -> None:
    """Duas tarefas com o mesmo corpo nao compartilham resposta.

    O caso que isso previne e o par PT/EN mal traduzido: corpos identicos fariam
    a resposta em portugues servir de resposta em ingles, e o Delta daquele par
    leria zero por construcao.
    """
    assert _chave(task_id="outra") != _chave()


def test_corpo_muda_a_chave() -> None:
    assert _chave(corpo_literal='{"a":2}') != _chave()


def test_grava_e_le(tmp_path: Path) -> None:
    chave = _chave()
    gravar(tmp_path, chave, RESPOSTA)
    assert ler(tmp_path, chave) == RESPOSTA


def test_leitura_sem_entrada_devolve_none(tmp_path: Path) -> None:
    assert ler(tmp_path, _chave()) is None


def test_a_entrada_guarda_so_a_resposta(tmp_path: Path) -> None:
    """Barreira 5: nenhum header vive no cache. `RespostaCrua` não tem onde."""
    chave = _chave()
    gravar(tmp_path, chave, RESPOSTA)
    texto = caminho_da_entrada(tmp_path, chave).read_text(encoding="utf-8")
    for proibido in ("x-api-key", "authorization", "headers"):
        assert proibido not in texto.lower()


def test_entrada_corrompida_e_tratada_como_ausente(tmp_path: Path) -> None:
    """Cache é otimização: derrubar uma rodada paga por causa dele seria pior."""
    chave = _chave()
    gravar(tmp_path, chave, RESPOSTA)
    caminho_da_entrada(tmp_path, chave).write_text("{ isso nao e json", encoding="utf-8")
    assert ler(tmp_path, chave) is None


def test_entrada_com_campo_a_mais_e_recusada(tmp_path: Path) -> None:
    """`extra="forbid"` faz uma entrada adulterada ser recusada na leitura."""
    chave = _chave()
    caminho = caminho_da_entrada(tmp_path, chave)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text('{"text": "oi", "headers": {"x-api-key": "vazou"}}', encoding="utf-8")
    assert ler(tmp_path, chave) is None


def test_regravar_sobrescreve(tmp_path: Path) -> None:
    chave = _chave()
    gravar(tmp_path, chave, RESPOSTA)
    outra = RespostaCrua(text="segunda", finish_reason="end_turn")
    gravar(tmp_path, chave, outra)
    assert ler(tmp_path, chave) == outra


def test_nao_sobra_temporario(tmp_path: Path) -> None:
    """A escrita é atômica: o temporário some no rename."""
    gravar(tmp_path, _chave(), RESPOSTA)
    assert list(tmp_path.rglob("*.tmp")) == []


def test_a_chave_vira_subdiretorio(tmp_path: Path) -> None:
    chave = _chave()
    gravar(tmp_path, chave, RESPOSTA)
    assert caminho_da_entrada(tmp_path, chave).parent.name == chave[:2]
