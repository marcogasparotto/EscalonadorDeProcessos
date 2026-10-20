# Simulador de Sistema Operacional Multitarefa de Tempo Compartilhado (Projeto A - v0.6)

Programa *standalone* desenvolvido em Python que simula o comportamento de um escalonador de tempo real e tempo compartilhado, utilizando exclusivamente a biblioteca padrão (Tkinter para a interface gráfica e manipulação nativa para parser e exportação SVG).

---

## Principais Funcionalidades

* **Algoritmos Plugáveis:** Suporte nativo aos algoritmos Rate Monotonic (RM) e Earliest Deadline First (EDF), estruturados por meio de um registro flexível que facilita a inclusão de novas políticas de escalonamento.


* **Mecanismo de Quantum:** Implementação de fatia de tempo para garantir justiça (*fairness*) em tarefas de mesma prioridade através de regime de rodízio (*round-robin*). Quando um job executa `quantum` ticks seguidos e existe outro job pronto com a mesma prioridade do algoritmo (mesmo período no RM, mesmo prazo absoluto no EDF), ele vai para o fim da fila desse nível de prioridade. Sem par de mesma prioridade, ele ganha um quantum novo e continua, para não deixar CPU ociosa nem violar RM/EDF.


* **Eventos no Gantt:** chegada, conclusão, estouro de prazo, sorteio, suspensão, preempção (triângulo roxo) e fim de quantum (letra Q azul), todos com legenda na tela e no SVG.


* **Modo Passo-a-Passo (Debugger):** Permite avançar e retroceder livremente na linha do tempo, acompanhando o estado dinâmico detalhado de cada tarefa por meio de um painel de controle (*TCB dinâmico*).


* **Exportação SVG Nativa:** Gera gráficos de Gantt completos ao término da simulação ou sob demanda, salvando o arquivo vetorial sem depender de bibliotecas externas de terceiros.


* **Edição Interativa:** Permite adicionar, editar ou remover tarefas e alterar parâmetros globais (como quantum e quantidade de CPUs) diretamente pela interface gráfica, reconstruindo a simulação de forma consistente.



---

## Requisitos do Sistema

* Python 3.x
* Nenhuma dependência externa é necessária (utiliza apenas módulos nativos: `tkinter`, `os`, `sys`, `copy`, `random`).



---

## Como Executar

Execute o script principal diretamente no terminal:

```bash
python main.py

```

Na interface gráfica aberta:

1. Clique em **"📂 Carregar arquivo..."** para importar um arquivo de configuração de texto (`.txt`).


2. Utilize os botões de controle (**Avançar passo**, **Retroceder passo**, **Executar tudo**) para navegar pela simulação.


3. Utilize o menu **Parâmetros...** para ajustar o quantum, o número de CPUs ou trocar o algoritmo de escalonamento.



---

## Formato do Arquivo de Configuração (`.txt`)

O arquivo deve seguir a seguinte estrutura baseada em campos separados por ponto e vírgula (`;`):

* **Primeira linha (Cabeçalho):**
```text
algoritmo_escalonamento;quantum;qtde_cpus

```


*Exemplo:* `RM;2;2` (Usa Rate Monotonic, quantum de 2 ticks e 2 CPUs).


* **Linhas seguintes (Tarefas):**
```text
id;cor;ingresso;duracao;periodo;prazo;lista_eventos

```


* **id:** Identificador numérico único da tarefa.


* **cor:** Cor em formato hexadecimal (ex: `#FF0000`).


* **ingresso:** Tick de liberação da primeira instância.


* **duracao:** Tempo de CPU necessário por instância.


* **periodo:** Período de repetição da tarefa (tarefas aperiódicas são ignoradas pelo simulador).


* **prazo:** Prazo relativo ao instante de liberação para conclusão.


* **Cor repetida:** a primeira tarefa fica com a cor; as seguintes recebem uma cor livre da paleta e o usuário é avisado.


* **lista_eventos:** Pares de bloqueio no formato `deslocamento:duracao` separados por vírgula (ex: `2:3,7:1`) ou vazio/`-` se não houver.
