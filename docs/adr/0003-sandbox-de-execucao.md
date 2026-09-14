# ADR 0003 — Sandbox de execução e separação de privilégio

- **Status:** Aceita
- **Data:** 2026-09-14
- **Decisores:** Rafael Machado Tavares
- **Relacionada a:** ADR 0002 (adaptadores)

## Contexto

A partir da v0.2 o Curupira executa código: a camada de pontuação por execução
roda ferramentas de verdade em sandbox, e a trilha T6 encadeia passos com efeito
colateral. A v0.1 (T1 e T2) **não executa nada** — é pontuação por AST.

Mesmo assim a decisão é registrada agora, porque a separação de privilégio abaixo
é também a barreira que protege as chaves de API, e retrofitar separação de
privilégio significa refazer o runner inteiro.

## Modelo de ameaça

O adversário não é hipotético. São quatro, em ordem de probabilidade:

1. **A saída do modelo.** O modelo escolhe os argumentos das ferramentas. Se uma
   ferramenta executa código, o modelo escreve o código.
2. **Um payload de T5 que funcionou.** A trilha existe para que injeções às vezes
   tenham sucesso. Sucesso significa que o atacante controla o agente.
3. **Um PR de contribuidor** que adiciona uma tarefa ou um gerador.
4. Nós mesmos, por descuido.

**Premissa de projeto: código escolhido por um adversário vai rodar lá dentro.**

## Decisão

### 1. Dois processos, nunca um

```
ORQUESTRADOR (host)                    SANDBOX (container)
- tem as chaves de API                 - executa as ferramentas
- fala HTTPS com o provedor    <--->   - SEM rede (--network=none)
- NAO executa nada que o       socket  - SEM chave de API
  modelo produziu              unix    - SEM acesso ao host
- pontua e grava resultado     JSON    - descartado a cada tarefa
```

Isso não é organização de código, é a barreira. **A chave de API não vaza do
sandbox porque nunca esteve lá.** Quem tem chave não executa; quem executa não
tem chave.

Comunicação por socket unix com protocolo JSON tipado e prefixado por tamanho.
**Não** HTTP (traria um servidor para dentro do sandbox). **Não** filesystem
compartilhado (traria uma condição de corrida e um canal).

### 2. Configuração do container

```
--rm
--network=none                      # não é firewall: não existe interface
--read-only                         # rootfs imutável
--tmpfs /tmp:rw,noexec,nosuid,size=64m
--cap-drop=ALL
--security-opt=no-new-privileges
--security-opt seccomp=default.json # NÃO desabilitar o seccomp
--user 65534:65534                  # nobody
--pids-limit=128
--memory=512m --memory-swap=512m    # swap igual = sem swap
--cpus=1.0
```

### 3. Runtime: gVisor (`runsc`) por padrão no CI

Kernel em espaço de usuário; transforma "escape de container" de um CVE de kernel
em dois problemas independentes. O custo é latência de syscall, irrelevante aqui.
Alternativa aceitável: Podman rootless, para que um escape aterrisse como usuário
sem privilégio.

### 4. Container novo por tarefa

Estado não atravessa tarefas. Sem isso, a tarefa A pode envenenar a tarefa B —
que é um ataque contra o *benchmark*, não contra a máquina, e é o mais provável
de acontecer por acidente.

### 5. Timeout imposto de fora

Kill por relógio de parede, pelo orquestrador. `signal.alarm` dentro do sandbox é
controlado pelo adversário.

### 6. Teto de saída

Ferramenta que devolve 2 GB de texto é DoS contra o harness e contra o orçamento
de tokens. Truncagem com limite duro, registrada no resultado.

### 7. Ferramentas destrutivas são falsas por construção

`criar_transferencia` não move dinheiro: acrescenta uma linha num JSON.
`apagar_arquivos` não apaga: marca. Uma injeção de T5 com 100% de sucesso
consegue escrever numa lista descartável.

Consequência: **o payload de T5 não é perigoso, é uma fixture.** Esse é o
fundamento da política de divulgação em `SECURITY.md`.

## Opções rejeitadas

- **Sandbox por `subprocess` + `resource.setrlimit`.** Simples e sem Docker, mas
  não isola filesystem nem rede, e `setrlimit` não contém um adversário decidido.
  Rejeitada: o modelo de ameaça acima assume código adversário.
- **Rodar tudo num único processo com `restrictedpython` ou AST allowlist.**
  Histórico ruim de escapes; e não protege as chaves, que é metade do objetivo.
- **VM completa por tarefa.** Isolaria melhor, mas o custo de boot por tarefa
  inviabiliza suítes de centenas de tarefas com repetições.

## Consequências

- Positivas: as chaves são protegidas por arquitetura, não por cuidado; o sandbox
  pode ser endurecido sem tocar no orquestrador.
- Negativas: dois processos e um protocolo entre eles é mais complexo que uma
  função; depuração fica mais chata; Docker vira requisito de desenvolvimento
  para a v0.2 em diante.
- Revisitar se: aparecer um runtime de sandbox mantido, com API Python, que
  ofereça as mesmas garantias com menos peça móvel.
