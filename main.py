#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULADOR DE UM SISTEMA OPERACIONAL MULTITAREFA DE TEMPO COMPARTILHADO
 Projeto A - Versão 0.6
 Feito por Marco Gasparotto e Rafael Monçores
================================================================================
"""

import os
import sys
import copy
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ==================================================================================================================
# CONSTANTES DE APRESENTAÇÃO (meramente gráficas, não afetam a lógica do escalonador, funcionando apenas pra representação gráfica)
# ==================================================================================================================
LARGURA_TICK = 26          # largura em pixels de um tick no eixo do tempo
ALTURA_LINHA = 32          # altura em pixels de cada linha (tarefa ou CPU)
MARGEM_ESQUERDA = 140      # espaço reservado à esquerda para os rótulos
MARGEM_TOPO = 40           # espaço reservado no topo para a régua de ticks
COR_GRADE = "#DDDDDD"      # cor das linhas de grade verticais/horizontais
COR_CPU_DESLIGADA = "#B0B0B0"  # cor usada para indicar uma CPU desligada
COR_TEXTO = "#222222"          # cor padrão usada para textos 
COR_CHEGADA = "#2E7D32"     # cor do marcador de chegada de instância
COR_DEADLINE_MISS = "#D32F2F"  # cor usada para indicar uma falha de deadline (OU SEJA, quando perde o prazo)
COR_SORTEIO = "#F9A825"  # cor usada para indicar um sorteio
ESPACO_REGUA = 24          # altura reservada à régua de ticks, logo abaixo das linhas de tarefa
MAX_CPUS = 64              # limite defensivo do simulador


# ==============================================================================
# CONSTANTES DE ESTILO DA INTERFACE (ttk) — usadas apenas na "casca" da janela
# (barra de ferramentas, status, molduras). Não afetam o desenho do Gantt em si
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
# 1) REGISTRO PLUGÁVEL DE ALGORITMOS DE ESCALONAMENTO
# ==============================================================================
'''
Requisito 4.2: O mecanismo de implementação do algoritmo de escalonamento deve ser
flexível/configurável/parametrizável de modo que novos algoritmos possam ser
facilmente incluídos no simulador sem a necessidade de modificar o código da
simulação. Idealmente, o escalonador é apenas uma função que retorna qual é a
próxima tarefa a ser executada, que pode, inclusive, estar contida em uma biblioteca
dinâmica fora do arquivo binário do executável do simulado.
'''


# Para adicionar um algoritmo novo (ex.: Deadline Monotonic), basta chamar
# `registrar_algoritmo(...)` — nenhuma outra parte do simulador precisa mudar,
# nem o parser do arquivo de configuração (que valida contra este registro) nem
# a interface gráfica (que lista as opções deste registro no combobox).
ALGORITMOS_DE_ESCALONAMENTO = {}


def registrar_algoritmo(nome, funcao_prioridade_primaria, descricao=""):
    """
    Registra (ou substitui) um algoritmo de escalonamento.

    `funcao_prioridade_primaria(tarefa, job) -> valor comparável (job é a ativação sendo avaliada)`
    onde MENOR valor significa MAIOR prioridade (é isso que o Python usa
    naturalmente ao ordenar tuplas/listas com `sort`/`min`).

    Exemplo — adicionando um hipotético "Deadline Monotonic" (prioridade fixa
    pelo prazo RELATIVO, e não pelo período como no RM):
        registrar_algoritmo(
            'DM',
            lambda tarefa, job: tarefa.prazo,
            descricao="Deadline Monotonic (prioridade fixa pelo prazo relativo)",
        )
    """
    chave = nome.strip().upper()
    ALGORITMOS_DE_ESCALONAMENTO[chave] = {
        'funcao': funcao_prioridade_primaria,
        'descricao': descricao or chave,
    }


# ---- algoritmos exigidos pelo Projeto A é o RM e o EDF, portanto haverá 2 chamadas da função: ----

registrar_algoritmo(
    'RM',
    lambda tarefa, job: tarefa.periodo,
    descricao="Rate Monotonic (prioridade fixa: menor período primeiro)",
)
registrar_algoritmo(
    'EDF',
    lambda tarefa, job: job['prazo_abs'],
    descricao="Earliest Deadline First (prioridade dinâmica: menor prazo absoluto primeiro)",
)


# ==============================================================================
# 2) ESTRUTURA DE DADOS: TAREFA (a parte "estática"/definição do Task Control Block)
# ==============================================================================

class Tarefa:
    """
    Guarda apenas a 'identidade' e as regras fixas da tarefa (o que veio do arquivo 
    de configuração e nunca muda, como duração, período e prazo). 

    O que muda a cada segundo (quanto tempo falta rodar, se está ativa ou em qual 
    CPU está) fica separado no Simulador. Fazemos isso para não misturar as regras 
    originais com o andamento da simulação, o que facilita muito na hora de resetar 
    o sistema ou de criar o histórico para o botão de 'voltar no tempo'.
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
# 3) FUNÇÕES AUXILIARES DE PARSING (tolerantes a formatação "suja")
# ==============================================================================

# Padroniza strings de cores para o formato hexadecimal canônico (#RRGGBB).

def _normalizar_cor(valor):
    v = valor.strip()              # Remove espaços em branco extras no começo e no fim da string.
    if not v:
        return None                # Se a string estiver vazia, retorna None.
    if not v.startswith('#'):
        v = '#' + v                # Se o usuário esqueceu de colocar o '#', o código adiciona.
    if len(v) != 7:
        return None                # O formato correto (#RRGGBB) tem exatamente 7 caracteres. Se não tiver, é inválido.
    try:
        int(v[1:], 16)             # Tenta converter os 6 caracteres após o '#' de base hexadecimal para número inteiro.
    except ValueError:
        return None                # Se houver letras inválidas (ex: 'G' ou 'Z'), a conversão falha e retorna None.
    return v.upper()               # Se passou em tudo, retorna a cor padronizada com letras maiúsculas.



# Interpreta o texto de eventos de bloqueio (formato "deslocamento:duracao,...").
# É tolerante a falhas: ignora tokens corrompidos sem quebrar a execução.

