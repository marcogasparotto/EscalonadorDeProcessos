#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULADOR DE UM SISTEMA OPERACIONAL MULTITAREFA DE TEMPO COMPARTILHADO
 Projeto A - Versão 0.6
================================================================================

Este programa é um único arquivo, autossuficiente (standalone), que utiliza
APENAS a biblioteca padrão do Python (tkinter para a interface gráfica e
manipulação nativa de arquivos/strings para o parser e para a exportação SVG).

--------------------------------------------------------------------------------
PREMISSAS ASSUMIDAS (o enunciado não detalha estes pontos e, por isso, as
decisões de projeto abaixo foram tomadas de forma explícita e documentada,
para que o comportamento do simulador seja previsível e possa ser revisado):

  1) Formato do campo "lista_eventos" (7º campo de cada tarefa no arquivo de
     configuração): pares "deslocamento:duracao" separados por vírgula, por
     exemplo "2:3,7:1". O "deslocamento" é contado em ticks a partir do
     instante de LIBERAÇÃO de CADA instância da tarefa (ou seja, o mesmo
     padrão de bloqueios se repete a cada período). Um campo vazio, "-" ou
     apenas espaços significa "nenhum evento de bloqueio". Ao ser atingido,
     o evento faz a tarefa entrar no estado "suspensa" pela duração indicada,
     mesmo que ela estivesse em execução ou apenas pronta.

  2) Significado do campo "prazo": é RELATIVO ao instante de liberação de
     cada instância. O prazo absoluto de uma instância liberada no tick T é,
     portanto, T + prazo. Esta é a convenção usual em escalonamento de tempo
     real (RM/EDF) e é usada tanto para o algoritmo EDF quanto para a
     detecção de estouro de prazo (deadline miss) em qualquer algoritmo.

  3) Significado do "quantum": é o tempo máximo (em ticks) que uma tarefa
     pode permanecer executando ININTERRUPTAMENTE antes que o escalonador
     seja obrigatoriamente reconsultado. Como RM e EDF, por si só, não têm
     noção de "fatia de tempo" (apenas de prioridade), o quantum é usado
     aqui como o mecanismo de justiça (fairness) do "tempo compartilhado":
     ao expirar, a tarefa perde temporariamente a vantagem do critério de
     desempate nº 1 ("estava executando antes"), permitindo que outra
     tarefa de MESMA prioridade (mesmo período no RM, ou mesmo prazo
     absoluto no EDF) assuma a CPU em regime de rodízio (round-robin).
     Se não houver nenhuma tarefa de prioridade igual/maior disputando,
     a própria tarefa continua executando normalmente.

  4) Ordem de aplicação dos critérios: os 5 critérios de desempate listados
     no enunciado são aplicados SOMENTE quando duas ou mais tarefas empatam
     no critério primário do algoritmo escolhido (menor período no RM, ou
     menor prazo absoluto no EDF) — é exatamente para isso que servem
     "critérios de desempate". A chave de ordenação completa usada é:
         (prioridade_primaria, [1] estava_executando_antes, [2] prazo,
          [3] ingresso, [4] duração, [5] sorteio-apenas-se-ainda-empatado)

  5) Edição de tarefas/parâmetros durante o modo passo-a-passo: como o
     simulador é orientado a eventos discretos (o estado de um tick depende
     de toda a história anterior), uma edição no meio da execução NÃO tenta
     remendar o estado corrente. Em vez disso, o simulador reconstrói TODA
     a linha do tempo do zero com a nova definição da tarefa e reposiciona
     o cursor de exibição no mesmo número de passo em que o usuário estava.
     Isso evita estados internamente inconsistentes e é equivalente, do
     ponto de vista do usuário, a "mudar uma característica da tarefa e ver
     o que teria acontecido".

  6) Atribuição de qual CPU física (CPU0, CPU1, ...) executa qual tarefa
     selecionada é apenas cosmética/de continuidade visual (tenta manter a
     tarefa na mesma CPU quando possível, para reduzir "troca de contexto"
     visual no gráfico). A decisão que realmente implementa RM/EDF e os
     critérios de desempate é QUAIS tarefas são selecionadas para rodar a
     cada instante, não em qual CPU especificamente. Uma CPU sem tarefa
     atribuída é sempre exibida como DESLIGADA (nunca "ociosa"), conforme
     exigido: se há tarefa pronta, nenhuma CPU pode ficar sem uso.

  7) Exportação SVG: o enunciado exige que a exportação ocorra "ao término
     da simulação". Por isso, o SVG completo é gerado AUTOMATICAMENTE assim
     que a simulação chega ao fim (todas as tarefas completam as 10
     instâncias), salvo como "<nome_do_arquivo_de_configuracao>_gantt.svg"
     na mesma pasta do arquivo carregado. Também é possível reexportar a
     qualquer momento (mesmo com a simulação parcial) pelo botão
     "Exportar SVG...".

  8) Tarefas aperiódicas (campo "periodo" vazio, "0" ou "-") não são
     suportadas pelo Projeto A: são identificadas, ignoradas, e um aviso
     claro é mostrado ao usuário ao carregar o arquivo — exatamente como
     pedido no enunciado.

  9) Mecanismo de escalonamento plugável (requisito 4.2): RM e EDF são
     apenas duas entradas registradas em ALGORITMOS_DE_ESCALONAMENTO (topo
     do arquivo), cada uma sendo só uma função "prioridade primária". O
     método `Simulador._escalonar` nunca precisa ser alterado para incluir
     um novo algoritmo — basta chamar `registrar_algoritmo(...)`. O parser
     do arquivo de configuração e o combobox da tela "Parâmetros..." também
     consultam este mesmo registro, então um algoritmo novo aparece em
     ambos automaticamente.

  10) Painel de "estado das tarefas" (requisito 1.5.1): ao lado do gráfico
      de Gantt, uma tabela mostra o TCB dinâmico de cada tarefa (estado,
      CPU, tempo restante, prazo absoluto, instância atual, se o prazo já
      foi perdido) referente ao EXATO passo em que o cursor de exibição
      está posicionado — funcionando como o "debugger" pedido no
      enunciado, inclusive ao retroceder no tempo.
--------------------------------------------------------------------------------

