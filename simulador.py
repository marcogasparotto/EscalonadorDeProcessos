# -*- coding: utf-8 -*-
"""
Núcleo do simulador (kernel). Não depende da interface gráfica: roda sozinho,
o que permite o modo completo e testes sem abrir janela.
"""

import copy
import random

from constantes import ATIVACOES_POR_TAREFA
from escalonadores import ALGORITMOS_DE_ESCALONAMENTO
from job import Job


class Simulador:
    """Núcleo do simulador, executado rigorosamente um tick por passo.

    Cada tarefa possui um TCB dinâmico (dicionário em `estado_tarefas`) e uma
    fila de Jobs. Um Job é uma ativação periódica independente. Isso é
    essencial porque uma nova ativação pode chegar enquanto uma anterior ainda
    está pronta, executando ou bloqueada. O escalonador escolhe Jobs, mas a
    interface apresenta o estado agregado por tarefa.
    """

    def __init__(self, algoritmo, quantum, num_cpus, tarefas, semente=0):
        self.algoritmo = algoritmo
        self.quantum = quantum
        self.num_cpus = num_cpus
        self.definicoes = tarefas
        self.tarefas_por_id = {t.id: t for t in tarefas}
        self.semente = semente
        self.rng = random.Random(semente)   # próprio, para o sorteio ser reproduzível
        self.tick = 0
        self.estado_tarefas = {}
        self.jobs = {}                      # id do job -> Job
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
        """Job mais representativo da tarefa para a interface."""
        ativos = [j for j in self.jobs.values()
                  if j.tarefa == tid and j.estado != 'concluido']
        if not ativos:
            return None
        ordem = {'executando': 0, 'suspensa': 1, 'pronta': 2}
        return min(ativos, key=lambda j: (ordem.get(j.estado, 9), j.liberacao, j.numero))

    def _sincronizar_tcbs(self):
        """Projeta a fila de jobs no TCB agregado consumido pela interface."""
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            ativos = sorted([j for j in self.jobs.values()
                             if j.tarefa == t.id and j.estado != 'concluido'],
                            key=lambda j: (j.liberacao, j.numero))
            et['jobs_pendentes'] = [j.id for j in ativos]
            et['concluidas'] = sum(1 for j in self.jobs.values()
                                   if j.tarefa == t.id and j.estado == 'concluido')
            visivel = self._job_visivel(t.id)
            if visivel is None:
                terminou = (et['instancias_liberadas'] >= ATIVACOES_POR_TAREFA
                            and et['concluidas'] >= ATIVACOES_POR_TAREFA)
                et.update({
                    'liberacao_atual': None, 'prazo_abs_atual': None,
                    'restante_atual': 0,
                    'estado': 'concluida' if terminou else 'nao_chegou',
                    'cpu': None, 'execucao_continua_desde': None,
                    'eventos_pendentes': [], 'bloqueio_fim': None,
                    'deadline_perdido': False,
                })
            else:
                et.update({
                    'liberacao_atual': visivel.liberacao,
                    'prazo_abs_atual': visivel.prazo_abs,
                    'restante_atual': visivel.restante,
                    'estado': visivel.estado, 'cpu': visivel.cpu,
                    'execucao_continua_desde': visivel.execucao_continua_desde,
                    'eventos_pendentes': list(visivel.eventos_pendentes),
                    'bloqueio_fim': visivel.bloqueio_fim,
                    'deadline_perdido': any(j.deadline_perdido for j in ativos),
                })

    def _criar_job(self, tarefa):
        et = self.estado_tarefas[tarefa.id]
        numero = et['instancias_liberadas'] + 1
        jid = self.proximo_job_id
        self.proximo_job_id += 1
        self.jobs[jid] = Job(jid, tarefa.id, numero, self.tick,
                             self.tick + tarefa.prazo, tarefa.duracao, tarefa.eventos)
        et['instancias_liberadas'] += 1
        return jid

    def _desvincular_job(self, jid):
        """Tira o job da CPU nos dois lados (CPU e job), para não ficarem inconsistentes."""
        for cpu in self.cpus:
            if cpu.get('job') == jid:
                cpu['job'] = None
                cpu['tarefa'] = None
                cpu['ligada'] = False
        job = self.jobs[jid]
        job.cpu = None
        job.execucao_continua_desde = None

    def _processar_tick(self, tick):
        """Processa conclusões, desbloqueios, deadlines, eventos e liberações."""
        eventos = []

        # O intervalo anterior termina neste tick; concluir vem antes do deadline,
        # então um job que termina exatamente no prazo NÃO conta como atrasado.
        for jid, job in list(self.jobs.items()):
            if job.estado == 'executando' and job.restante <= 0:
                job.restante = 0
                self._desvincular_job(jid)
                job.estado = 'concluido'
                job.conclusao = tick
                ultima = (self.estado_tarefas[job.tarefa]['instancias_liberadas'] >= ATIVACOES_POR_TAREFA
                          and sum(1 for j in self.jobs.values()
                                  if j.tarefa == job.tarefa and j.estado == 'concluido')
                          >= ATIVACOES_POR_TAREFA)
                eventos.append({'tipo': 'conclusao_tarefa' if ultima else 'conclusao_instancia',
                                'tarefa': job.tarefa, 'job': jid})

        for jid, job in self.jobs.items():
            if (job.estado == 'suspensa' and job.bloqueio_fim is not None
                    and tick >= job.bloqueio_fim):
                job.estado = 'pronta'
                job.bloqueio_fim = None
                job.motivo_suspensao = None

        for jid, job in self.jobs.items():
            if (job.estado in ('pronta', 'executando', 'suspensa')
                    and not job.deadline_perdido and job.restante > 0
                    and tick >= job.prazo_abs):
                job.deadline_perdido = True
                eventos.append({'tipo': 'deadline_miss', 'tarefa': job.tarefa, 'job': jid})

        # Eventos são medidos em tempo efetivo de CPU da ativação (convenção
        # provisória: o formato definitivo pertence ao Projeto B).
        for jid, job in list(self.jobs.items()):
            if job.estado not in ('pronta', 'executando'):
                continue
            restantes = []
            disparou = False
            for desloc, dur in job.eventos_pendentes:
                if not disparou and desloc <= job.tempo_cpu:
                    self._desvincular_job(jid)
                    job.estado = 'suspensa'
                    job.bloqueio_fim = tick + dur
                    job.motivo_suspensao = 'evento'
                    disparou = True
                    eventos.append({'tipo': 'suspensao', 'tarefa': job.tarefa, 'job': jid})
                else:
                    restantes.append((desloc, dur))
            job.eventos_pendentes = restantes

        # Liberações periódicas: ingresso + k * período, no máximo 10 por tarefa.
        for t in self.definicoes:
            et = self.estado_tarefas[t.id]
            if et['instancias_liberadas'] >= ATIVACOES_POR_TAREFA:
                continue
            proxima = t.ingresso + et['instancias_liberadas'] * t.periodo
            if tick >= proxima:
                jid = self._criar_job(t)
                eventos.append({'tipo': 'chegada', 'tarefa': t.id, 'job': jid})

        self._sincronizar_tcbs()
        return eventos

    def _prioridade_primaria(self, jid):
        """Prioridade dada pelo algoritmo escolhido (menor = mais prioritário).

        Vem do registro plugável (req. 4.2): um algoritmo novo registrado passa
        a valer sem alterar o núcleo da simulação."""
        job = self.jobs[jid]
        tarefa = self.tarefas_por_id[job.tarefa]
        return ALGORITMOS_DE_ESCALONAMENTO[self.algoritmo]['funcao'](tarefa, job)

    def _chave_job(self, jid, incumbentes):
        """Prioridade do algoritmo, rodízio do quantum e desempates 1 a 4 (req. 4.3)."""
        job = self.jobs[jid]
        tarefa = self.tarefas_por_id[job.tarefa]
        primaria = self._prioridade_primaria(jid)
        # Rodízio (quantum): quem esgotou a fatia fica atrás dos jobs de mesma
        # prioridade que ainda não esgotaram. Entre os que esgotaram, sai
        # primeiro quem foi para o fim da fila antes (FIFO, como no round-robin).
        # Isso só reordena empates da prioridade primária, então RM/EDF seguem
        # valendo entre prioridades diferentes.
        rodizio = (0, 0) if job.fim_fila_desde is None else (1, job.fim_fila_desde)
        # Critério 1 (quem já executava fica) só protege quem ainda tem quantum;
        # sem essa exceção o job que esgotou a fatia nunca sairia da CPU.
        incumbente = 0 if (jid in incumbentes and job.fim_fila_desde is None) else 1
        return (primaria, rodizio, incumbente,
                job.prazo_abs, tarefa.ingresso, tarefa.duracao)

    def _aplicar_quantum(self, elegiveis):
        """Manda para o fim da fila quem esgotou o quantum (req. 3.3: quantum é o
        tempo máximo que uma tarefa executa sem ser reescalonada).

        Só faz sentido trocar se existir outro job elegível com a MESMA
        prioridade primária para revezar. Sem esse par, o job ganha um quantum
        novo e continua: tirá-lo da CPU deixaria um processador ocioso (req.
        1.2) ou daria a CPU a alguém menos prioritário, violando RM/EDF."""
        prioridade = {jid: self._prioridade_primaria(jid) for jid in elegiveis}
        for jid in elegiveis:
            job = self.jobs[jid]
            if job.estado != 'executando' or job.fatia_usada < self.quantum:
                continue
            tem_par = any(outro != jid and prioridade[outro] == prioridade[jid]
                          for outro in elegiveis)
            if tem_par:
                if job.fim_fila_desde is None:
                    job.fim_fila_desde = self.tick
            else:
                job.fatia_usada = 0

    def _jobs_mais_antigos_por_tarefa(self):
        """Ids das ativações que podem competir por CPU.

        Uma tarefa é um fluxo sequencial de execução: só a ativação não
        concluída mais antiga de cada tarefa pode ocupar uma CPU. As mais
        novas ficam na fila aguardando a predecessora terminar. Sem isso, a
        mesma tarefa executaria em duas CPUs ao mesmo tempo quando a duração
        excede o período."""
        mais_antigo = {}
        for jid, j in self.jobs.items():
            if j.estado == 'concluido':
                continue
            atual = mais_antigo.get(j.tarefa)
            if atual is None or j.numero < self.jobs[atual].numero:
                mais_antigo[j.tarefa] = jid
        return set(mais_antigo.values())

    def _escalonar(self):
        """Aplica RM/EDF, o rodízio por quantum e os cinco desempates do enunciado."""
        eventos = []
        mais_antigo = self._jobs_mais_antigos_por_tarefa()
        elegiveis = [jid for jid, j in self.jobs.items()
                     if jid in mais_antigo and j.estado in ('pronta', 'executando')]
        self._aplicar_quantum(elegiveis)
        incumbentes = {cpu.get('job') for cpu in self.cpus if cpu.get('job') is not None}
        elegiveis.sort(key=lambda jid: self._chave_job(jid, incumbentes))
        vagas = min(self.num_cpus, len(elegiveis))

        # Critério 5: sorteio, só quando há empate na fronteira das vagas.
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
                                    'tarefa': self.jobs[jid].tarefa, 'job': jid})

        selecionados = elegiveis[:vagas]

        # Cada job mantém a CPU em que já estava (evita migrações artificiais).
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

        # Preempção: quem executava e não foi selecionado volta para a fila.
        # O evento diz o motivo, para o Gantt mostrar um símbolo para cada um:
        # fim do quantum (rodízio) ou chegada de alguém mais prioritário.
        for jid, job in self.jobs.items():
            if job.estado == 'executando' and jid not in selecionados:
                tipo = 'fim_quantum' if job.fim_fila_desde is not None else 'preempcao'
                eventos.append({'tipo': tipo, 'tarefa': job.tarefa, 'job': jid})
                job.estado = 'pronta'
                job.cpu = None
                job.execucao_continua_desde = None

        for idx, cpu in enumerate(self.cpus):
            jid = atribuicoes.get(idx)
            if jid is None:
                cpu.update({'ligada': False, 'tarefa': None, 'job': None})
                continue
            job = self.jobs[jid]
            nova_fatia = job.estado != 'executando' or job.cpu != idx
            cpu.update({'ligada': True, 'tarefa': job.tarefa, 'job': jid})
            job.estado = 'executando'
            job.cpu = idx
            if nova_fatia:
                job.trocas += 1   # troca de contexto: Pronta -> Executando
                job.execucao_continua_desde = self.tick
                job.fatia_usada = 0          # entrou na CPU: quantum novo
                job.fim_fila_desde = None
            elif job.fim_fila_desde is not None:
                # Esgotou o quantum mas continua, porque havia CPU para todos
                # os de mesma prioridade: começa um quantum novo sem troca.
                job.fatia_usada = 0
                job.fim_fila_desde = None

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
                job.restante -= 1
                job.tempo_cpu += 1
                job.fatia_usada += 1          # consome o quantum
                if job.primeira_execucao is None:
                    job.primeira_execucao = inicio   # tempo de resposta (tr)
                blocos.append((job.tarefa, idx, inicio, fim, 'executando'))
        for job in self.jobs.values():
            if job.estado == 'suspensa':
                blocos.append((job.tarefa, None, inicio, fim, 'suspensa'))
            elif job.estado == 'pronta' and job.conclusao is None:
                job.tempo_espera += 1                # tempo de espera (tw)
        self.tick = fim
        eventos = self._processar_tick(self.tick)
        eventos += self._escalonar()
        self._sincronizar_tcbs()
        self.finalizado = all(
            self.estado_tarefas[t.id]['instancias_liberadas'] >= ATIVACOES_POR_TAREFA and
            self.estado_tarefas[t.id]['concluidas'] >= ATIVACOES_POR_TAREFA
            for t in self.definicoes
        )
        self._registrar_snapshot(eventos, blocos)
        return True

    def executar_completo(self, limite_de_seguranca=200000):
        # Se o usuário retrocedeu antes, volta ao fim do histórico: sem isso os
        # passos novos seriam anexados depois de snapshots antigos e o Gantt
        # mostraria blocos e eventos duplicados.
        if self.indice_historico < len(self.historico) - 1:
            self._restaurar_snapshot(len(self.historico) - 1)
        passos = 0
        while not self.finalizado:
            if passos >= limite_de_seguranca:
                raise RuntimeError('A simulação excedeu o limite de segurança de passos.')
            self.passo()
            passos += 1
        self.indice_historico = len(self.historico) - 1

    # ------------------------------ histórico ------------------------------
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
        """Reconstrói com os parâmetros novos até o tick selecionado.

        Limitação conhecida: o passado também é recalculado com os parâmetros
        novos."""
        alvo_tick = self.tick if indice_alvo is None else self.historico[indice_alvo]['tick']
        self.tarefas_por_id = {t.id: t for t in self.definicoes}
        self.reiniciar()
        while self.tick < alvo_tick and not self.finalizado:
            self.passo()
        self.indice_historico = len(self.historico) - 1

    def alterar_estado_tarefa(self, tid, novo_estado):
        """Altera o job visível da tarefa no ponto atual e cria uma ramificação."""
        if novo_estado not in ('pronta', 'suspensa'):
            raise ValueError('O estado manual deve ser pronta ou suspensa.')
        job = self._job_visivel(tid)
        if job is None:
            raise ValueError('A tarefa não possui ativação pendente neste tick.')
        self.historico = self.historico[:self.indice_historico + 1]   # descarta o futuro
        self._desvincular_job(job.id)
        job.estado = novo_estado
        job.bloqueio_fim = self.tick + 1 if novo_estado == 'suspensa' else None
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
            'rng_state': self.rng.getstate(),   # sem isso o sorteio não se repete ao voltar
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
        """Tt, Tw, tr e trocas de contexto (capítulo 6) e aproveitamento das CPUs."""
        linhas = []
        total_trocas = 0
        for t in sorted(self.definicoes, key=lambda x: x.id):
            jobs = [j for j in self.jobs.values()
                    if j.tarefa == t.id and j.estado == 'concluido']
            if not jobs:
                continue
            tt = sum((j.conclusao - j.ingresso) for j in jobs) / len(jobs)
            tw = sum(j.tempo_espera for j in jobs) / len(jobs)
            tr = sum((j.primeira_execucao - j.ingresso)
                     for j in jobs if j.primeira_execucao is not None)
            com_resposta = sum(1 for j in jobs if j.primeira_execucao is not None)
            trocas = sum(j.trocas for j in jobs)
            total_trocas += trocas
            linhas.append({
                'tarefa': t.id, 'periodo': t.periodo, 'duracao': t.duracao,
                'prazo': t.prazo, 'ativacoes': len(jobs),
                'tt': tt, 'tw': tw,
                'tr': (tr / com_resposta) if com_resposta else 0.0,
                'trocas': trocas,
                'deadlines_perdidos': sum(1 for j in jobs if j.deadline_perdido),
            })

        if not self.historico:
            return {'linhas': linhas, 'resumo': {}}
        tick_final = self.historico[-1]['tick']
        tick_inicial = self.historico[0]['tick']
        horizonte = max(1, tick_final - tick_inicial)
        tempo_processamento = sum(j.tempo_cpu for j in self.jobs.values())
        capacidade = max(1, self.num_cpus * horizonte)
        resumo = {
            'algoritmo': self.algoritmo,
            'tick_inicial': tick_inicial, 'tick_final': tick_final,
            'horizonte': horizonte,
            'tempo_processamento': tempo_processamento,
            'capacidade_cpu': capacidade,
            'aproveitamento': tempo_processamento / capacidade,
            'ociosidade': 1 - (tempo_processamento / capacidade),
            'trocas_totais': total_trocas,
            'deadlines_perdidos': sum(1 for j in self.jobs.values() if j.deadline_perdido),
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