def _parsear_eventos(campo, contexto="lista de eventos"):
    """Lê deslocamento:duração e informa precisamente qualquer erro."""
    campo = campo.strip()
    if campo in ('', '-'):
        return []
    eventos, deslocamentos = [], set()
    for parte in campo.split(','):
        parte = parte.strip()
        if not parte or ':' not in parte:
            raise ValueError(f"{contexto}: evento inválido '{parte}'. Use deslocamento:duração.")
        desloc_str, dur_str = parte.split(':', 1)
        try:
            desloc, dur = int(desloc_str.strip()), int(dur_str.strip())
        except ValueError as erro:
            raise ValueError(f"{contexto}: evento inválido '{parte}'; use inteiros.") from erro
        if desloc < 0 or dur <= 0:
            raise ValueError(f"{contexto}: deslocamento >= 0 e duração > 0 são obrigatórios.")
        if desloc in deslocamentos:
            raise ValueError(f"{contexto}: dois eventos no deslocamento {desloc} não são permitidos.")
        deslocamentos.add(desloc)
        eventos.append((desloc, dur))
    return sorted(eventos, key=lambda par: par[0])


# Lê o arquivo de configuração linha por linha, validando parâmetros globais 
# e instanciando as tarefas válidas. Retorna dados limpos e uma lista de avisos.

def carregar_configuracao(caminho):
    """
    Lê e interpreta um arquivo de configuração da simulação.

    Formato esperado (campos separados por ';'):
        linha 1:        algoritmo_escalonamento;quantum;qtde_cpus
        linhas 2..N:    id;cor;ingresso;duracao;periodo;prazo;lista_eventos

    Tolerâncias implementadas:
      - nomes de algoritmo são tratados de forma "case-insensitive";
      - linhas em branco (ou só com espaços) são ignoradas;
      - um ';' sobrando no final de qualquer linha é tolerado;
      - caminho absoluto ou relativo — ambos funcionam com os.path.abspath;
      - linhas de tarefa mal formadas geram um AVISO e são ignoradas sem quebrar o app.

    Retorna: (algoritmo, quantum, num_cpus, lista_de_tarefas, avisos)
    """
    # Padroniza o caminho do arquivo para garantir compatibilidade com o S.O.
    caminho = os.path.abspath(os.path.expanduser(caminho.strip()))
    
    # Valida se o arquivo realmente existe no disco
    if not os.path.isfile(caminho):
        raise ValueError(f"Arquivo não encontrado: {caminho}")

    # Abre o arquivo de texto com codificação UTF-8
    with open(caminho, 'r', encoding='utf-8-sig') as arquivo:
        linhas_brutas = arquivo.readlines()

    # Limpeza preliminar: remove espaços extras e descarta linhas totalmente vazias
    linhas = [linha.strip() for linha in linhas_brutas]
    linhas = [linha for linha in linhas if linha != '']

    # Se após a limpeza a lista estiver vazia, o arquivo não tem conteúdo útil
    if not linhas:
        raise ValueError("O arquivo de configuração está vazio.")

    avisos = []  # Lista para armazenar avisos de inconsistências leves

    # -------------------------------------------------------------------------
    # 1) LEITURA E VALIDAÇÃO DO CABEÇALHO (PRIMEIRA LINHA)
    # -------------------------------------------------------------------------
    cabecalho = linhas[0]
    if cabecalho.endswith(';'):
        cabecalho = cabecalho[:-1]  # Tolera ponto e vírgula sobrando no fim da linha
        
    campos_cabecalho = [c.strip() for c in cabecalho.split(';')]
    
    if len(campos_cabecalho) != 3:
        raise ValueError(
            "Primeira linha inválida. O formato esperado é: "
            "algoritmo_escalonamento;quantum;qtde_cpus"
        )
        
    algoritmo_bruto, quantum_bruto, cpus_bruto = campos_cabecalho[:3]

    # Valida se o algoritmo informado existe no dicionário global de algoritmos
    algoritmo = algoritmo_bruto.strip().upper()
    if algoritmo not in ALGORITMOS_DE_ESCALONAMENTO:
        disponiveis = ', '.join(sorted(ALGORITMOS_DE_ESCALONAMENTO))
        raise ValueError(
            f"Algoritmo de escalonamento desconhecido: '{algoritmo_bruto}'. "
            f"Algoritmos disponíveis: {disponiveis}."
        )

    # Valida se o quantum é um número inteiro positivo
    try:
        quantum = int(quantum_bruto)
        if quantum <= 0:
            raise ValueError
    except ValueError:
        raise ValueError(f"Quantum inválido na primeira linha: '{quantum_bruto}'.")

    # Valida se a quantidade de CPUs é um número inteiro positivo
    try:
        num_cpus = int(cpus_bruto)
        if num_cpus <= 0 or num_cpus > MAX_CPUS:
            raise ValueError
    except ValueError:
        raise ValueError(f"Quantidade de CPUs inválida: '{cpus_bruto}'. Use 1 a {MAX_CPUS}.")

    # -------------------------------------------------------------------------
    # 2) LEITURA E VALIDAÇÃO DAS TAREFAS (LINHAS SEGUINTES)
    # -------------------------------------------------------------------------
    tarefas = []
    ids_vistos = set()  # Conjunto para controlar IDs duplicados
    cores_vistas = set()

    # Varre da segunda linha em diante, contando o número da linha para logs de erro
    for numero_linha, linha in enumerate(linhas[1:], start=2):
        # Remove ponto e vírgula do final da linha se houver
        linha_sem_ponto_e_virgula_final = linha[:-1] if linha.endswith(';') else linha
        campos = [c.strip() for c in linha_sem_ponto_e_virgula_final.split(';')]

        # Os seis primeiros campos são obrigatórios; lista_eventos pode ser vazia.
        if len(campos) == 6:
            campos.append('')
        elif len(campos) != 7:
            raise ValueError(f"Linha {numero_linha}: esperados 7 campos; recebidos {len(campos)}.")

        (id_str, cor_str, ingresso_str, duracao_str,
         periodo_str, prazo_str, eventos_str) = campos

        # Validação do ID da tarefa
        try:
            id_tarefa = int(id_str)
        except ValueError:
            raise ValueError(f"Linha {numero_linha}: ID inválido ('{id_str}').")
            
        # Verifica duplicidade de ID
        if id_tarefa in ids_vistos:
            raise ValueError(f"Linha {numero_linha}: ID {id_tarefa} duplicado.")

        # Validação e normalização da cor
        cor = _normalizar_cor(cor_str)
        if cor is None:
            raise ValueError(f"Linha {numero_linha}: cor inválida ('{cor_str}').")
        if cor in cores_vistas:
            raise ValueError(f"Linha {numero_linha}: a cor {cor} já pertence a outra tarefa.")

        # Validação do instante de ingresso
        try:
            ingresso = int(ingresso_str)
            if ingresso < 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Linha {numero_linha}: ingresso inválido ('{ingresso_str}').")

        # Validação da duração (deve ser maior que zero)
        try:
            duracao = int(duracao_str)
            if duracao <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Linha {numero_linha}: duração inválida ('{duracao_str}').")

        # Validação do período (descarta tarefas aperiódicas)
        periodo_limpo = periodo_str.strip()
        if periodo_limpo in ('', '0', '-'):
            avisos.append(
                f"Tarefa {id_tarefa} é aperiódica (sem período definido). O simulador "
                "não oferece suporte a tarefas aperiódicas; ela foi ignorada."
            )
            continue
            
        try:
            periodo = int(periodo_limpo)
            if periodo <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Linha {numero_linha}: período inválido ('{periodo_str}').")

        # Validação do prazo (se inválido, assume prazo igual ao período)
        try:
            prazo = int(prazo_str)
            if prazo <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Linha {numero_linha}: prazo inválido ('{prazo_str}').")

        # Processa a string de eventos de bloqueio
        try:
            eventos = _parsear_eventos(eventos_str, f"Linha {numero_linha}, tarefa {id_tarefa}")
        except ValueError as erro_eventos:
            # Projeto A: a lista_eventos só é tratada no Projeto B (req. 3.3.5).
            # Conteúdo fora do formato provisório é ignorado com aviso, para
            # nunca recusar um arquivo que respeita o formato do enunciado.
            avisos.append(f"{erro_eventos} Eventos desta tarefa foram ignorados no Projeto A.")
            eventos = []

        # Instancia o objeto Tarefa e adiciona à lista válida
        tarefas.append(Tarefa(id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos))
        ids_vistos.add(id_tarefa)
        cores_vistas.add(cor)

    # Garante que sobrou pelo menos uma tarefa válida para simular
    if not tarefas:
        raise ValueError("Nenhuma tarefa periódica válida foi encontrada no arquivo.")

    return algoritmo, quantum, num_cpus, tarefas, avisos

