# ADR 0001 — Registrar decisões de arquitetura como ADR

- **Status:** Aceita
- **Data:** 2026-09-14
- **Decisores:** Rafael Machado Tavares

## Contexto

O Curupira é um benchmark. O produto não é o código: é um **número defensável**.
Um número só é defensável se as escolhas que o produziram forem auditáveis por
alguém que não estava na sala.

Existe ainda uma razão específica deste projeto. Várias decisões de desenho —
o que conta como `parity: strict`, quando um juiz LLM pode ser usado, o que entra
na suíte congelada — são exatamente as que um revisor de artigo vai atacar. Se a
justificativa dessas escolhas viver só no histórico do git ou na cabeça do autor,
a defesa é reconstruída de memória meses depois, e reconstrução de memória é
onde a racionalização entra.

## Decisão

Toda decisão de arquitetura, metodologia de medição ou política do projeto é
registrada como um ADR em `docs/adr/`, numerado sequencialmente, em português.

**Formato:** `NNNN-titulo-em-kebab-case.md`, com as seções:

```
# ADR NNNN — Título
- Status: Proposta | Aceita | Substituída por ADR NNNN | Obsoleta
- Data:
- Decisores:
## Contexto
## Forças em jogo          (opcional, quando há tensão real)
## Opções consideradas     (com + e − de cada uma)
## Decisão
## Consequências           (positivas, negativas, e quando revisitar)
```

**Regras:**

1. **ADR não se edita depois de aceita.** Mudou de ideia? ADR nova que substitui
   a anterior, e a anterior ganha `Status: Substituída por ADR NNNN`. O registro
   é histórico, não estado atual.
2. **Toda ADR lista as opções rejeitadas com os pontos positivos delas.** Uma ADR
   que só elogia a opção escolhida não registra uma decisão, registra uma
   justificativa.
3. **Toda ADR diz quando revisitar.** Uma decisão sem gatilho de revisão vira
   dogma.
4. **Decisão de metodologia de medição é ADR.** Não só decisão de código.

## Consequências

- Positivas: a seção de metodologia do artigo sai quase pronta dos ADRs; um
  contribuidor entende o porquê antes de propor mudar o quê.
- Negativas: custa 20 minutos por decisão, e há a tentação de escrever ADR para
  escolha trivial. Critério: se alguém pode razoavelmente discordar daqui a seis
  meses, é ADR. Senão, é comentário no código.
- Revisitar se: o volume de ADRs passar de ~30 e a navegação virar problema
  (nesse caso, adicionar um índice, não abandonar o registro).