Todo o código abaixo é comentado em português, explicando o que cada parte
faz e por que foi implementada daquela forma.
"""

import os
import sys
import copy
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ==============================================================================
# CONSTANTES DE APRESENTAÇÃO (usadas tanto no Canvas do Tkinter quanto no SVG)
# ==============================================================================
LARGURA_TICK = 26          # largura em pixels de um tick no eixo do tempo
ALTURA_LINHA = 32          # altura em pixels de cada linha (tarefa ou CPU)
MARGEM_ESQUERDA = 140      # espaço reservado à esquerda para os rótulos
MARGEM_TOPO = 40           # espaço reservado no topo para a régua de ticks
COR_GRADE = "#DDDDDD"      # cor das linhas de grade verticais/horizontais
COR_CPU_DESLIGADA = "#B0B0B0"  # cor usada para indicar uma CPU desligada
COR_TEXTO = "#222222"
COR_CHEGADA = "#2E7D32"
COR_DEADLINE_MISS = "#D32F2F"
COR_SORTEIO = "#F9A825"


# ==============================================================================
# CONSTANTES DE ESTILO DA INTERFACE (ttk) — usadas apenas na "casca" da janela
# (barra de ferramentas, status, molduras). Não afetam o desenho do Gantt.
# ==============================================================================
COR_FUNDO_APP = "#F2F4F8"
COR_BARRA_FERRAMENTAS = "#FFFFFF"
COR_ACCENT = "#2F6FED"
COR_ACCENT_HOVER = "#255BC4"
COR_ACCENT_PRESS = "#1E49A0"
COR_TEXTO_CLARO = "#FFFFFF"
COR_SECUNDARIO = "#E9ECF3"
COR_SECUNDARIO_HOVER = "#DCE1EC"
COR_SECUNDARIO_PRESS = "#CDD4E4"
COR_TEXTO_SECUNDARIO = "#1F2A44"
COR_STATUS_BG = "#1F2A44"
COR_STATUS_TEXTO = "#E8ECF5"
COR_BORDA = "#D8DEE9"
FONTE_PADRAO = ("Segoe UI", 10)
FONTE_TITULO = ("Segoe UI", 12, "bold")
FONTE_STATUS = ("Segoe UI", 9)


# ==============================================================================
# 0) REGISTRO PLUGÁVEL DE ALGORITMOS DE ESCALONAMENTO
# ==============================================================================
# Requisito 4.2: o mecanismo de escalonamento deve ser flexível/configurável,
# de modo que NOVOS algoritmos possam ser incluídos sem precisar alterar o
# código da classe Simulador. Para isso, cada algoritmo é representado apenas
# como uma função "prioridade primária": recebe (tarefa, estado_dinamico) e
# devolve um valor comparável, onde MENOR = MAIS prioritário. O restante do
# escalonamento (os 5 critérios de desempate, atribuição de CPU, etc.) é
# comum a todos os algoritmos e fica implementado uma única vez em
# `Simulador._escalonar`.
#
# Para adicionar um algoritmo novo (ex.: Deadline Monotonic), basta chamar
# `registrar_algoritmo(...)` — nenhuma outra parte do simulador precisa mudar,
# nem o parser do arquivo de configuração (que valida contra este registro) nem
# a interface gráfica (que lista as opções deste registro no combobox).
ALGORITMOS_DE_ESCALONAMENTO = {}


def registrar_algoritmo(nome, funcao_prioridade_primaria, descricao=""):
    """
    Registra (ou substitui) um algoritmo de escalonamento.

    `funcao_prioridade_primaria(tarefa, estado_dinamico) -> valor comparável`
    onde MENOR valor significa MAIOR prioridade (é isso que o Python usa
    naturalmente ao ordenar tuplas/listas com `sort`/`min`).

    Exemplo — adicionando um hipotético "Deadline Monotonic" (prioridade fixa
    pelo prazo RELATIVO, e não pelo período como no RM):
        registrar_algoritmo(
            'DM',
            lambda tarefa, et: tarefa.prazo,
            descricao="Deadline Monotonic (prioridade fixa pelo prazo relativo)",
        )
    """
    chave = nome.strip().upper()
    ALGORITMOS_DE_ESCALONAMENTO[chave] = {
        'funcao': funcao_prioridade_primaria,
        'descricao': descricao or chave,
    }


# ---- algoritmos exigidos pelo Projeto A ----
registrar_algoritmo(
    'RM',
    lambda tarefa, et: tarefa.periodo,
    descricao="Rate Monotonic (prioridade fixa: menor período primeiro)",
)
registrar_algoritmo(
    'EDF',
    lambda tarefa, et: et['prazo_abs_atual'],
    descricao="Earliest Deadline First (prioridade dinâmica: menor prazo absoluto primeiro)",
)


# ==============================================================================
# 1) ESTRUTURA DE DADOS: TAREFA (a parte "estática"/definição do TCB)
# ==============================================================================
class Tarefa:
    """
    Guarda os parâmetros ESTÁTICOS de uma tarefa (aqueles que vêm do arquivo
    de configuração ou que o usuário altera pelo editor de tarefas).

    O estado DINÂMICO de execução (quanto tempo falta, se está bloqueada,
    em qual CPU está etc.) NÃO fica aqui — fica em um dicionário separado
    dentro da classe Simulador (`estado_tarefas`), pois esse estado muda a
    cada tick e precisa ser copiado (deepcopy) para o histórico do modo
    passo-a-passo. Manter as duas coisas separadas facilita bastante tanto
    a reconstrução da simulação (quando uma tarefa é editada) quanto a
    navegação livre para frente/trás no tempo.
    """

    def __init__(self, id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos):
        self.id = id_tarefa
        self.cor = cor                  # string "#RRGGBB"
        self.ingresso = ingresso        # tick de chegada da PRIMEIRA instância
        self.duracao = duracao          # tempo de CPU necessário por instância
        self.periodo = periodo          # período entre liberações (> 0 sempre;
                                         # tarefas aperiódicas já são descartadas
                                         # no parser, conforme o Projeto A exige)
        self.prazo = prazo              # prazo RELATIVO à liberação da instância
        self.eventos = eventos          # lista de (deslocamento, duracao_bloqueio)


# ==============================================================================
# 2) FUNÇÕES AUXILIARES DE PARSING (tolerantes a formatação "suja")
# ==============================================================================
def _normalizar_cor(valor):
    """
    Aceita cores como 'FF0000', '#ff0000', ' #FF0000 ' etc. e devolve sempre
    no formato canônico '#RRGGBB' em maiúsculas. Devolve None se a cor for
    inválida, para que quem chamou decida o que fazer (usar cor padrão etc.).
    """
    v = valor.strip()
    if not v:
        return None
    if not v.startswith('#'):
        v = '#' + v
    if len(v) != 7:
        return None
    try:
        int(v[1:], 16)
    except ValueError:
        return None
    return v.upper()


def _parsear_eventos(campo):
    """
    Interpreta o campo "lista_eventos" de uma tarefa (ver PREMISSA 1 no topo
    do arquivo). Formato: "deslocamento:duracao,deslocamento:duracao,...".
    Tokens mal formados são silenciosamente ignorados (o parser deve ser
    tolerante, conforme pedido no enunciado) — apenas os pares válidos são
    aproveitados.
    """
    campo = campo.strip()
    if campo in ('', '-'):
        return []
    eventos = []
    for parte in campo.split(','):
        parte = parte.strip()
        if not parte or ':' not in parte:
            continue
        desloc_str, dur_str = parte.split(':', 1)
        try:
            desloc = int(desloc_str.strip())
            dur = int(dur_str.strip())
        except ValueError:
            continue
        if desloc >= 0 and dur > 0:
            eventos.append((desloc, dur))
    eventos.sort(key=lambda par: par[0])
    return eventos


def carregar_configuracao(caminho):
    """
    Lê e interpreta um arquivo de configuração da simulação.

    Formato esperado (campos separados por ';'):
        linha 1:        algoritmo_escalonamento;quantum;qtde_cpus
        linhas 2..N:    id;cor;ingresso;duracao;periodo;prazo;lista_eventos

    Tolerâncias implementadas (exigidas no enunciado):
      - nomes de algoritmo são tratados de forma "case-insensitive";
      - linhas em branco (ou só com espaços) são ignoradas;
      - um ';' sobrando no final de qualquer linha é tolerado;
      - caminho absoluto ou relativo (relativo ao diretório de trabalho
        atual) — ambos funcionam, pois normalizamos com os.path.abspath;
      - linhas de tarefa mal formadas geram um AVISO e são ignoradas em vez
        de interromper o carregamento inteiro do arquivo.

    Retorna: (algoritmo, quantum, num_cpus, lista_de_tarefas, avisos)
    Lança ValueError (com mensagem amigável) apenas quando o arquivo não
    pode ser interpretado de jeito nenhum (cabeçalho ausente/errado, ou
    nenhuma tarefa válida sobrou depois da filtragem).
    """
    caminho = os.path.abspath(os.path.expanduser(caminho.strip()))
    if not os.path.isfile(caminho):
        raise ValueError(f"Arquivo não encontrado: {caminho}")

    with open(caminho, 'r', encoding='utf-8') as arquivo:
        linhas_brutas = arquivo.readlines()

    # Tolerância: descarta linhas totalmente vazias (ou só com espaços)
    linhas = [linha.strip() for linha in linhas_brutas]
    linhas = [linha for linha in linhas if linha != '']

    if not linhas:
        raise ValueError("O arquivo de configuração está vazio.")

    avisos = []

    # ---------------- linha 1: cabeçalho ----------------
    cabecalho = linhas[0]
    if cabecalho.endswith(';'):
        cabecalho = cabecalho[:-1]
    campos_cabecalho = [c.strip() for c in cabecalho.split(';')]
    if len(campos_cabecalho) < 3:
        raise ValueError(
            "Primeira linha inválida. O formato esperado é: "
            "algoritmo_escalonamento;quantum;qtde_cpus"
        )
    algoritmo_bruto, quantum_bruto, cpus_bruto = campos_cabecalho[:3]

    algoritmo = algoritmo_bruto.strip().upper()
    if algoritmo not in ALGORITMOS_DE_ESCALONAMENTO:
        disponiveis = ', '.join(sorted(ALGORITMOS_DE_ESCALONAMENTO))
        raise ValueError(
            f"Algoritmo de escalonamento desconhecido: '{algoritmo_bruto}'. "
            f"Algoritmos disponíveis: {disponiveis}."
        )

    try:
        quantum = int(quantum_bruto)
        if quantum <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"Quantum inválido na primeira linha: '{quantum_bruto}'.")

    try:
        num_cpus = int(cpus_bruto)
        if num_cpus <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"Quantidade de CPUs inválida na primeira linha: '{cpus_bruto}'.")

    # ---------------- linhas seguintes: tarefas ----------------
    tarefas = []
    ids_vistos = set()

    for numero_linha, linha in enumerate(linhas[1:], start=2):
        linha_sem_ponto_e_virgula_final = linha[:-1] if linha.endswith(';') else linha
        campos = [c.strip() for c in linha_sem_ponto_e_virgula_final.split(';')]

        # Tolerância extra: completa campos faltando em vez de descartar a
        # linha inteira (o 7º campo, lista_eventos, é opcional na prática)
        while len(campos) < 7:
            campos.append('')
        if len(campos) > 7:
            avisos.append(f"Linha {numero_linha}: havia campos em excesso; os extras foram ignorados.")
            campos = campos[:7]

        (id_str, cor_str, ingresso_str, duracao_str,
         periodo_str, prazo_str, eventos_str) = campos

        try:
            id_tarefa = int(id_str)
        except ValueError:
            avisos.append(f"Linha {numero_linha}: ID de tarefa inválido ('{id_str}'); linha ignorada.")
            continue
        if id_tarefa in ids_vistos:
            avisos.append(f"Linha {numero_linha}: ID {id_tarefa} duplicado; linha ignorada.")
            continue

        cor = _normalizar_cor(cor_str)
        if cor is None:
            cor = "#3366CC"
            avisos.append(f"Tarefa {id_tarefa}: cor inválida ('{cor_str}'); usando cor padrão {cor}.")

        try:
            ingresso = int(ingresso_str)
        except ValueError:
            avisos.append(f"Tarefa {id_tarefa}: instante de ingresso inválido; assumindo 0.")
            ingresso = 0

        try:
            duracao = int(duracao_str)
            if duracao <= 0:
                raise ValueError
        except ValueError:
            avisos.append(f"Tarefa {id_tarefa}: duração inválida; tarefa ignorada.")
            continue

        periodo_limpo = periodo_str.strip()
        if periodo_limpo in ('', '0', '-'):
            avisos.append(
                f"Tarefa {id_tarefa} é aperiódica (sem período definido). O Projeto A "
                "não oferece suporte a tarefas aperiódicas; ela foi ignorada na simulação."
            )
            continue
        try:
            periodo = int(periodo_limpo)
            if periodo <= 0:
                raise ValueError
        except ValueError:
            avisos.append(f"Tarefa {id_tarefa}: período inválido; tarefa ignorada.")
            continue

        try:
            prazo = int(prazo_str)
            if prazo <= 0:
                raise ValueError
        except ValueError:
            avisos.append(f"Tarefa {id_tarefa}: prazo inválido; assumindo prazo == período.")
            prazo = periodo

        eventos = _parsear_eventos(eventos_str)

        tarefas.append(Tarefa(id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos))
        ids_vistos.add(id_tarefa)

    if not tarefas:
        raise ValueError("Nenhuma tarefa periódica válida foi encontrada no arquivo.")

    return algoritmo, quantum, num_cpus, tarefas, avisos


# ==============================================================================
# 3) NÚCLEO DO SIMULADOR (KERNEL)
# ==============================================================================
class Simulador:
    """
    Implementa o núcleo (kernel) da simulação: o relógio global orientado a
    eventos, o TCB dinâmico de cada tarefa, o escalonador (RM/EDF + critérios
    de desempate) e o histórico completo de estados usado pelo modo
    passo-a-passo (debugger).

    A ideia central do "tick dinâmico" (pedida no enunciado) é: em vez de
    avançar tick a tick sempre, calculamos qual é o PRÓXIMO instante em que
    ALGO relevante muda (chegada de tarefa, fim de instância, expiração de
    quantum, início/fim de bloqueio, ou o instante exato de um prazo) e
    pulamos diretamente para ele. Isso é o que a função `_calcular_proximo_evento`
    faz, e é ela quem determina o tamanho de cada "passo" da simulação.
    """

    def __init__(self, algoritmo, quantum, num_cpus, tarefas):
        self.algoritmo = algoritmo
        self.quantum = quantum
        self.num_cpus = num_cpus
        self.definicoes = tarefas                      # lista de Tarefa (editável)
        self.tarefas_por_id = {t.id: t for t in tarefas}

        self.tick = 0
        self.estado_tarefas = {}    # id -> dict de estado dinâmico (ver reiniciar)
        self.cpus = []              # lista de {'ligada': bool, 'tarefa': id|None}
        self.historico = []         # lista de "fotografias" completas do sistema
        self.indice_historico = 0   # posição do cursor de exibição dentro do histórico
        self.finalizado = False

    # -------------------------- controle geral --------------------------
    def reiniciar(self):
        """Zera todo o estado dinâmico e recomeça a simulação do tick inicial."""
        self.tick = min(t.ingresso for t in self.definicoes)
        self.estado_tarefas = {
            t.id: {
                'instancias_liberadas': 0,
                'concluidas': 0,
                'liberacao_atual': None,
                'prazo_abs_atual': None,
                'restante_atual': 0,
                'estado': 'nao_chegou',   # nao_chegou | pronta | executando | suspensa | concluida
                'cpu': None,
                'execucao_continua_desde': None,   # usado para controlar o quantum
                'eventos_pendentes': [],
                'bloqueio_fim': None,
                'deadline_perdido': False,
            }
            for t in self.definicoes
        }
        self.cpus = [{'ligada': False, 'tarefa': None} for _ in range(self.num_cpus)]
        self.finalizado = False
        self.historico = []

        eventos = self._processar_tick(self.tick)
        eventos += self._escalonar()
        self._registrar_snapshot(eventos, blocos_intervalo=[])
        self.indice_historico = 0

    def aplicar_edicao_e_reconstruir(self, indice_alvo=None):
        """
        Reconstrói a simulação inteira do zero (após o usuário editar uma
        tarefa ou um parâmetro global como quantum/num_cpus) e reposiciona
        o cursor de exibição no mesmo passo em que o usuário estava (ou no
        último disponível, caso a simulação agora termine mais cedo).
        Ver PREMISSA 5 no cabeçalho do arquivo para a justificativa.
        """
        if indice_alvo is None:
            indice_alvo = self.indice_historico
        self.tarefas_por_id = {t.id: t for t in self.definicoes}
        self.reiniciar()
        while (len(self.historico) - 1) < indice_alvo and not self.finalizado:
            self.passo()
        self.indice_historico = min(indice_alvo, len(self.historico) - 1)

    # -------------------------- avanço no tempo --------------------------
    def _processar_tick(self, tick):
        """
        Aplica, no instante `tick`, todas as transições de estado que não
        dependem da decisão do escalonador: fim de bloqueios, liberação de
        novas instâncias periódicas, início de novos bloqueios programados,
        conclusão de instâncias/tarefas e verificação de estouro de prazo.
        Devolve a lista de eventos ocorridos (para desenhar marcadores).
        """
        eventos = []

        # A) fim de bloqueios/suspensões que estavam em andamento
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['estado'] == 'suspensa' and et['bloqueio_fim'] == tick:
                et['estado'] = 'pronta'
                et['bloqueio_fim'] = None

        # B) liberação de novas instâncias periódicas (até a 10ª, conforme o enunciado)
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['concluidas'] >= 10:
                continue
            proxima_liberacao = t.ingresso + et['instancias_liberadas'] * t.periodo
            if tick == proxima_liberacao:
                et['instancias_liberadas'] += 1
                et['liberacao_atual'] = tick
                et['prazo_abs_atual'] = tick + t.prazo
                et['restante_atual'] = t.duracao
                et['estado'] = 'pronta'
                et['deadline_perdido'] = False
                et['eventos_pendentes'] = list(t.eventos)  # cópia própria desta instância
                et['execucao_continua_desde'] = None
                eventos.append({'tipo': 'chegada', 'tarefa': t.id})

        # C) início de bloqueios programados (lista_eventos) desta instância
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['estado'] in ('pronta', 'executando') and et['liberacao_atual'] is not None:
                deslocamento_atual = tick - et['liberacao_atual']
                pendentes_restantes = []
                ja_disparou_um = False
                for (desloc, dur) in et['eventos_pendentes']:
                    if not ja_disparou_um and desloc == deslocamento_atual:
                        et['estado'] = 'suspensa'
                        et['bloqueio_fim'] = tick + dur
                        et['cpu'] = None
                        et['execucao_continua_desde'] = None
                        ja_disparou_um = True
                        eventos.append({'tipo': 'suspensao', 'tarefa': t.id})
                    else:
                        pendentes_restantes.append((desloc, dur))
                et['eventos_pendentes'] = pendentes_restantes

        # D) conclusão de instância (o tempo restante chegou a zero)
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['estado'] == 'executando' and et['restante_atual'] <= 0:
                et['restante_atual'] = 0
                et['concluidas'] += 1
                et['cpu'] = None
                et['execucao_continua_desde'] = None
                if et['concluidas'] >= 10:
                    et['estado'] = 'concluida'
                    eventos.append({'tipo': 'conclusao_tarefa', 'tarefa': t.id})
                else:
                    et['estado'] = 'nao_chegou'  # aguardando a próxima liberação periódica
                    eventos.append({'tipo': 'conclusao_instancia', 'tarefa': t.id})

        # E) verificação de estouro de prazo (a tarefa continua rodando, só é sinalizada)
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if (et['estado'] in ('pronta', 'executando', 'suspensa')
                    and et['prazo_abs_atual'] is not None
                    and not et['deadline_perdido']
                    and et['restante_atual'] > 0
                    and tick >= et['prazo_abs_atual']):
                et['deadline_perdido'] = True
                eventos.append({'tipo': 'deadline_miss', 'tarefa': t.id})

        return eventos

    def _escalonar(self):
        """
        Decide, a partir do estado corrente (já atualizado por
        `_processar_tick`), quais tarefas ocupam quais CPUs a partir de
        agora. A "prioridade primária" (o que diferencia RM de EDF, ou de
        qualquer outro algoritmo futuro) é obtida do registro plugável
        ALGORITMOS_DE_ESCALONAMENTO — este método em si NUNCA precisa ser
        alterado para adicionar um novo algoritmo. Os 5 critérios de
        desempate exigidos são aplicados na ordem definida no enunciado.
        Devolve a lista de eventos de "sorteio" ocorridos (para exibir o
        marcador gráfico correspondente).
        """
        eventos_sorteio = []

        elegiveis = [
            t.id for t in self.definicoes
            if self.estado_tarefas[t.id]['estado'] in ('pronta', 'executando')
        ]

        if not elegiveis:
            for cpu in self.cpus:
                cpu['ligada'] = False
                cpu['tarefa'] = None
            return eventos_sorteio

        # quem estava executando IMEDIATAMENTE ANTES desta decisão, e para
        # quem, dentre esses, o quantum já expirou (perdendo a "vantagem")
        estava_executando_antes = set()
        quantum_expirou = set()
        for cpu in self.cpus:
            tid = cpu['tarefa']
            if tid is not None:
                estava_executando_antes.add(tid)
                inicio = self.estado_tarefas[tid]['execucao_continua_desde']
                if inicio is not None and (self.tick - inicio) >= self.quantum:
                    quantum_expirou.add(tid)

        # critério primário: delegado inteiramente ao algoritmo registrado em
        # ALGORITMOS_DE_ESCALONAMENTO (ver seção 0, topo do arquivo). Trocar de
        # algoritmo, ou adicionar um novo, nunca exige tocar neste método.
        funcao_prioridade_primaria = ALGORITMOS_DE_ESCALONAMENTO[self.algoritmo]['funcao']

        def chave_prioridade(tid):
            tarefa = self.tarefas_por_id[tid]
            et = self.estado_tarefas[tid]
            prioridade_primaria = funcao_prioridade_primaria(tarefa, et)
            # critério de desempate 1: já estava executando (e não perdeu o quantum)
            tem_vantagem_de_incumbente = (
                tid in estava_executando_antes and tid not in quantum_expirou
            )
            chave_incumbente = 0 if tem_vantagem_de_incumbente else 1
            # critérios de desempate 2, 3 e 4:
            return (prioridade_primaria, chave_incumbente,
                    et['prazo_abs_atual'], tarefa.ingresso, tarefa.duracao)

        elegiveis.sort(key=chave_prioridade)

        n_vagas = min(self.num_cpus, len(elegiveis))

        # critério de desempate 5 (sorteio): só é necessário quando um grupo de
        # tarefas EMPATADAS em todos os critérios anteriores disputa a(s)
        # última(s) vaga(s) disponível(is) e nem todas cabem.
        if 0 < n_vagas < len(elegiveis):
            chave_da_fronteira = chave_prioridade(elegiveis[n_vagas - 1])
            grupo_empatado = [tid for tid in elegiveis if chave_prioridade(tid) == chave_da_fronteira]
            if len(grupo_empatado) > 1:
                indice_inicio_grupo = elegiveis.index(grupo_empatado[0])
                vagas_disputadas = n_vagas - indice_inicio_grupo
                if 0 < vagas_disputadas < len(grupo_empatado):
                    sorteados = random.sample(grupo_empatado, vagas_disputadas)
                    for tid in sorteados:
                        eventos_sorteio.append({'tipo': 'sorteio', 'tarefa': tid})
                    nova_ordem = []
                    usados = 0
                    for tid in elegiveis:
                        if tid in grupo_empatado:
                            if usados < len(sorteados):
                                nova_ordem.append(sorteados[usados])
                                usados += 1
                        else:
                            nova_ordem.append(tid)
                    elegiveis = nova_ordem

        selecionados = elegiveis[:n_vagas]
        nao_selecionados = elegiveis[n_vagas:]

        # ---- atribuição de CPU física: tenta manter continuidade visual ----
        cpu_da_tarefa_antes = {
            cpu['tarefa']: idx for idx, cpu in enumerate(self.cpus) if cpu['tarefa'] is not None
        }
        atribuicoes = {}
        restantes = list(selecionados)
        for tid in list(restantes):
            if tid in cpu_da_tarefa_antes:
                idx = cpu_da_tarefa_antes[tid]
                atribuicoes[idx] = tid
                restantes.remove(tid)
        cpus_livres = [i for i in range(self.num_cpus) if i not in atribuicoes]
        for idx, tid in zip(cpus_livres, restantes):
            atribuicoes[idx] = tid

        for idx, cpu in enumerate(self.cpus):
            tid = atribuicoes.get(idx)
            if tid is None:
                cpu['ligada'] = False
                cpu['tarefa'] = None
                continue
            cpu['ligada'] = True
            cpu['tarefa'] = tid
            et = self.estado_tarefas[tid]
            # começa uma fatia nova (reinicia o contador de quantum) se a
            # tarefa não estava executando nesta MESMA cpu antes, OU se o
            # quantum acabou de expirar (mesmo que ela continue na mesma cpu)
            comeca_fatia_nova = (
                et['estado'] != 'executando' or et['cpu'] != idx or tid in quantum_expirou
            )
            if comeca_fatia_nova:
                et['execucao_continua_desde'] = self.tick
            et['estado'] = 'executando'
            et['cpu'] = idx

        for tid in nao_selecionados:
            et = self.estado_tarefas[tid]
            if et['estado'] == 'executando':
                et['estado'] = 'pronta'
            et['cpu'] = None
            et['execucao_continua_desde'] = None

        return eventos_sorteio

    def _calcular_proximo_evento(self):
        """
        Calcula o próximo tick (estritamente maior que o atual) em que algo
        relevante muda no sistema. É este cálculo que permite "pular" o
        tempo sem precisar avançar tick a tick — ver PREMISSA/explicação no
        topo da classe Simulador.
        """
        candidatos = []
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]

            if et['concluidas'] < 10:
                proxima_liberacao = t.ingresso + et['instancias_liberadas'] * t.periodo
                candidatos.append(proxima_liberacao)

            if et['estado'] == 'executando':
                candidatos.append(self.tick + et['restante_atual'])  # término natural
                if et['execucao_continua_desde'] is not None:
                    candidatos.append(et['execucao_continua_desde'] + self.quantum)

            if et['estado'] == 'suspensa' and et['bloqueio_fim'] is not None:
                candidatos.append(et['bloqueio_fim'])

            if et['estado'] in ('pronta', 'executando') and et['liberacao_atual'] is not None:
                for (desloc, _dur) in et['eventos_pendentes']:
                    candidatos.append(et['liberacao_atual'] + desloc)
                if et['prazo_abs_atual'] is not None and not et['deadline_perdido']:
                    candidatos.append(et['prazo_abs_atual'])

        candidatos = [c for c in candidatos if c > self.tick]
        return min(candidatos) if candidatos else None

    def passo(self):
        """
        Executa UM passo da simulação: avança diretamente até o próximo
        evento relevante (ver `_calcular_proximo_evento`), contabiliza o
        tempo de CPU consumido nesse intervalo por cada tarefa em execução,
        processa as transições de estado no novo tick e roda o escalonador.
        Devolve True se avançou, False se a simulação já estava finalizada.
        """
        if self.finalizado:
            return False

        tick_alvo = self._calcular_proximo_evento()
        if tick_alvo is None:
            self.finalizado = True
            return False

        delta = tick_alvo - self.tick
        blocos = []  # blocos de Gantt referentes ao intervalo [self.tick, tick_alvo)

        for idx_cpu, cpu in enumerate(self.cpus):
            tid = cpu['tarefa']
            if tid is not None:
                et = self.estado_tarefas[tid]
                et['restante_atual'] -= delta
                blocos.append((tid, idx_cpu, self.tick, tick_alvo, 'executando'))

        for t in self.definicoes:
            if self.estado_tarefas[t.id]['estado'] == 'suspensa':
                blocos.append((t.id, None, self.tick, tick_alvo, 'suspensa'))

        self.tick = tick_alvo
        eventos = self._processar_tick(self.tick)
        eventos += self._escalonar()
        self._registrar_snapshot(eventos, blocos)

        if all(self.estado_tarefas[t.id]['estado'] == 'concluida' for t in self.definicoes):
            self.finalizado = True

        return True

    def executar_completo(self, limite_de_seguranca=200_000):
        """
        Executa a simulação inteira sem intervenção humana (Modo Completo),
        até que todas as tarefas completem as 10 instâncias. O limite de
        segurança evita um laço infinito caso alguma configuração inválida
        impeça a simulação de terminar.
        """
        while not self.finalizado:
            if self.tick > limite_de_seguranca:
                raise RuntimeError(
                    "A simulação ultrapassou o limite de segurança de ticks. "
                    "Verifique se todas as tarefas conseguem completar 10 "
                    "instâncias (ex.: duração x tarefas concorrentes não "
                    "deveria exceder a capacidade das CPUs indefinidamente)."
                )
            self.passo()
        self.indice_historico = len(self.historico) - 1

    # -------------------------- navegação (debugger) --------------------------
    def avancar(self):
        """Avança o CURSOR de exibição um passo (calcula um novo passo se necessário)."""
        if self.indice_historico < len(self.historico) - 1:
            self.indice_historico += 1
            return True
        if self.finalizado:
            return False
        avancou = self.passo()
        if avancou:
            self.indice_historico = len(self.historico) - 1
        return avancou

    def retroceder(self):
        """Retrocede o CURSOR de exibição um passo (não recalcula nada)."""
        if self.indice_historico > 0:
            self.indice_historico -= 1
            return True
        return False

    # -------------------------- histórico / Gantt --------------------------
    def _registrar_snapshot(self, eventos, blocos_intervalo):
        """
        Guarda uma "fotografia" completa e independente do estado do sistema
        (cópia profunda) para permitir a navegação livre para frente/trás
        exigida pelo modo passo-a-passo, sem qualquer risco de uma tela
        antiga ser afetada por mutações posteriores do estado ao vivo.
        """
        self.historico.append({
            'tick': self.tick,
            'estado_tarefas': copy.deepcopy(self.estado_tarefas),
            'cpus': copy.deepcopy(self.cpus),
            'eventos': eventos,
            'blocos_intervalo': blocos_intervalo,
        })

    def obter_todos_os_blocos(self, ate_indice=None):
        """
        Junta, em uma única lista, todos os blocos de Gantt (execução e
        suspensão) e todos os eventos pontuais (chegada, conclusão,
        estouro de prazo, sorteio) do início da simulação até o índice do
        histórico indicado (por padrão, até o final). Usado tanto pelo
        desenho no Canvas quanto pela exportação SVG.
        """
        if ate_indice is None:
            ate_indice = len(self.historico) - 1
        blocos, eventos = [], []
        for i in range(1, ate_indice + 1):
            blocos.extend(self.historico[i]['blocos_intervalo'])
            for ev in self.historico[i]['eventos']:
                eventos.append(dict(ev, tick=self.historico[i]['tick']))
        return blocos, eventos


# ==============================================================================
# 4) EXPORTAÇÃO NATIVA EM SVG (pura manipulação de strings, sem bibliotecas)
# ==============================================================================
def exportar_svg(caminho, simulador):
    """
    Gera um arquivo .svg com o Gráfico de Gantt COMPLETO da simulação (do
    primeiro ao último tick, sem nenhum corte de tela), construído
    inteiramente por concatenação de strings — nenhuma biblioteca de
    desenho é usada, conforme exigido no enunciado.
    """
    if not simulador.historico:
        raise ValueError("Não há histórico de simulação para exportar.")

    tick_inicial = simulador.historico[0]['tick']
    tick_final = simulador.historico[-1]['tick']
    duracao_total = max(1, tick_final - tick_inicial)

    ids_tarefas = sorted(simulador.tarefas_por_id.keys(), reverse=True)  # ID menor embaixo
    n_tarefas = len(ids_tarefas)
    n_cpus = simulador.num_cpus

    largura_tick, altura_linha = 22, 28
    margem_esq, margem_topo, espaco_entre_secoes = 150, 50, 20
    n_linhas_legenda = n_tarefas + 6
    altura_legenda = 40 + n_linhas_legenda * 20

    largura_grafico = duracao_total * largura_tick
    altura_tarefas = n_tarefas * altura_linha
    altura_cpus = n_cpus * altura_linha
    largura_total = margem_esq + largura_grafico + 40
    y_cpus_topo = margem_topo + altura_tarefas + espaco_entre_secoes
    altura_total = y_cpus_topo + altura_cpus + altura_legenda

    def x_do_tick(tk_):
        return margem_esq + (tk_ - tick_inicial) * largura_tick

    partes = []
    partes.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura_total}" '
        f'height="{altura_total}" viewBox="0 0 {largura_total} {altura_total}" '
        f'font-family="Helvetica, Arial, sans-serif">'
    )
    partes.append(f'<rect x="0" y="0" width="{largura_total}" height="{altura_total}" fill="#FFFFFF"/>')

    # padrão de hachurado usado para representar tarefas suspensas/bloqueadas
    partes.append(
        '<defs><pattern id="hachura" width="6" height="6" patternTransform="rotate(45)" '
        'patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#000000"/>'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#777777" stroke-width="2"/></pattern></defs>'
    )

    partes.append(
        f'<text x="10" y="22" font-size="16" font-weight="bold" fill="{COR_TEXTO}">'
        f'Grafico de Gantt - Algoritmo {simulador.algoritmo}, quantum={simulador.quantum}, '
        f'{n_cpus} CPU(s)</text>'
    )

    # régua de ticks (uma marca a cada 5 ticks, para não poluir demais)
    y_fim_grade = y_cpus_topo + altura_cpus
    for tk_ in range(tick_inicial, tick_final + 1):
        if (tk_ - tick_inicial) % 5 == 0:
            x = x_do_tick(tk_)
            partes.append(f'<line x1="{x}" y1="{margem_topo}" x2="{x}" y2="{y_fim_grade}" stroke="#DDDDDD"/>')
            partes.append(f'<text x="{x}" y="{margem_topo - 10}" font-size="10" fill="#666666" text-anchor="middle">{tk_}</text>')

    # linhas de tarefas (eixo Y: ID decrescente, ou seja, ID menor mais embaixo)
    y_por_tarefa = {}
    for i, tid in enumerate(ids_tarefas):
        y = margem_topo + i * altura_linha
        y_por_tarefa[tid] = y
        partes.append(f'<text x="{margem_esq - 10}" y="{y + altura_linha/2 + 4}" font-size="12" text-anchor="end" fill="{COR_TEXTO}">Tarefa {tid}</text>')
        partes.append(f'<line x1="{margem_esq}" y1="{y + altura_linha}" x2="{margem_esq + largura_grafico}" y2="{y + altura_linha}" stroke="#EEEEEE"/>')

    # linhas de status das CPUs
    y_por_cpu = {}
    for c in range(n_cpus):
        y = y_cpus_topo + c * altura_linha
        y_por_cpu[c] = y
        partes.append(f'<text x="{margem_esq - 10}" y="{y + altura_linha/2 + 4}" font-size="12" text-anchor="end" fill="{COR_TEXTO}">CPU {c}</text>')
        # fundo cinza = desligada; será sobreposto onde estiver ligada
        partes.append(f'<rect x="{margem_esq}" y="{y+2}" width="{largura_grafico}" height="{altura_linha-4}" fill="{COR_CPU_DESLIGADA}"/>')

    cor_por_tarefa = {t.id: t.cor for t in simulador.definicoes}
    blocos, eventos = simulador.obter_todos_os_blocos()

    # blocos nas linhas de TAREFA (execução colorida / suspensão hachurada)
    for (tid, idx_cpu, ini, fim, estado) in blocos:
        if tid is None or tid not in y_por_tarefa:
            continue
        y = y_por_tarefa[tid]
        x1, x2 = x_do_tick(ini), x_do_tick(fim)
        w = max(1, x2 - x1)
        if estado == 'executando':
            partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="{cor_por_tarefa[tid]}" stroke="#333333" stroke-width="0.5"/>')
            if idx_cpu is not None and w > 20:
                partes.append(f'<text x="{x1 + w/2}" y="{y + altura_linha/2 + 3}" font-size="8" text-anchor="middle" fill="#FFFFFF">CPU{idx_cpu}</text>')
        elif estado == 'suspensa':
            partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="url(#hachura)" stroke="#333333" stroke-width="0.5"/>')

    # blocos nas linhas de CPU (sobrepõe o fundo cinza onde a CPU está ligada)
    for (tid, idx_cpu, ini, fim, estado) in blocos:
        if idx_cpu is None or estado != 'executando':
            continue
        y = y_por_cpu[idx_cpu]
        x1, x2 = x_do_tick(ini), x_do_tick(fim)
        w = max(1, x2 - x1)
        partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="{cor_por_tarefa[tid]}" stroke="#333333" stroke-width="0.5"/>')
        if w > 20:
            partes.append(f'<text x="{x1 + w/2}" y="{y + altura_linha/2 + 3}" font-size="8" text-anchor="middle" fill="#FFFFFF">T{tid}</text>')

    # marcadores de eventos pontuais
    for ev in eventos:
        tid = ev.get('tarefa')
        if tid not in y_por_tarefa:
            continue
        y = y_por_tarefa[tid]
        x = x_do_tick(ev['tick'])
        tipo = ev['tipo']
        if tipo == 'chegada':
            partes.append(f'<polygon points="{x-5},{y+altura_linha-2} {x+5},{y+altura_linha-2} {x},{y+altura_linha-11}" fill="{COR_CHEGADA}"/>')
        elif tipo in ('conclusao_instancia', 'conclusao_tarefa'):
            partes.append(f'<line x1="{x}" y1="{y+2}" x2="{x}" y2="{y+altura_linha-2}" stroke="#000000" stroke-width="2"/>')
            partes.append(f'<circle cx="{x}" cy="{y+6}" r="3" fill="#000000"/>')
        elif tipo == 'deadline_miss':
            partes.append(f'<circle cx="{x}" cy="{y+altura_linha/2}" r="8" fill="none" stroke="{COR_DEADLINE_MISS}" stroke-width="1.5"/>')
            partes.append(f'<text x="{x}" y="{y+altura_linha/2+4}" font-size="12" fill="{COR_DEADLINE_MISS}" font-weight="bold" text-anchor="middle">!</text>')
        elif tipo == 'sorteio':
            partes.append(f'<text x="{x}" y="{y+altura_linha-5}" font-size="11" fill="{COR_SORTEIO}" font-weight="bold" text-anchor="middle">S</text>')

    # ------------------------------ legenda ------------------------------
    y_legenda = y_cpus_topo + altura_cpus + 30
    partes.append(f'<text x="10" y="{y_legenda}" font-size="14" font-weight="bold" fill="{COR_TEXTO}">Legenda</text>')
    x_leg, y_leg = 10, y_legenda + 22

    def linha_legenda(cor_ou_none, hachurado, texto):
        nonlocal y_leg
        if hachurado:
            partes.append(f'<rect x="{x_leg}" y="{y_leg-12}" width="16" height="16" fill="url(#hachura)" stroke="#999999"/>')
        elif cor_ou_none is not None:
            partes.append(f'<rect x="{x_leg}" y="{y_leg-12}" width="16" height="16" fill="{cor_ou_none}" stroke="#999999"/>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">{texto}</text>')
        y_leg += 20

    for t in simulador.definicoes:
        linha_legenda(t.cor, False, f"Tarefa {t.id} executando")
    linha_legenda("#FFFFFF", False, "Pronta na fila (sem cor / bloco vazio)")
    linha_legenda(None, True, "Suspensa / bloqueada")
    linha_legenda(COR_CPU_DESLIGADA, False, "CPU desligada")

    partes.append(f'<polygon points="{x_leg+3},{y_leg+2} {x_leg+13},{y_leg+2} {x_leg+8},{y_leg-7}" fill="{COR_CHEGADA}"/>')
    partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Chegada de nova instância</text>'); y_leg += 20

    partes.append(f'<circle cx="{x_leg+8}" cy="{y_leg-4}" r="3" fill="#000000"/>')
    partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Conclusão de instância/tarefa</text>'); y_leg += 20

    partes.append(f'<circle cx="{x_leg+8}" cy="{y_leg-6}" r="8" fill="none" stroke="{COR_DEADLINE_MISS}" stroke-width="1.5"/>')
    partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Estouro de prazo (deadline miss)</text>'); y_leg += 20

    partes.append(f'<text x="{x_leg+8}" y="{y_leg-2}" font-size="12" fill="{COR_SORTEIO}" font-weight="bold" text-anchor="middle">S</text>')
    partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Escolhida por sorteio (desempate)</text>')

    partes.append('</svg>')

    conteudo = ''.join(partes)
    with open(caminho, 'w', encoding='utf-8') as arquivo:
        arquivo.write(conteudo)
    return caminho


# ==============================================================================
# 5) INTERFACE GRÁFICA (TKINTER)
# ==============================================================================
class Aplicacao(tk.Tk):
    """
    Janela principal. Concentra a barra de ferramentas, o Canvas do
    Gráfico de Gantt (com barras de rolagem, pois a linha do tempo pode
    ficar bem longa), a legenda e a barra de status.
    """

    def __init__(self):
        super().__init__()
        self.title("Simulador de SO Multitarefa - Projeto A (v0.6)")
        self.geometry("1280x800")
        self.minsize(1000, 650)
        self.configure(bg=COR_FUNDO_APP)

        self._configurar_estilo_ttk()

        self.simulador = None
        self.caminho_arquivo_atual = None
        self.reproducao_automatica = False
        self.svg_exportado_automaticamente = False

        self._montar_barra_de_ferramentas()
        self._montar_area_status()
        self._montar_area_gantt()
        self._montar_area_legenda()

    # --------------------------- estilo visual (ttk) ---------------------------
    def _configurar_estilo_ttk(self):
        """
        Define uma aparência mais moderna e consistente para os widgets ttk
        (botões, separadores, combobox, barras de rolagem) usados na "casca"
        da janela. O tema base 'clam' é escolhido por permitir customização
        de cores plana (sem relevo 3D antiquado); se não estiver disponível
        na plataforma, o tema padrão do sistema é mantido sem erro.
        """
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass

        estilo.configure("Toolbar.TFrame", background=COR_BARRA_FERRAMENTAS)

        estilo.configure(
            "Accent.TButton",
            font=FONTE_PADRAO,
            padding=(12, 7),
            background=COR_ACCENT,
            foreground=COR_TEXTO_CLARO,
            borderwidth=0,
            relief="flat",
        )
        estilo.map(
            "Accent.TButton",
            background=[("pressed", COR_ACCENT_PRESS), ("active", COR_ACCENT_HOVER)],
        )

        estilo.configure(
            "Secondary.TButton",
            font=FONTE_PADRAO,
            padding=(12, 7),
            background=COR_SECUNDARIO,
            foreground=COR_TEXTO_SECUNDARIO,
            borderwidth=0,
            relief="flat",
        )
        estilo.map(
            "Secondary.TButton",
            background=[("pressed", COR_SECUNDARIO_PRESS), ("active", COR_SECUNDARIO_HOVER)],
        )

        estilo.configure("Status.TLabel", background=COR_STATUS_BG, foreground=COR_STATUS_TEXTO,
                          font=FONTE_STATUS, padding=(12, 7))
        estilo.configure("TCombobox", padding=4, font=FONTE_PADRAO)
        estilo.configure("TSeparator", background=COR_BORDA)
        estilo.configure("Treeview", font=FONTE_PADRAO, rowheight=24,
                          background="#FFFFFF", fieldbackground="#FFFFFF")
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                          background=COR_SECUNDARIO, foreground=COR_TEXTO_SECUNDARIO)
        estilo.map("Treeview.Heading", background=[("active", COR_SECUNDARIO_HOVER)])

    # --------------------------- montagem da UI ---------------------------
    def _montar_barra_de_ferramentas(self):
        barra = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 10))
        barra.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(barra, text="📂 Carregar arquivo...", style="Accent.TButton",
                   command=self.carregar_arquivo).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(barra, text="⚙ Parâmetros...", style="Secondary.TButton",
                   command=self.editar_parametros).pack(side=tk.LEFT, padx=6)
        ttk.Separator(barra, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        ttk.Button(barra, text="⏩ Executar tudo (Modo Completo)", style="Accent.TButton",
                   command=self.executar_modo_completo).pack(side=tk.LEFT, padx=6)
        self.botao_reproduzir = ttk.Button(barra, text="▶ Reproduzir", style="Secondary.TButton",
                                            command=self.alternar_reproducao)
        self.botao_reproduzir.pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="⏮ Retroceder passo", style="Secondary.TButton",
                   command=self.retroceder_passo).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Avançar passo ⏭", style="Secondary.TButton",
                   command=self.avancar_passo).pack(side=tk.LEFT, padx=6)
        ttk.Separator(barra, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        ttk.Button(barra, text="✎ Editar tarefa...", style="Secondary.TButton",
                   command=self.abrir_editor_de_tarefa).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="💾 Exportar SVG...", style="Secondary.TButton",
                   command=self.exportar_para_svg).pack(side=tk.LEFT, padx=6)

    def _montar_area_status(self):
        self.rotulo_status = ttk.Label(self, text="Nenhum arquivo carregado.", anchor="w",
                                        style="Status.TLabel")
        self.rotulo_status.pack(side=tk.TOP, fill=tk.X)

    def _montar_area_gantt(self):
        moldura_externa = tk.Frame(self, bg=COR_FUNDO_APP, padx=10, pady=8)
        moldura_externa.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        divisor = ttk.PanedWindow(moldura_externa, orient=tk.HORIZONTAL)
        divisor.pack(fill=tk.BOTH, expand=True)

        moldura_gantt = tk.Frame(divisor, bg=COR_BORDA, bd=1)
        self.canvas_gantt = tk.Canvas(moldura_gantt, bg="white", highlightthickness=0)
        barra_v = ttk.Scrollbar(moldura_gantt, orient=tk.VERTICAL, command=self.canvas_gantt.yview)
        barra_h = ttk.Scrollbar(moldura_gantt, orient=tk.HORIZONTAL, command=self.canvas_gantt.xview)
        self.canvas_gantt.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)

        self.canvas_gantt.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h.grid(row=1, column=0, sticky="ew")
        moldura_gantt.rowconfigure(0, weight=1)
        moldura_gantt.columnconfigure(0, weight=1)

        moldura_painel = tk.Frame(divisor, bg=COR_BORDA, bd=1)
        self._montar_painel_tarefas(moldura_painel)

        divisor.add(moldura_gantt, weight=4)
        divisor.add(moldura_painel, weight=1)

    def _montar_painel_tarefas(self, container):
        """
        Painel "debugger" (requisito 1.5.1): mostra, tarefa por tarefa, o
        estado dinâmico corrente no exato passo em que o cursor de exibição
        está posicionado — estado (pronta/executando/suspensa/concluída),
        CPU atual, tempo restante da instância, prazo absoluto, qual
        instância está em curso e se o prazo já foi perdido. É repopulado a
        cada mudança de estado por `_atualizar_painel_tarefas`, em conjunto
        com o redesenho do gráfico de Gantt.
        """
        cabecalho = tk.Frame(container, bg=COR_BARRA_FERRAMENTAS)
        cabecalho.pack(side=tk.TOP, fill=tk.X)
        tk.Label(cabecalho, text="Estado das tarefas", bg=COR_BARRA_FERRAMENTAS,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=10, pady=8)

        colunas = ("estado", "cpu", "restante", "prazo_abs", "instancia", "deadline")
        self.tabela_tarefas = ttk.Treeview(container, columns=colunas, show="tree headings", height=10)
        self.tabela_tarefas.heading("#0", text="Tarefa")
        self.tabela_tarefas.column("#0", width=70, anchor="w")
        titulos = {
            "estado": "Estado", "cpu": "CPU", "restante": "Falta",
            "prazo_abs": "Prazo abs.", "instancia": "Inst.", "deadline": "Prazo?",
        }
        larguras = {"estado": 82, "cpu": 42, "restante": 48, "prazo_abs": 68, "instancia": 44, "deadline": 56}
        for col in colunas:
            self.tabela_tarefas.heading(col, text=titulos[col])
            self.tabela_tarefas.column(col, width=larguras[col], anchor="center")
        self.tabela_tarefas.tag_configure("deadline_perdido", foreground=COR_DEADLINE_MISS)
        self.tabela_tarefas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    def _montar_area_legenda(self):
        moldura = tk.Frame(self, bg=COR_BORDA)
        moldura.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas_legenda = tk.Canvas(moldura, height=92, bg="#FCFCFD", highlightthickness=0)
        self.canvas_legenda.pack(fill=tk.X, padx=1, pady=(1, 0))

    # --------------------------- ações da barra ---------------------------
    def carregar_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo de configuração (.txt)",
            filetypes=[("Arquivos de texto", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if caminho:
            self._carregar_arquivo_de_caminho(caminho)

    def _carregar_arquivo_de_caminho(self, caminho):
        try:
            algoritmo, quantum, num_cpus, tarefas, avisos = carregar_configuracao(caminho)
        except ValueError as erro:
            messagebox.showerror("Erro ao carregar arquivo", str(erro))
            return

        self.simulador = Simulador(algoritmo, quantum, num_cpus, tarefas)
        self.simulador.reiniciar()
        self.caminho_arquivo_atual = caminho
        self.svg_exportado_automaticamente = False

        self._apos_mudanca_de_estado()
        self.desenhar_legenda()

        if avisos:
            messagebox.showwarning("Avisos ao carregar o arquivo", "\n".join(avisos))

    def editar_parametros(self):
        """
        Janela de parâmetros globais da simulação: quantum, quantidade de
        CPUs e o ALGORITMO de escalonamento (requisito 3.1 — o algoritmo deve
        poder ser trocado tanto antes quanto durante a execução). As opções
        de algoritmo mostradas no combobox vêm diretamente do registro
        plugável ALGORITMOS_DE_ESCALONAMENTO: qualquer algoritmo novo
        registrado (ver seção 0 do arquivo) aparece aqui automaticamente,
        sem qualquer alteração nesta função.
        """
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Parâmetros da simulação")
        janela.geometry("380x260")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        tk.Label(janela, text="Parâmetros da simulação", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 10))

        tk.Label(janela, text="Algoritmo:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=1, column=0, sticky="w", padx=16, pady=6)
        nomes_algoritmos = sorted(ALGORITMOS_DE_ESCALONAMENTO.keys())
        variavel_algoritmo = tk.StringVar(value=self.simulador.algoritmo)
        combo_algoritmo = ttk.Combobox(janela, textvariable=variavel_algoritmo,
                                        values=nomes_algoritmos, state="readonly", width=22)
        combo_algoritmo.grid(row=1, column=1, padx=16, pady=6, sticky="ew")

        rotulo_descricao = tk.Label(janela, text="", bg=COR_FUNDO_APP, fg="#555555",
                                     font=("Segoe UI", 8), wraplength=340, justify="left")
        rotulo_descricao.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))

        def atualizar_descricao(*_args):
            info = ALGORITMOS_DE_ESCALONAMENTO.get(variavel_algoritmo.get())
            rotulo_descricao.config(text=info['descricao'] if info else "")

        combo_algoritmo.bind("<<ComboboxSelected>>", atualizar_descricao)
        atualizar_descricao()

        tk.Label(janela, text="Quantum:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=3, column=0, sticky="w", padx=16, pady=6)
        entrada_quantum = tk.Entry(janela, width=10, font=FONTE_PADRAO, relief="solid", bd=1)
        entrada_quantum.insert(0, str(self.simulador.quantum))
        entrada_quantum.grid(row=3, column=1, padx=16, pady=6, sticky="w")

        tk.Label(janela, text="Quantidade de CPUs:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=4, column=0, sticky="w", padx=16, pady=6)
        entrada_cpus = tk.Entry(janela, width=10, font=FONTE_PADRAO, relief="solid", bd=1)
        entrada_cpus.insert(0, str(self.simulador.num_cpus))
        entrada_cpus.grid(row=4, column=1, padx=16, pady=6, sticky="w")

        janela.columnconfigure(1, weight=1)

        def aplicar():
            try:
                novo_quantum = int(entrada_quantum.get())
                novo_num_cpus = int(entrada_cpus.get())
                if novo_quantum <= 0 or novo_num_cpus <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Erro", "Quantum e quantidade de CPUs devem ser inteiros positivos.",
                    parent=janela,
                )
                return

            self.simulador.algoritmo = variavel_algoritmo.get()
            self.simulador.quantum = novo_quantum
            self.simulador.num_cpus = novo_num_cpus
            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            janela.destroy()

        ttk.Button(janela, text="Aplicar", style="Accent.TButton", command=aplicar).grid(
            row=5, column=0, columnspan=2, pady=18)

    def executar_modo_completo(self):
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return
        try:
            self.simulador.executar_completo()
        except RuntimeError as erro:
            messagebox.showerror("Erro na simulação", str(erro))
            return
        self._apos_mudanca_de_estado()
        messagebox.showinfo(
            "Simulação concluída",
            f"Simulação concluída no tick {self.simulador.tick}.\n"
            "O gráfico de Gantt completo foi exportado automaticamente em SVG.",
        )

    def alternar_reproducao(self):
        if self.simulador is None:
            return
        self.reproducao_automatica = not self.reproducao_automatica
        self.botao_reproduzir.config(text="⏸ Pausar" if self.reproducao_automatica else "▶ Reproduzir")
        if self.reproducao_automatica:
            self._tick_de_reproducao()

    def _tick_de_reproducao(self):
        if not self.reproducao_automatica or self.simulador is None:
            return
        avancou = self.simulador.avancar()
        self._apos_mudanca_de_estado()
        if not avancou:
            self.reproducao_automatica = False
            self.botao_reproduzir.config(text="▶ Reproduzir")
            return
        self.after(350, self._tick_de_reproducao)

    def avancar_passo(self):
        if self.simulador is None:
            return
        try:
            self.simulador.avancar()
        except RuntimeError as erro:
            messagebox.showerror("Erro na simulação", str(erro))
            return
        self._apos_mudanca_de_estado()

    def retroceder_passo(self):
        if self.simulador is None:
            return
        self.simulador.retroceder()
        self._apos_mudanca_de_estado()

    def abrir_editor_de_tarefa(self):
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Editar tarefa")
        janela.geometry("400x430")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        cabecalho = tk.Frame(janela, bg=COR_FUNDO_APP)
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 4))
        tk.Label(cabecalho, text="Editar tarefa", bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO,
                 font=FONTE_TITULO).pack(anchor="w")

        tk.Label(janela, text="Tarefa:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=1, column=0, sticky="w", padx=16, pady=6)
        ids = sorted(self.simulador.tarefas_por_id.keys())
        variavel_id = tk.StringVar(value=str(ids[0]))
        combo = ttk.Combobox(janela, textvariable=variavel_id, values=[str(i) for i in ids], state="readonly")
        combo.grid(row=1, column=1, padx=16, pady=6, sticky="ew")

        campos = {}
        rotulos = [
            ("cor", "Cor (#RRGGBB):"),
            ("ingresso", "Ingresso:"),
            ("duracao", "Duração:"),
            ("periodo", "Período:"),
            ("prazo", "Prazo:"),
            ("eventos", "Eventos (desloc:dur,...):"),
        ]
        for i, (chave, texto) in enumerate(rotulos, start=2):
            tk.Label(janela, text=texto, bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
                row=i, column=0, sticky="w", padx=16, pady=6)
            entrada = tk.Entry(janela, width=26, font=FONTE_PADRAO, relief="solid", bd=1)
            entrada.grid(row=i, column=1, padx=16, pady=6, sticky="ew")
            campos[chave] = entrada
        janela.columnconfigure(1, weight=1)

        def carregar_valores(*_args):
            tarefa = self.simulador.tarefas_por_id[int(variavel_id.get())]
            valores = {
                "cor": tarefa.cor,
                "ingresso": str(tarefa.ingresso),
                "duracao": str(tarefa.duracao),
                "periodo": str(tarefa.periodo),
                "prazo": str(tarefa.prazo),
                "eventos": ",".join(f"{d}:{dur}" for d, dur in tarefa.eventos),
            }
            for chave, valor in valores.items():
                campos[chave].delete(0, tk.END)
                campos[chave].insert(0, valor)

        combo.bind("<<ComboboxSelected>>", carregar_valores)
        carregar_valores()

        def aplicar():
            tarefa = self.simulador.tarefas_por_id[int(variavel_id.get())]
            cor = _normalizar_cor(campos["cor"].get())
            if cor is None:
                messagebox.showerror("Erro", "Cor inválida. Use o formato #RRGGBB.", parent=janela)
                return
            try:
                ingresso = int(campos["ingresso"].get())
                duracao = int(campos["duracao"].get())
                periodo = int(campos["periodo"].get())
                prazo = int(campos["prazo"].get())
                if duracao <= 0 or periodo <= 0 or prazo <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Erro",
                    "Ingresso deve ser inteiro (>= 0); duração, período e prazo devem ser inteiros positivos.",
                    parent=janela,
                )
                return
            eventos = _parsear_eventos(campos["eventos"].get())

            tarefa.cor = cor
            tarefa.ingresso = ingresso
            tarefa.duracao = duracao
            tarefa.periodo = periodo
            tarefa.prazo = prazo
            tarefa.eventos = eventos

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        ttk.Button(janela, text="Aplicar", style="Accent.TButton", command=aplicar).grid(
            row=len(rotulos) + 2, column=0, columnspan=2, pady=18)

    def exportar_para_svg(self):
        if self.simulador is None or not self.simulador.historico:
            messagebox.showinfo("Aviso", "Carregue e execute (ao menos parcialmente) uma simulação primeiro.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".svg",
            filetypes=[("Imagem SVG", "*.svg")],
            initialfile="gantt_simulacao.svg",
        )
        if not caminho:
            return
        try:
            exportar_svg(caminho, self.simulador)
        except Exception as erro:  # noqa: BLE001 - queremos capturar qualquer falha de I/O e mostrar ao usuário
            messagebox.showerror("Erro ao exportar", str(erro))
            return
        messagebox.showinfo("Exportado com sucesso", f"Gráfico de Gantt exportado para:\n{caminho}")

    def _exportar_svg_automaticamente(self):
        if self.caminho_arquivo_atual:
            base, _ext = os.path.splitext(self.caminho_arquivo_atual)
        else:
            base = os.path.join(os.getcwd(), "simulacao")
        caminho = base + "_gantt.svg"
        try:
            exportar_svg(caminho, self.simulador)
            self.rotulo_status.config(text=self.rotulo_status.cget("text") + f"   |   SVG salvo automaticamente em: {caminho}")
        except Exception:
            pass  # a exportação automática não deve interromper a simulação em caso de falha de disco, etc.

    # --------------------------- atualização de tela ---------------------------
    def _apos_mudanca_de_estado(self):
        """
        Ponto único chamado depois de qualquer ação que altere o estado da
        simulação (carregar, avançar, retroceder, editar, executar tudo).
        Atualiza a barra de status, redesenha o Gantt e, se a simulação
        acabou de terminar, dispara a exportação SVG automática (uma única
        vez por simulação, conforme a PREMISSA 7 do cabeçalho).
        """
        self._atualizar_status()
        self._atualizar_painel_tarefas()
        self.desenhar_gantt()
        if (self.simulador is not None and self.simulador.finalizado
                and self.simulador.indice_historico == len(self.simulador.historico) - 1
                and not self.svg_exportado_automaticamente):
            self._exportar_svg_automaticamente()
            self.svg_exportado_automaticamente = True

    def _atualizar_status(self):
        s = self.simulador
        if s is None:
            self.rotulo_status.config(text="Nenhum arquivo carregado.")
            return
        atual = s.historico[s.indice_historico]
        texto = (
            f"Arquivo: {os.path.basename(self.caminho_arquivo_atual)}   |   "
            f"Algoritmo: {s.algoritmo}   |   Quantum: {s.quantum}   |   CPUs: {s.num_cpus}   |   "
            f"Tick atual: {atual['tick']}   |   Passo {s.indice_historico + 1} de {len(s.historico)}"
        )
        if s.finalizado and s.indice_historico == len(s.historico) - 1:
            texto += "   |   SIMULAÇÃO FINALIZADA"
        self.rotulo_status.config(text=texto)

    def _atualizar_painel_tarefas(self):
        """
        Repopula o painel "debugger" com o estado dinâmico de cada tarefa
        exatamente no passo em que o cursor de exibição (`indice_historico`)
        está posicionado — e não necessariamente no estado "ao vivo" mais
        recente do simulador, para que retroceder no tempo também retroceda
        o que é mostrado aqui.
        """
        tabela = self.tabela_tarefas
        for item in tabela.get_children():
            tabela.delete(item)

        s = self.simulador
        if s is None:
            return

        snapshot = s.historico[s.indice_historico]
        estado_tarefas = snapshot['estado_tarefas']
        cpus = snapshot['cpus']

        rotulos_estado = {
            'nao_chegou': 'Não chegou',
            'pronta': 'Pronta',
            'executando': 'Executando',
            'suspensa': 'Suspensa',
            'concluida': 'Concluída',
        }

        for tid in sorted(s.tarefas_por_id.keys()):
            et = estado_tarefas[tid]
            estado_legivel = rotulos_estado.get(et['estado'], et['estado'])

            cpu_texto = "—"
            if et['cpu'] is not None and et['cpu'] < len(cpus):
                cpu_texto = f"CPU{et['cpu']}"

            restante_texto = str(et['restante_atual']) if et['estado'] in (
                'pronta', 'executando', 'suspensa') else "—"
            prazo_texto = str(et['prazo_abs_atual']) if et['prazo_abs_atual'] is not None else "—"
            instancia_texto = f"{et['instancias_liberadas']}/10"
            deadline_texto = "SIM" if et['deadline_perdido'] else "não"

            tags = ("deadline_perdido",) if et['deadline_perdido'] else ()
            tabela.insert(
                "", "end", text=f"Tarefa {tid}",
                values=(estado_legivel, cpu_texto, restante_texto, prazo_texto,
                        instancia_texto, deadline_texto),
                tags=tags,
            )

    def desenhar_gantt(self):
        canvas = self.canvas_gantt
        canvas.delete("all")
        s = self.simulador
        if s is None:
            return

        ids_tarefas = sorted(s.tarefas_por_id.keys(), reverse=True)  # ID menor mais próximo do eixo X
        n_tarefas = len(ids_tarefas)
        n_cpus = s.num_cpus

        tick_inicial = s.historico[0]['tick']
        tick_atual = s.historico[s.indice_historico]['tick']
        duracao = max(1, tick_atual - tick_inicial)

        largura_total = MARGEM_ESQUERDA + duracao * LARGURA_TICK + 40
        altura_total = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA + 20
        canvas.configure(scrollregion=(0, 0, largura_total, altura_total))

        def x_do_tick(tk_):
            return MARGEM_ESQUERDA + (tk_ - tick_inicial) * LARGURA_TICK

        y_fim_grade = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA
        for tk_ in range(tick_inicial, tick_atual + 1):
            if (tk_ - tick_inicial) % 5 == 0:
                x = x_do_tick(tk_)
                canvas.create_line(x, MARGEM_TOPO, x, y_fim_grade, fill=COR_GRADE)
                canvas.create_text(x, MARGEM_TOPO - 12, text=str(tk_), font=("Helvetica", 8), fill="#666666")

        y_por_tarefa = {}
        for i, tid in enumerate(ids_tarefas):
            y = MARGEM_TOPO + i * ALTURA_LINHA
            y_por_tarefa[tid] = y
            canvas.create_text(MARGEM_ESQUERDA - 10, y + ALTURA_LINHA / 2, text=f"Tarefa {tid}", anchor="e", font=("Helvetica", 10))
            canvas.create_line(MARGEM_ESQUERDA, y + ALTURA_LINHA, largura_total - 40, y + ALTURA_LINHA, fill=COR_GRADE)

        y_cpus_topo = MARGEM_TOPO + n_tarefas * ALTURA_LINHA
        y_por_cpu = {}
        for cidx in range(n_cpus):
            y = y_cpus_topo + cidx * ALTURA_LINHA
            y_por_cpu[cidx] = y
            canvas.create_text(MARGEM_ESQUERDA - 10, y + ALTURA_LINHA / 2, text=f"CPU {cidx}", anchor="e", font=("Helvetica", 10))
            canvas.create_rectangle(
                MARGEM_ESQUERDA, y + 3, MARGEM_ESQUERDA + duracao * LARGURA_TICK, y + ALTURA_LINHA - 3,
                fill=COR_CPU_DESLIGADA, outline="",
            )

        blocos, eventos = s.obter_todos_os_blocos(ate_indice=s.indice_historico)

        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if tid is None or tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            if estado == 'executando':
                canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3, fill=s.tarefas_por_id[tid].cor, outline="#333333")
                if idx_cpu is not None and (x2 - x1) > 24:
                    canvas.create_text((x1 + x2) / 2, y + ALTURA_LINHA / 2, text=f"CPU{idx_cpu}", fill="white", font=("Helvetica", 7))
            elif estado == 'suspensa':
                canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3, fill="black", stipple="gray50", outline="#333333")

        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if idx_cpu is None or estado != 'executando':
                continue
            y = y_por_cpu[idx_cpu]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3, fill=s.tarefas_por_id[tid].cor, outline="#333333")

        for ev in eventos:
            tid = ev.get('tarefa')
            if tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x = x_do_tick(ev['tick'])
            tipo = ev['tipo']
            if tipo == 'chegada':
                canvas.create_polygon(x - 5, y + ALTURA_LINHA - 2, x + 5, y + ALTURA_LINHA - 2, x, y + ALTURA_LINHA - 12, fill=COR_CHEGADA)
            elif tipo in ('conclusao_instancia', 'conclusao_tarefa'):
                canvas.create_line(x, y + 3, x, y + ALTURA_LINHA - 3, fill="black", width=2)
                canvas.create_oval(x - 3, y + 2, x + 3, y + 8, fill="black")
            elif tipo == 'deadline_miss':
                canvas.create_oval(x - 8, y + 6, x + 8, y + 22, outline=COR_DEADLINE_MISS, width=2)
                canvas.create_text(x, y + 14, text="!", fill=COR_DEADLINE_MISS, font=("Helvetica", 10, "bold"))
            elif tipo == 'sorteio':
                canvas.create_text(x, y + ALTURA_LINHA - 6, text="S", fill=COR_SORTEIO, font=("Helvetica", 10, "bold"))

    def desenhar_legenda(self):
        canvas = self.canvas_legenda
        canvas.delete("all")
        s = self.simulador
        if s is None:
            return

        x, y = 10, 14
        canvas.create_text(x, y, text="Legenda:", anchor="w", font=("Helvetica", 10, "bold"), fill=COR_TEXTO_SECUNDARIO)
        x += 75
        for t in s.definicoes:
            canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill=t.cor, outline="#999999")
            canvas.create_text(x + 20, y, text=f"Tarefa {t.id}", anchor="w", font=("Helvetica", 9))
            x += 95

        x, y = 10, 38
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill="white", outline="#999999")
        canvas.create_text(x + 20, y, text="Pronta (sem cor)", anchor="w", font=("Helvetica", 9)); x += 150
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill="black", stipple="gray50", outline="#999999")
        canvas.create_text(x + 20, y, text="Suspensa/bloqueada", anchor="w", font=("Helvetica", 9)); x += 170
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill=COR_CPU_DESLIGADA, outline="#999999")
        canvas.create_text(x + 20, y, text="CPU desligada", anchor="w", font=("Helvetica", 9))

        x, y = 10, 62
        canvas.create_polygon(x + 3, y + 6, x + 13, y + 6, x + 8, y - 4, fill=COR_CHEGADA)
        canvas.create_text(x + 20, y, text="Chegada de instância", anchor="w", font=("Helvetica", 9)); x += 175
        canvas.create_line(x + 8, y - 6, x + 8, y + 6, fill="black", width=2)
        canvas.create_oval(x + 5, y - 8, x + 11, y - 2, fill="black")
        canvas.create_text(x + 20, y, text="Conclusão", anchor="w", font=("Helvetica", 9)); x += 110
        canvas.create_oval(x, y - 8, x + 16, y + 8, outline=COR_DEADLINE_MISS, width=2)
        canvas.create_text(x + 20, y, text="Estouro de prazo", anchor="w", font=("Helvetica", 9)); x += 155
        canvas.create_text(x + 8, y, text="S", fill=COR_SORTEIO, font=("Helvetica", 10, "bold"))
        canvas.create_text(x + 22, y, text="Escolhida por sorteio", anchor="w", font=("Helvetica", 9))


def main():
    app = Aplicacao()
    app.mainloop()


if __name__ == "__main__":
    main()