# ==============================================================================
# 4) NÚCLEO DO SIMULADOR (KERNEL)
# ==============================================================================
class Simulador:
    """Núcleo do simulador, executado rigorosamente um tick por passo.

    Cada tarefa possui um TCB dinâmico e uma fila de jobs. Um job representa
    uma ativação periódica independente. Isso é essencial porque uma nova
    ativação pode chegar enquanto uma anterior ainda está pronta, executando
    ou bloqueada. O escalonador escolhe jobs, mas a interface continua
    apresentando o estado agregado por tarefa.
    """

    def __init__(self, algoritmo, quantum, num_cpus, tarefas, semente=0):
        self.algoritmo = algoritmo
        self.quantum = quantum
        self.num_cpus = num_cpus
        self.definicoes = tarefas
        self.tarefas_por_id = {t.id: t for t in tarefas}
        self.semente = semente
        self.rng = random.Random(semente)
        self.tick = 0
        self.estado_tarefas = {}
        self.jobs = {}
        self.proximo_job_id = 1
        self.cpus = []
        self.historico = []
        self.indice_historico = 0
        self.finalizado = False

    def _novo_tcb(self):
        return {
            'instancias_liberadas': 0, 'concluidas': 0,
            'liberacao_atual': None, 'prazo_abs_atual': None,
            'restante_atual': 0, 'estado': 'nao_chegou', 'cpu': None,
            'execucao_continua_desde': None, 'eventos_pendentes': [],
            'bloqueio_fim': None, 'deadline_perdido': False,
            'jobs_pendentes': [],
        }

    def reiniciar(self):
        """Reinicia o relógio, TCBs, jobs, CPUs, histórico e sorteios."""
        self.tick = min(t.ingresso for t in self.definicoes)
        self.estado_tarefas = {t.id: self._novo_tcb() for t in self.definicoes}
        self.jobs = {}
        self.proximo_job_id = 1
        self.cpus = [{'ligada': False, 'tarefa': None, 'job': None}
                     for _ in range(self.num_cpus)]
        self.finalizado = False
        self.historico = []
        self.rng = random.Random(self.semente)
        eventos = self._processar_tick(self.tick)
        eventos += self._escalonar()
        self._sincronizar_tcbs()
        self._registrar_snapshot(eventos, [])
        self.indice_historico = 0

    def _job_visivel(self, tid):
        """Retorna o job mais representativo da tarefa para a interface."""
        ativos = [j for j in self.jobs.values()
                  if j['tarefa'] == tid and j['estado'] != 'concluido']
        if not ativos:
            return None
        ordem = {'executando': 0, 'suspensa': 1, 'pronta': 2}
        return min(ativos, key=lambda j: (ordem.get(j['estado'], 9),
                                          j['liberacao'], j['numero']))

    def _sincronizar_tcbs(self):
        """Projeta a fila de jobs no TCB agregado consumido pela interface."""
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            ativos = sorted([j for j in self.jobs.values()
                             if j['tarefa'] == t.id and j['estado'] != 'concluido'],
                            key=lambda j: (j['liberacao'], j['numero']))
            et['jobs_pendentes'] = [j['id'] for j in ativos]
            et['concluidas'] = sum(1 for j in self.jobs.values()
                                   if j['tarefa'] == t.id and j['estado'] == 'concluido')
            visivel = self._job_visivel(t.id)
            if visivel is None:
                et.update({
                    'liberacao_atual': None, 'prazo_abs_atual': None,
                    'restante_atual': 0,
                    'estado': 'concluida' if et['instancias_liberadas'] >= 10
                              and et['concluidas'] >= 10 else 'nao_chegou',
                    'cpu': None, 'execucao_continua_desde': None,
                    'eventos_pendentes': [], 'bloqueio_fim': None,
                    'deadline_perdido': False,
                })
            else:
                et.update({
                    'liberacao_atual': visivel['liberacao'],
                    'prazo_abs_atual': visivel['prazo_abs'],
                    'restante_atual': visivel['restante'],
                    'estado': visivel['estado'], 'cpu': visivel['cpu'],
                    'execucao_continua_desde': visivel['execucao_continua_desde'],
                    'eventos_pendentes': list(visivel['eventos_pendentes']),
                    'bloqueio_fim': visivel['bloqueio_fim'],
                    'deadline_perdido': any(j['deadline_perdido'] for j in ativos),
                })

    def _criar_job(self, tarefa):
        et = self.estado_tarefas[tarefa.id]
        numero = et['instancias_liberadas'] + 1
        jid = self.proximo_job_id
        self.proximo_job_id += 1
        self.jobs[jid] = {
            'id': jid, 'tarefa': tarefa.id, 'numero': numero,
            'liberacao': self.tick, 'prazo_abs': self.tick + tarefa.prazo,
            'restante': tarefa.duracao, 'estado': 'pronta', 'cpu': None,
            'execucao_continua_desde': None,
            'eventos_pendentes': list(tarefa.eventos),
            'bloqueio_fim': None, 'deadline_perdido': False,
            'motivo_suspensao': None, 'tempo_cpu': 0,
            # --- métricas do capítulo 6 do livro (Tt, Tw, tr e trocas) ---
            'ingresso': self.tick,
            'conclusao': None,
            'tempo_espera': 0,
            'trocas': 0,
            'primeira_execucao': None,
        }
        et['instancias_liberadas'] += 1
        return jid

    def _desvincular_job(self, jid):
        for cpu in self.cpus:
            if cpu.get('job') == jid:
                cpu['job'] = None
                cpu['tarefa'] = None
                cpu['ligada'] = False
        job = self.jobs[jid]
        job['cpu'] = None
        job['execucao_continua_desde'] = None

    def _processar_tick(self, tick):
        """Processa conclusões, desbloqueios, deadlines, eventos e liberações."""
        eventos = []

        # O intervalo anterior termina neste tick; concluir vem antes do deadline.
        for jid, job in list(self.jobs.items()):
            if job['estado'] == 'executando' and job['restante'] <= 0:
                job['restante'] = 0
                self._desvincular_job(jid)
                job['estado'] = 'concluido'
                job['conclusao'] = tick
                tipo = 'conclusao_tarefa' if (
                    self.estado_tarefas[job['tarefa']]['instancias_liberadas'] >= 10 and
                    sum(1 for j in self.jobs.values()
                        if j['tarefa'] == job['tarefa'] and j['estado'] == 'concluido') >= 10
                ) else 'conclusao_instancia'
                eventos.append({'tipo': tipo, 'tarefa': job['tarefa'], 'job': jid})

        for jid, job in self.jobs.items():
            if job['estado'] == 'suspensa' and job['bloqueio_fim'] is not None                     and tick >= job['bloqueio_fim']:
                job['estado'] = 'pronta'
                job['bloqueio_fim'] = None
                job['motivo_suspensao'] = None

        for jid, job in self.jobs.items():
            if job['estado'] in ('pronta', 'executando', 'suspensa')                     and not job['deadline_perdido'] and job['restante'] > 0                     and tick >= job['prazo_abs']:
                job['deadline_perdido'] = True
                eventos.append({'tipo': 'deadline_miss', 'tarefa': job['tarefa'], 'job': jid})

        # Eventos são medidos em tempo efetivo de CPU da ativação.
        for jid, job in list(self.jobs.items()):
            if job['estado'] not in ('pronta', 'executando'):
                continue
            restantes = []
            disparou = False
            for desloc, dur in job['eventos_pendentes']:
                if not disparou and desloc <= job['tempo_cpu']:
                    self._desvincular_job(jid)
                    job['estado'] = 'suspensa'
                    job['bloqueio_fim'] = tick + dur
                    job['motivo_suspensao'] = 'evento'
                    disparou = True
                    eventos.append({'tipo': 'suspensao', 'tarefa': job['tarefa'], 'job': jid})
                else:
                    restantes.append((desloc, dur))
            job['eventos_pendentes'] = restantes

        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['instancias_liberadas'] >= 10:
                continue
            proxima = t.ingresso + et['instancias_liberadas'] * t.periodo
            if tick >= proxima:
                jid = self._criar_job(t)
                eventos.append({'tipo': 'chegada', 'tarefa': t.id, 'job': jid})

        self._sincronizar_tcbs()
        return eventos

    def _chave_job(self, jid, incumbentes):
        job = self.jobs[jid]
        tarefa = self.tarefas_por_id[job['tarefa']]
        # Prioridade primária vem do registro plugável (req. 4.2): um algoritmo novo
        # registrado passa a valer sem alterar o núcleo da simulação.
        primaria = ALGORITMOS_DE_ESCALONAMENTO[self.algoritmo]['funcao'](tarefa, job)
        return (primaria, 0 if jid in incumbentes else 1,
                job['prazo_abs'], tarefa.ingresso, tarefa.duracao)

    def _jobs_mais_antigos_por_tarefa(self):
        """Ids das ativações que podem competir por CPU.

        Uma tarefa é um fluxo sequencial de execução: só a ativação não
        concluída mais antiga de cada tarefa pode ocupar uma CPU. As mais
        novas ficam na fila aguardando a predecessora terminar. Sem isso, a
        mesma tarefa executaria em duas CPUs ao mesmo tempo quando a duração
        excede o período."""
        mais_antigo = {}
        for jid, j in self.jobs.items():
            if j['estado'] == 'concluido':
                continue
            atual = mais_antigo.get(j['tarefa'])
            if atual is None or j['numero'] < self.jobs[atual]['numero']:
                mais_antigo[j['tarefa']] = jid
        return set(mais_antigo.values())

    def _escalonar(self):
        """Aplica RM/EDF e os cinco desempates exigidos pelo enunciado."""
        eventos = []
        mais_antigo = self._jobs_mais_antigos_por_tarefa()
        elegiveis = [jid for jid, j in self.jobs.items() if jid in mais_antigo
                     if j['estado'] in ('pronta', 'executando')]
        incumbentes = {cpu.get('job') for cpu in self.cpus if cpu.get('job') is not None}
        elegiveis.sort(key=lambda jid: self._chave_job(jid, incumbentes))
        vagas = min(self.num_cpus, len(elegiveis))

        if 0 < vagas < len(elegiveis):
            fronteira = self._chave_job(elegiveis[vagas - 1], incumbentes)
            empatados = [jid for jid in elegiveis
                         if self._chave_job(jid, incumbentes) == fronteira]
            inicio = min((elegiveis.index(jid) for jid in empatados), default=vagas)
            disputadas = vagas - inicio
            if 0 < disputadas < len(empatados):
                escolhidos = self.rng.sample(empatados, disputadas)
                antes = [jid for jid in elegiveis[:inicio] if jid not in empatados]
                depois = [jid for jid in elegiveis if jid not in empatados]
                elegiveis = antes + escolhidos + [jid for jid in depois if jid not in antes]
                for jid in escolhidos:
                    eventos.append({'tipo': 'sorteio',
                                    'tarefa': self.jobs[jid]['tarefa'], 'job': jid})

        selecionados = elegiveis[:vagas]
        anteriores = {cpu.get('job'): idx for idx, cpu in enumerate(self.cpus)
                      if cpu.get('job') is not None}
        atribuicoes = {}
        restantes = list(selecionados)
        for jid in list(restantes):
            if jid in anteriores:
                atribuicoes[anteriores[jid]] = jid
                restantes.remove(jid)
        livres = [i for i in range(self.num_cpus) if i not in atribuicoes]
        for idx, jid in zip(livres, restantes):
            atribuicoes[idx] = jid

        for jid, job in self.jobs.items():
            if job['estado'] == 'executando' and jid not in selecionados:
                job['estado'] = 'pronta'
                job['cpu'] = None
                job['execucao_continua_desde'] = None

        for idx, cpu in enumerate(self.cpus):
            jid = atribuicoes.get(idx)
            if jid is None:
                cpu.update({'ligada': False, 'tarefa': None, 'job': None})
                continue
            job = self.jobs[jid]
            nova_fatia = job['estado'] != 'executando' or job['cpu'] != idx
            cpu.update({'ligada': True, 'tarefa': job['tarefa'], 'job': jid})
            job['estado'] = 'executando'
            job['cpu'] = idx
            if nova_fatia:
                # troca de contexto: o livro conta cada mudança de tarefa no processador
                job['trocas'] += 1
                job['execucao_continua_desde'] = self.tick

        self._sincronizar_tcbs()
        return eventos

    def passo(self):
        """Executa exatamente um tick: [tick, tick+1)."""
        if self.finalizado:
            return False
        inicio, fim = self.tick, self.tick + 1
        blocos = []
        for idx, cpu in enumerate(self.cpus):
            jid = cpu.get('job')
            if jid is not None:
                job = self.jobs[jid]
                job['restante'] -= 1
                job['tempo_cpu'] += 1
                if job['primeira_execucao'] is None:
                    # tempo de resposta (tr) do livro: da chegada ao primeiro uso de CPU
                    job['primeira_execucao'] = inicio
                blocos.append((job['tarefa'], idx, inicio, fim, 'executando'))
        for job in self.jobs.values():
            if job['estado'] == 'suspensa':
                blocos.append((job['tarefa'], None, inicio, fim, 'suspensa'))
            elif job['estado'] == 'pronta' and job['conclusao'] is None:
                # tempo de espera (tw) do livro: tempo na fila global sem executar
                job['tempo_espera'] += 1
        self.tick = fim
        eventos = self._processar_tick(self.tick)
        eventos += self._escalonar()
        self._sincronizar_tcbs()
        self.finalizado = all(
            self.estado_tarefas[t.id]['instancias_liberadas'] >= 10 and
            self.estado_tarefas[t.id]['concluidas'] >= 10
            for t in self.definicoes
        )
        self._registrar_snapshot(eventos, blocos)
        return True

    def executar_completo(self, limite_de_seguranca=200000):
        passos = 0
        while not self.finalizado:
            if passos >= limite_de_seguranca:
                raise RuntimeError('A simulação excedeu o limite de segurança de passos.')
            self.passo()
            passos += 1
        self.indice_historico = len(self.historico) - 1

    def _restaurar_snapshot(self, indice):
        snap = self.historico[indice]
        self.tick = snap['tick']
        self.estado_tarefas = copy.deepcopy(snap['estado_tarefas'])
        self.jobs = copy.deepcopy(snap['jobs'])
        self.cpus = copy.deepcopy(snap['cpus'])
        self.proximo_job_id = snap['proximo_job_id']
        self.finalizado = snap['finalizado']
        self.rng.setstate(snap['rng_state'])
        self.indice_historico = indice

    def avancar(self):
        if self.indice_historico < len(self.historico) - 1:
            self._restaurar_snapshot(self.indice_historico + 1)
            return True
        return self.passo()

    def retroceder(self):
        if self.indice_historico <= 0:
            return False
        self._restaurar_snapshot(self.indice_historico - 1)
        return True

    def aplicar_edicao_e_reconstruir(self, indice_alvo=None):
        """Reconstrói parâmetros estáticos até o tick selecionado."""
        alvo_tick = self.tick if indice_alvo is None else self.historico[indice_alvo]['tick']
        self.tarefas_por_id = {t.id: t for t in self.definicoes}
        self.reiniciar()
        while self.tick < alvo_tick and not self.finalizado:
            self.passo()
        self.indice_historico = len(self.historico) - 1

    def alterar_estado_tarefa(self, tid, novo_estado):
        """Altera semanticamente o job visível no ponto atual e cria uma ramificação."""
        if novo_estado not in ('pronta', 'suspensa'):
            raise ValueError('O estado manual deve ser pronta ou suspensa.')
        job = self._job_visivel(tid)
        if job is None:
            raise ValueError('A tarefa não possui ativação pendente neste tick.')
        self.historico = self.historico[:self.indice_historico + 1]
        self._desvincular_job(job['id'])
        job['estado'] = novo_estado
        if novo_estado == 'suspensa':
            job['bloqueio_fim'] = self.tick + 1
        else:
            job['bloqueio_fim'] = None
        self.finalizado = False
        eventos = self._escalonar()
        self._sincronizar_tcbs()
        self._substituir_snapshot_atual(eventos)

    def _substituir_snapshot_atual(self, eventos):
        anterior = self.historico[self.indice_historico]
        novo = self._criar_snapshot(anterior.get('eventos', []) + eventos,
                                    anterior.get('blocos_intervalo', []))
        self.historico[self.indice_historico] = novo

    def _criar_snapshot(self, eventos, blocos_intervalo):
        return {
            'tick': self.tick,
            'estado_tarefas': copy.deepcopy(self.estado_tarefas),
            'jobs': copy.deepcopy(self.jobs),
            'cpus': copy.deepcopy(self.cpus),
            'eventos': copy.deepcopy(eventos),
            'blocos_intervalo': copy.deepcopy(blocos_intervalo),
            'proximo_job_id': self.proximo_job_id,
            'finalizado': self.finalizado,
            'rng_state': self.rng.getstate(),
        }

    def _registrar_snapshot(self, eventos, blocos_intervalo):
        self.historico.append(self._criar_snapshot(eventos, blocos_intervalo))
        self.indice_historico = len(self.historico) - 1

    def obter_todos_os_blocos(self, ate_indice=None):
        if ate_indice is None:
            ate_indice = len(self.historico) - 1
        blocos, eventos = [], []
        for i in range(0, ate_indice + 1):
            blocos.extend(self.historico[i]['blocos_intervalo'])
            for ev in self.historico[i]['eventos']:
                eventos.append(dict(ev, tick=self.historico[i]['tick']))
        return blocos, eventos

    # --------------------------- métricas do livro ---------------------------
    def calcular_metricas(self):
        """Consolida as métricas do capítulo 6 do livro (Tt, Tw, tr e trocas).

        Para cada tarefa considera todas as ativações concluídas, que é o
        equivalente do job por ativação exigido pelo capítulo 4. Também
        devolve o tempo total de processamento e a eficiência do uso das CPUs,
        que o livro mede na seção 5.2 como E = tq / (tq + ttc).
        """
        linhas = []
        total_trocas = 0
        for t in sorted(self.definicoes, key=lambda x: x.id):
            jobs = [j for j in self.jobs.values()
                    if j['tarefa'] == t.id and j['estado'] == 'concluido']
            if not jobs:
                continue
            tt = sum((j['conclusao'] - j['ingresso']) for j in jobs) / len(jobs)
            tw = sum(j['tempo_espera'] for j in jobs) / len(jobs)
            tr = sum((j['primeira_execucao'] - j['ingresso'])
                     for j in jobs if j['primeira_execucao'] is not None)
            com_resposta = sum(1 for j in jobs if j['primeira_execucao'] is not None)
            trocas = sum(j['trocas'] for j in jobs)
            total_trocas += trocas
            linhas.append({
                'tarefa': t.id,
                'periodo': t.periodo,
                'duracao': t.duracao,
                'prazo': t.prazo,
                'ativacoes': len(jobs),
                'tt': tt,
                'tw': tw,
                'tr': (tr / com_resposta) if com_resposta else 0.0,
                'trocas': trocas,
                'deadlines_perdidos': sum(1 for j in jobs if j['deadline_perdido']),
            })

        if not self.historico:
            return {'linhas': linhas, 'resumo': {}}
        tick_final = self.historico[-1]['tick']
        tick_inicial = self.historico[0]['tick']
        horizonte = max(1, tick_final - tick_inicial)
        tempo_processamento = sum(j['tempo_cpu'] for j in self.jobs.values())
        # capacidade teórica = nº de CPUs x ticks simulados; a diferença é ociosidade
        capacidade = max(1, self.num_cpus * horizonte)
        resumo = {
            'algoritmo': self.algoritmo,
            'tick_inicial': tick_inicial,
            'tick_final': tick_final,
            'horizonte': horizonte,
            'tempo_processamento': tempo_processamento,
            'capacidade_cpu': capacidade,
            'aproveitamento': tempo_processamento / capacidade,
            'ociosidade': 1 - (tempo_processamento / capacidade),
            'trocas_totais': total_trocas,
            'deadlines_perdidos': sum(
                1 for j in self.jobs.values() if j['deadline_perdido']),
        }
        return {'linhas': linhas, 'resumo': resumo}

    def texto_metricas(self):
        """Formata as métricas para exibição na interface."""
        dados = self.calcular_metricas()
        resumo = dados.get('resumo') or {}
        partes = []
        if resumo:
            partes.append(
                f"Algoritmo: {resumo['algoritmo']}  |  "
                f"Ticks: {resumo['tick_inicial']} a {resumo['tick_final']} "
                f"({resumo['horizonte']})  |  CPUs: {self.num_cpus}")
            partes.append(
                f"Tempo de processamento: {resumo['tempo_processamento']}  |  "
                f"Capacidade: {resumo['capacidade_cpu']}  |  "
                f"Aproveitamento: {resumo['aproveitamento']:.1%}  |  "
                f"Ociosidade: {resumo['ociosidade']:.1%}")
            partes.append(
                f"Trocas de contexto: {resumo['trocas_totais']}  |  "
                f"Deadlines perdidos: {resumo['deadlines_perdidos']}")
        partes.append("")
        partes.append(f"{'Tar':>4} {'Ativ':>5} {'Tt':>7} {'Tw':>7} {'Tr':>7} "
                      f"{'Trocas':>7} {'Perdas':>7}")
        for linha in dados['linhas']:
            partes.append(
                f"{linha['tarefa']:>4} {linha['ativacoes']:>5} "
                f"{linha['tt']:>7.1f} {linha['tw']:>7.1f} {linha['tr']:>7.1f} "
                f"{linha['trocas']:>7} {linha['deadlines_perdidos']:>7}")
        return "\n".join(partes)

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
    margem_esq, margem_topo, espaco_entre_secoes = 150, 50, 26
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
            partes.append(f'<text x="{x}" y="{margem_topo + altura_tarefas + 16}" font-size="10" fill="#666666" text-anchor="middle">{tk_}</text>')

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

    # Paleta de cores sugeridas (requisito 3.2 — sugerir valores padrão) para
    # quando o usuário cria uma nova tarefa pela interface: percorrida em
    # ordem, pulando cores já usadas por alguma tarefa existente.
    PALETA_CORES_PADRAO = [
        "#3366CC", "#DC3912", "#FF9900", "#109618", "#990099",
        "#0099C6", "#DD4477", "#66AA00", "#B82E2E", "#316395",
    ]

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
        ttk.Button(barra, text="＋ Nova tarefa...", style="Secondary.TButton",
                   command=self.abrir_nova_tarefa).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="✎ Editar tarefa...", style="Secondary.TButton",
                   command=self.abrir_editor_de_tarefa).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Estado...", style="Secondary.TButton",
                   command=self.abrir_editor_de_estado).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Métricas...", style="Secondary.TButton",
                   command=self.abrir_relatorio_metricas).pack(side=tk.LEFT, padx=6)
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
            title="Selecione o arquivo de configuração",
            filetypes=[("Todos os arquivos", "*.*"), ("Configuração (.txt, .cfg)", "*.txt *.cfg")],
        )
        if caminho:
            self._carregar_arquivo_de_caminho(caminho)

    def _carregar_arquivo_de_caminho(self, caminho):
        try:
            algoritmo, quantum, num_cpus, tarefas, avisos = carregar_configuracao(caminho)
        except (ValueError, OSError, UnicodeError) as erro:
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

    def _proxima_cor_padrao(self):
        """Sugere (requisito 3.2) a primeira cor da paleta ainda não usada por nenhuma tarefa."""
        usadas = {t.cor for t in self.simulador.definicoes} if self.simulador else set()
        for cor in self.PALETA_CORES_PADRAO:
            if cor not in usadas:
                return cor
        return self.PALETA_CORES_PADRAO[len(usadas) % len(self.PALETA_CORES_PADRAO)]

    def abrir_nova_tarefa(self):
        """
        Adiciona uma nova tarefa ao conjunto de tarefas simulado (requisito
        3.1 — o "conjunto de tarefas" deve poder ser configurado pelo
        usuário, o que inclui incluir tarefas novas, não só editar as que
        já vieram do arquivo). Os campos vêm com valores padrão sugeridos
        (requisito 3.2), que o usuário pode sobrescrever livremente.
        """
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Nova tarefa")
        janela.geometry("400x460")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        cabecalho = tk.Frame(janela, bg=COR_FUNDO_APP)
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 4))
        tk.Label(cabecalho, text="Nova tarefa", bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO,
                 font=FONTE_TITULO).pack(anchor="w")

        ids_existentes = self.simulador.tarefas_por_id.keys()
        proximo_id = (max(ids_existentes) + 1) if ids_existentes else 1

        campos = {}
        rotulos_com_padrao = [
            ("id", "ID (único):", str(proximo_id)),
            ("cor", "Cor (#RRGGBB):", self._proxima_cor_padrao()),
            ("ingresso", "Ingresso:", "0"),
            ("duracao", "Duração:", "1"),
            ("periodo", "Período:", "5"),
            ("prazo", "Prazo:", "5"),
            ("eventos", "Eventos (desloc:dur,...):", ""),
        ]
        for i, (chave, texto, valor_padrao) in enumerate(rotulos_com_padrao, start=1):
            tk.Label(janela, text=texto, bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
                row=i, column=0, sticky="w", padx=16, pady=6)
            entrada = tk.Entry(janela, width=26, font=FONTE_PADRAO, relief="solid", bd=1)
            entrada.insert(0, valor_padrao)
            entrada.grid(row=i, column=1, padx=16, pady=6, sticky="ew")
            campos[chave] = entrada
        janela.columnconfigure(1, weight=1)

        def aplicar():
            try:
                novo_id = int(campos["id"].get())
            except ValueError:
                messagebox.showerror("Erro", "ID deve ser um número inteiro.", parent=janela)
                return
            if novo_id in self.simulador.tarefas_por_id:
                messagebox.showerror(
                    "Erro", f"Já existe uma tarefa com ID {novo_id}. Escolha outro ID.", parent=janela)
                return

            cor = _normalizar_cor(campos["cor"].get())
            if cor is None:
                messagebox.showerror("Erro", "Cor inválida. Use o formato #RRGGBB.", parent=janela)
                return

            try:
                ingresso = int(campos["ingresso"].get())
                duracao = int(campos["duracao"].get())
                periodo = int(campos["periodo"].get())
                prazo = int(campos["prazo"].get())
                if ingresso < 0 or duracao <= 0 or periodo <= 0 or prazo <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Erro",
                    "Ingresso deve ser inteiro (>= 0); duração, período e prazo devem ser inteiros positivos.",
                    parent=janela,
                )
                return
            eventos = _parsear_eventos(campos["eventos"].get())

            nova_tarefa = Tarefa(novo_id, cor, ingresso, duracao, periodo, prazo, eventos)
            self.simulador.definicoes.append(nova_tarefa)
            self.simulador.tarefas_por_id = {t.id: t for t in self.simulador.definicoes}

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        ttk.Button(janela, text="Adicionar tarefa", style="Accent.TButton", command=aplicar).grid(
            row=len(rotulos_com_padrao) + 1, column=0, columnspan=2, pady=18)

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
                if ingresso < 0 or duracao <= 0 or periodo <= 0 or prazo <= 0:
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

        def remover():
            """
            Remove a tarefa selecionada do conjunto de tarefas simulado
            (requisito 3.1 — "conjunto de tarefas" é um parâmetro
            configurável). É preciso manter ao menos uma tarefa, senão não
            há o que simular. A remoção, como qualquer edição, reconstrói
            a linha do tempo inteira (Premissa 5).
            """
            if len(self.simulador.definicoes) <= 1:
                messagebox.showerror(
                    "Erro", "Não é possível remover a última tarefa restante.", parent=janela)
                return
            id_selecionado = int(variavel_id.get())
            if not messagebox.askyesno(
                    "Confirmar remoção", f"Remover a Tarefa {id_selecionado}? Esta ação não pode ser desfeita.",
                    parent=janela):
                return

            self.simulador.definicoes = [
                t for t in self.simulador.definicoes if t.id != id_selecionado
            ]
            self.simulador.tarefas_por_id = {t.id: t for t in self.simulador.definicoes}

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        quadro_botoes = tk.Frame(janela, bg=COR_FUNDO_APP)
        quadro_botoes.grid(row=len(rotulos) + 2, column=0, columnspan=2, pady=18)
        ttk.Button(quadro_botoes, text="Aplicar", style="Accent.TButton",
                   command=aplicar).pack(side=tk.LEFT, padx=6)
        ttk.Button(quadro_botoes, text="Remover tarefa", style="Secondary.TButton",
                   command=remover).pack(side=tk.LEFT, padx=6)

    def abrir_editor_de_estado(self):
        """Altera o estado dinâmico no tick exibido e descarta o futuro antigo."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue uma configuração primeiro.")
            return
        janela = tk.Toplevel(self)
        janela.title("Editar estado atual")
        janela.geometry("430x250")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)
        janela.grab_set()
        tk.Label(janela, text="Estado no tick selecionado", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=18, pady=(18, 10))
        quadro = tk.Frame(janela, bg=COR_FUNDO_APP)
        quadro.pack(fill=tk.X, padx=18)
        ids = sorted(self.simulador.tarefas_por_id)
        var_id = tk.StringVar(value=str(ids[0]))
        var_estado = tk.StringVar(value="pronta")
        tk.Label(quadro, text="Tarefa:", bg=COR_FUNDO_APP).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(quadro, textvariable=var_id, values=[str(i) for i in ids],
                     state="readonly").grid(row=0, column=1, sticky="ew", pady=6)
        tk.Label(quadro, text="Novo estado:", bg=COR_FUNDO_APP).grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(quadro, textvariable=var_estado, values=["pronta", "suspensa"],
                     state="readonly").grid(row=1, column=1, sticky="ew", pady=6)
        quadro.columnconfigure(1, weight=1)
        tk.Label(janela,
                 text="O estado executando é sempre decidido pelo escalonador.\n"
                      "Uma suspensão manual permanece por um tick.",
                 bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO, justify=tk.LEFT).pack(anchor="w", padx=18, pady=8)
        def aplicar_estado():
            try:
                self.simulador.alterar_estado_tarefa(int(var_id.get()), var_estado.get())
            except ValueError as erro:
                messagebox.showerror("Alteração inválida", str(erro), parent=janela)
                return
            self.svg_exportado_automaticamente = False
            self._apos_mudanca_de_estado()
            janela.destroy()
        ttk.Button(janela, text="Aplicar", style="Accent.TButton",
                   command=aplicar_estado).pack(pady=10)

    def _ociosidade_por_cpu(self):
        """Soma os ticks em que cada CPU ficou desligada (requisito 1.2)."""
        total = len(self.simulador.cpus)
        desligado = [0] * total
        blocos, _ = self.simulador.obter_todos_os_blocos()
        ocupadas = set()
        for (_tid, idx_cpu, ini, fim, estado) in blocos:
            if estado != 'executando' or idx_cpu is None:
                continue
            for t in range(ini, fim):
                ocupadas.add((idx_cpu, t))
        for (idx_cpu, _t) in ocupadas:
            desligado[idx_cpu] = desligado[idx_cpu]
        ticks = max(0, self.simulador.historico[-1]['tick'] - self.simulador.historico[0]['tick']) \
            if self.simulador.historico else 0
        for idx in range(total):
            ativos = sum(1 for (_c, t) in ocupadas if _c == idx)
            desligado[idx] = max(0, ticks - ativos)
        partes = [f"CPU{i}={desligado[i]}" for i in range(total) if desligado[i] > 0]
        return ", ".join(partes)


    def abrir_relatorio_metricas(self):
        """Mostra Tt, Tw, tr, trocas e aproveitamento (capítulo 6 do livro)."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue uma configuração primeiro.")
            return
        janela = tk.Toplevel(self)
        janela.title("Métricas da simulação")
        janela.geometry("560x460")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)
        tk.Label(janela, text="Métricas de escalonamento", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=16, pady=(14, 8))
        texto = tk.Text(janela, wrap="none", font=("Consolas", 9), height=20)
        texto.insert("1.0", self.simulador.texto_metricas())
        texto.configure(state="disabled")
        texto.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        ttk.Button(janela, text="Fechar", style="Accent.TButton",
                   command=janela.destroy).pack(pady=(0, 14))

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
        except Exception as erro:
            messagebox.showerror('Erro ao exportar automaticamente', str(erro))

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
        snap = s.historico[s.indice_historico]
        jobs = snap.get('jobs', {})
        prontos = sum(1 for j in jobs.values() if j['estado'] == 'pronta')
        executando = sum(1 for j in jobs.values() if j['estado'] == 'executando')
        suspensos = sum(1 for j in jobs.values() if j['estado'] == 'suspensa')
        texto += f"   |   Jobs: {prontos} prontos, {executando} executando, {suspensos} suspensos"
        ociosidade = self._ociosidade_por_cpu()
        if ociosidade:
            texto += "   |   CPUs desligadas (ticks): " + ociosidade
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
        altura_total = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA + ESPACO_REGUA + 20
        canvas.configure(scrollregion=(0, 0, largura_total, altura_total))

        def x_do_tick(tk_):
            return MARGEM_ESQUERDA + (tk_ - tick_inicial) * LARGURA_TICK

        y_fim_grade = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA + ESPACO_REGUA
        for tk_ in range(tick_inicial, tick_atual + 1):
            if (tk_ - tick_inicial) % 5 == 0:
                x = x_do_tick(tk_)
                canvas.create_line(x, MARGEM_TOPO, x, y_fim_grade, fill=COR_GRADE)
                canvas.create_text(x, MARGEM_TOPO + n_tarefas * ALTURA_LINHA + 12, text=str(tk_), font=("Helvetica", 8), fill="#666666")

        y_por_tarefa = {}
        for i, tid in enumerate(ids_tarefas):
            y = MARGEM_TOPO + i * ALTURA_LINHA
            y_por_tarefa[tid] = y
            canvas.create_text(MARGEM_ESQUERDA - 10, y + ALTURA_LINHA / 2, text=f"Tarefa {tid}", anchor="e", font=("Helvetica", 10))
            canvas.create_line(MARGEM_ESQUERDA, y + ALTURA_LINHA, largura_total - 40, y + ALTURA_LINHA, fill=COR_GRADE)

        y_cpus_topo = MARGEM_TOPO + n_tarefas * ALTURA_LINHA + ESPACO_REGUA
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