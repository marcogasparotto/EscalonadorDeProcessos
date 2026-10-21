# -*- coding: utf-8 -*-
# Declara que o arquivo está em UTF-8, para aceitar acentos nos textos e comentários.

"""
Núcleo do simulador (kernel). Não depende da interface gráfica: roda sozinho,
o que permite o modo completo e testes sem abrir janela.
"""
# Docstring do módulo: explica que este arquivo é o "coração" do simulador, a parte que decide o que acontece a cada tick. Como não usa Tkinter, pode ser testado em linha de comando.

import copy
# Biblioteca padrão para copiar objetos. Usada em deepcopy, que cria cópias independentes dos snapshots do histórico (sem isso, mudanças futuras alterariam o passado gravado).
import random
# Biblioteca padrão de números aleatórios. Usada para o sorteio de desempate (critério 5).

from constantes import ATIVACOES_POR_TAREFA
# Importa o limite de 10 ativações por tarefa (req. 4.4). Depois que uma tarefa atinge esse número, não libera mais jobs.
from escalonadores import ALGORITMOS_DE_ESCALONAMENTO
# Importa o registro de algoritmos (RM, EDF). É o que traduz o nome 'RM' na função de prioridade correspondente.
from job import Job
# Importa a classe Job: uma ativação periódica de uma tarefa, com seu próprio estado e métricas.


class Simulador:
    # Classe central: guarda todo o estado da simulação e oferece métodos para avançar o tempo.
    """Núcleo do simulador, executado rigorosamente um tick por passo.

    Cada tarefa possui um TCB dinâmico (dicionário em `estado_tarefas`) e uma
    fila de Jobs. Um Job é uma ativação periódica independente. Isso é
    essencial porque uma nova ativação pode chegar enquanto uma anterior ainda
    está pronta, executando ou bloqueada. O escalonador escolhe Jobs, mas a
    interface apresenta o estado agregado por tarefa.
    """
    # A docstring explica a ideia central: o escalonador trabalha com JOBS (ativações), enquanto a tela mostra um resumo por TAREFA.

    def __init__(self, algoritmo, quantum, num_cpus, tarefas, semente=0):
        # Construtor. Recebe os parâmetros da simulação. 'semente' controla o sorteio: a mesma semente sempre gera os mesmos sorteios.
        self.algoritmo = algoritmo
        # Nome do algoritmo escolhido, por exemplo 'RM' ou 'EDF'.
        self.quantum = quantum
        # Tamanho da fatia de CPU em ticks. Só tem efeito quando há empate de prioridade (ver _aplicar_quantum).
        self.num_cpus = num_cpus
        # Quantidade de CPUs disponíveis.
        self.definicoes = tarefas
        # Lista das Tarefas lidas do arquivo (dados estáticos, que não mudam durante a simulação).
        self.tarefas_por_id = {t.id: t for t in tarefas}
        # Dicionário para achar uma Tarefa pelo id em tempo constante, por exemplo tarefas_por_id[2].
        self.semente = semente
        # Guarda a semente, para poder recriar o gerador de números aleatórios ao reiniciar.
        self.rng = random.Random(semente)   # próprio, para o sorteio ser reproduzível
        # Gerador de números aleatórios próprio desta simulação. Não usa o gerador global, para que nada externo altere o sorteio.
        self.tick = 0
        # Relógio da simulação. Começa em 0, mas reiniciar() ajusta para o primeiro ingresso.
        self.estado_tarefas = {}
        # TCBs: um dicionário por tarefa com o estado agregado que a interface consome. É preenchido em reiniciar().
        self.jobs = {}                      # id do job -> Job
        # Todas as ativações criadas até agora, indexadas pelo id do job.
        self.proximo_job_id = 1
        # Contador usado para dar um id novo e único a cada job criado.
        self.cpus = []
        # Lista com o estado de cada CPU (ligada, tarefa, job). Preenchida em reiniciar().
        self.historico = []
        # Lista de snapshots, um por tick. Permite avançar e retroceder no tempo sem recalcular tudo.
        self.indice_historico = 0
        # Posição atual dentro do histórico (qual tick está sendo exibido).
        self.finalizado = False
        # Indica que todas as tarefas já completaram suas 10 ativações.

    def _novo_tcb(self):
        # Cria o TCB (estado agregado) de uma tarefa, com todos os campos zerados ou vazios.
        return {
            'instancias_liberadas': 0, 'concluidas': 0,
            # Quantas ativações já foram liberadas e quantas já terminaram.
            'liberacao_atual': None, 'prazo_abs_atual': None,
            # Tick de liberação e prazo absoluto da ativação que a interface deve mostrar.
            'restante_atual': 0, 'estado': 'nao_chegou', 'cpu': None,
            # Ticks de CPU que faltam, estado atual (começa 'nao_chegou') e CPU onde está.
            'execucao_continua_desde': None, 'eventos_pendentes': [],
            # Desde quando executa de forma contínua e lista de eventos ainda não disparados.
            'bloqueio_fim': None, 'deadline_perdido': False,
            # Tick em que termina uma suspensão e se algum prazo já foi perdido.
            'jobs_pendentes': [],
            # Ids dos jobs ainda não concluídos desta tarefa.
        }

    def reiniciar(self):
        """Reinicia o relógio, TCBs, jobs, CPUs, histórico e sorteios."""
        self.tick = min(t.ingresso for t in self.definicoes)
        # O relógio começa no menor ingresso entre as tarefas. Se a primeira tarefa chega no tick 3, a simulação começa no tick 3.
        self.estado_tarefas = {t.id: self._novo_tcb() for t in self.definicoes}
        # Cria um TCB novo para cada tarefa (uma linha do dicionário por tarefa).
        self.jobs = {}
        # Esvazia a lista de jobs, pois a simulação está recomeçando.
        self.proximo_job_id = 1
        # Os ids voltam a começar em 1.
        self.cpus = [{'ligada': False, 'tarefa': None, 'job': None}
                     for _ in range(self.num_cpus)]
        # Cria uma CPU por unidade de num_cpus, todas começando desligadas e sem job.
        self.finalizado = False
        # A simulação ainda não terminou.
        self.historico = []
        # Apaga o histórico anterior.
        self.rng = random.Random(self.semente)
        # Recria o gerador com a mesma semente, para que o sorteio seja idêntico a cada execução.
        eventos = self._processar_tick(self.tick)
        # Processa o primeiro tick: libera as tarefas que chegam nele e registra os eventos gerados.
        eventos += self._escalonar()
        # Decide qual job ocupa cada CPU neste primeiro tick e acrescenta os eventos de escalonamento.
        self._sincronizar_tcbs()
        # Atualiza os TCBs agregados com o estado atual dos jobs.
        self._registrar_snapshot(eventos, [])
        # Grava o estado do tick inicial no histórico. Lista de blocos vazia porque ainda não houve execução.
        self.indice_historico = 0
        # O ponto exibido é o primeiro snapshot.

    def _job_visivel(self, tid):
        """Job mais representativo da tarefa para a interface."""
        ativos = [j for j in self.jobs.values()
                  if j.tarefa == tid and j.estado != 'concluido']
        # Lista de jobs da tarefa 'tid' que ainda não terminaram.
        if not ativos:
            # Se não há nenhum job ativo, a tarefa não tem nada para mostrar.
            return None
        ordem = {'executando': 0, 'suspensa': 1, 'pronta': 2}
        # Ordem de prioridade para a exibição: primeiro o que executa, depois o suspenso, depois o pronto.
        return min(ativos, key=lambda j: (ordem.get(j.estado, 9), j.liberacao, j.numero))
        # Escolhe o job de menor chave: estado mais relevante primeiro, depois o mais antigo (liberação e número) para empates.

    def _sincronizar_tcbs(self):
        """Projeta a fila de jobs no TCB agregado consumido pela interface."""
        for t in self.definicoes:
            # Para cada tarefa, atualiza o TCB correspondente.
            et = self.estado_tarefas[t.id]
            # 'et' é o TCB desta tarefa, um apelido para escrever menos.
            ativos = sorted([j for j in self.jobs.values()
                             if j.tarefa == t.id and j.estado != 'concluido'],
                            key=lambda j: (j.liberacao, j.numero))
            # Lista dos jobs pendentes desta tarefa, ordenada por ordem de chegada (liberação e depois número).
            et['jobs_pendentes'] = [j.id for j in ativos]
            # Guarda só os ids dos jobs pendentes.
            et['concluidas'] = sum(1 for j in self.jobs.values()
                                   if j.tarefa == t.id and j.estado == 'concluido')
            # Conta quantas ativações desta tarefa já terminaram.
            visivel = self._job_visivel(t.id)
            # Escolhe o job que a interface deve mostrar para esta tarefa.
            if visivel is None:
                # Não há job pendente: a tarefa ou ainda não chegou ou já terminou.
                terminou = (et['instancias_liberadas'] >= ATIVACOES_POR_TAREFA
                            and et['concluidas'] >= ATIVACOES_POR_TAREFA)
                # Terminou só se já liberou e concluiu as 10 ativações.
                et.update({
                    'liberacao_atual': None, 'prazo_abs_atual': None,
                    'restante_atual': 0,
                    # Sem job visível, esses campos são zerados.
                    'estado': 'concluida' if terminou else 'nao_chegou',
                    # Se terminou, marca 'concluida'. Caso contrário, 'nao_chegou' (ainda sem ativação pendente).
                    'cpu': None, 'execucao_continua_desde': None,
                    'eventos_pendentes': [], 'bloqueio_fim': None,
                    'deadline_perdido': False,
                    # Zera os demais campos, já que não há nada em andamento.
                })
            else:
                # Há um job visível: copia os dados dele para o TCB.
                et.update({
                    'liberacao_atual': visivel.liberacao,
                    'prazo_abs_atual': visivel.prazo_abs,
                    'restante_atual': visivel.restante,
                    'estado': visivel.estado, 'cpu': visivel.cpu,
                    'execucao_continua_desde': visivel.execucao_continua_desde,
                    'eventos_pendentes': list(visivel.eventos_pendentes),
                    # list(...) cria uma cópia da lista, para que o TCB não compartilhe a mesma lista com o job.
                    'bloqueio_fim': visivel.bloqueio_fim,
                    'deadline_perdido': any(j.deadline_perdido for j in ativos),
                    # Marca como perdido se QUALQUER ativação pendente já estourou o prazo.
                })

    def _criar_job(self, tarefa):
        et = self.estado_tarefas[tarefa.id]
        # TCB da tarefa que está liberando uma nova ativação.
        numero = et['instancias_liberadas'] + 1
        # Número desta ativação (1ª, 2ª, ...). Antes de incrementar, já havia 'instancias_liberadas' liberadas.
        jid = self.proximo_job_id
        # Id do novo job.
        self.proximo_job_id += 1
        # Prepara o próximo id, para que nenhum job receba o mesmo número.
        self.jobs[jid] = Job(jid, tarefa.id, numero, self.tick,
                             self.tick + tarefa.prazo, tarefa.duracao, tarefa.eventos)
        # Cria o Job. Argumentos: id, tarefa, número da ativação, tick de liberação, prazo absoluto (liberação + prazo relativo), duração de CPU e eventos.
        et['instancias_liberadas'] += 1
        # Registra que mais uma ativação foi liberada.
        return jid
        # Devolve o id do job criado (quem chamou usa para registrar o evento de chegada).

    def _desvincular_job(self, jid):
        """Tira o job da CPU nos dois lados (CPU e job), para não ficarem inconsistentes."""
        for cpu in self.cpus:
            # Procura em todas as CPUs se alguma está executando este job.
            if cpu.get('job') == jid:
                # Achou: a CPU deixa de apontar para o job.
                cpu['job'] = None
                cpu['tarefa'] = None
                cpu['ligada'] = False
                # A CPU fica desligada e vazia.
        job = self.jobs[jid]
        # Pega o job para atualizar o outro lado da ligação.
        job.cpu = None
        # O job não está mais em nenhuma CPU.
        job.execucao_continua_desde = None
        # Zera o marcador de execução contínua, porque a execução foi interrompida.

    def _processar_tick(self, tick):
        """Processa conclusões, desbloqueios, deadlines, eventos e liberações."""
        eventos = []
        # Lista de eventos ocorridos neste tick (conclusão, suspensão, deadline, chegada).

        # O intervalo anterior termina neste tick; concluir vem antes do deadline,
        # então um job que termina exatamente no prazo NÃO conta como atrasado.
        for jid, job in list(self.jobs.items()):
            # Percorre uma cópia da lista de jobs. A cópia é necessária porque o laço pode modificar o estado dos jobs.
            if job.estado == 'executando' and job.restante <= 0:
                # Um job em execução que não tem mais tempo de CPU terminou.
                job.restante = 0
                # Garante que o restante fique em zero (nunca negativo).
                self._desvincular_job(jid)
                # Tira o job da CPU.
                job.estado = 'concluido'
                # Marca como concluído.
                job.conclusao = tick
                # Registra o tick de conclusão (usado nas métricas Tt).
                ultima = (self.estado_tarefas[job.tarefa]['instancias_liberadas'] >= ATIVACOES_POR_TAREFA
                          and sum(1 for j in self.jobs.values()
                                  if j.tarefa == job.tarefa and j.estado == 'concluido')
                          >= ATIVACOES_POR_TAREFA)
                # Verifica se esta é a última ativação da tarefa: já foram liberadas as 10 e todas as 10 concluídas.
                eventos.append({'tipo': 'conclusao_tarefa' if ultima else 'conclusao_instancia',
                                'tarefa': job.tarefa, 'job': jid})
                # Registra o evento. O tipo diferencia a última conclusão das demais, para o Gantt desenhar símbolos distintos.

        for jid, job in self.jobs.items():
            # Verifica se alguma suspensão por evento já terminou.
            if (job.estado == 'suspensa' and job.bloqueio_fim is not None
                    and tick >= job.bloqueio_fim):
                # O job está suspenso e o tempo de bloqueio chegou ao fim.
                job.estado = 'pronta'
                # Volta para a fila de prontos.
                job.bloqueio_fim = None
                # Limpa o instante de desbloqueio.
                job.motivo_suspensao = None
                # Limpa o motivo da suspensão.

        for jid, job in self.jobs.items():
            # Verifica prazos estourados.
            if (job.estado in ('pronta', 'executando', 'suspensa')
                    and not job.deadline_perdido and job.restante > 0
                    and tick >= job.prazo_abs):
                # Condições: o job ainda não terminou, ainda não foi marcado como atrasado, ainda precisa de CPU e o tick atual alcançou o prazo absoluto.
                job.deadline_perdido = True
                # Marca o atraso. A marcação acontece uma única vez por job.
                eventos.append({'tipo': 'deadline_miss', 'tarefa': job.tarefa, 'job': jid})
                # Registra o evento de estouro de prazo.

        # Eventos são medidos em tempo efetivo de CPU da ativação (convenção
        # provisória: o formato definitivo pertence ao Projeto B).
        for jid, job in list(self.jobs.items()):
            # Percorre uma cópia, porque a suspensão pode alterar o estado do job.
            if job.estado not in ('pronta', 'executando'):
                # Só jobs prontos ou executando podem ser suspensos por evento.
                continue
                # Pula os demais.
            restantes = []
            # Lista dos eventos que ainda não dispararam.
            disparou = False
            # Garante que no máximo um evento dispare por tick.
            for desloc, dur in job.eventos_pendentes:
                # Cada evento é um par (deslocamento, duração do bloqueio).
                if not disparou and desloc <= job.tempo_cpu:
                    # Dispara quando o job já consumiu CPU suficiente para alcançar o deslocamento do evento.
                    self._desvincular_job(jid)
                    # Tira o job da CPU, pois ele vai bloquear.
                    job.estado = 'suspensa'
                    # Muda o estado para suspensa.
                    job.bloqueio_fim = tick + dur
                    # Calcula o tick em que o bloqueio termina.
                    job.motivo_suspensao = 'evento'
                    # Registra a causa.
                    disparou = True
                    # Impede que outro evento dispare neste mesmo tick.
                    eventos.append({'tipo': 'suspensao', 'tarefa': job.tarefa, 'job': jid})
                    # Registra o evento para o Gantt.
                else:
                    restantes.append((desloc, dur))
                    # Evento ainda não atingido (ou outro já disparou neste tick): mantém na lista.
            job.eventos_pendentes = restantes
            # Atualiza a lista de eventos do job, sem o que acabou de disparar.

        # Liberações periódicas: ingresso + k * período, no máximo 10 por tarefa.
        for t in self.definicoes:
            # Para cada tarefa, verifica se é hora de liberar nova ativação.
            et = self.estado_tarefas[t.id]
            # TCB da tarefa.
            if et['instancias_liberadas'] >= ATIVACOES_POR_TAREFA:
                # Já liberou as 10 ativações: não libera mais.
                continue
            proxima = t.ingresso + et['instancias_liberadas'] * t.periodo
            # Tick da próxima liberação: ingresso + k * período, onde k é o número de ativações já liberadas.
            if tick >= proxima:
                # Chegou a hora (ou já passou, caso algo tenha sido pulado).
                jid = self._criar_job(t)
                # Cria a nova ativação.
                eventos.append({'tipo': 'chegada', 'tarefa': t.id, 'job': jid})
                # Registra a chegada.

        self._sincronizar_tcbs()
        # Atualiza os TCBs agregados, já que jobs podem ter mudado de estado.
        return eventos
        # Devolve a lista de eventos deste tick.

    def _prioridade_primaria(self, jid):
        """Prioridade dada pelo algoritmo escolhido (menor = mais prioritário).

        Vem do registro plugável (req. 4.2): um algoritmo novo registrado passa
        a valer sem alterar o núcleo da simulação."""
        job = self.jobs[jid]
        # Job cuja prioridade será calculada.
        tarefa = self.tarefas_por_id[job.tarefa]
        # Tarefa dona do job (o algoritmo pode precisar do período ou do prazo relativo dela).
        return ALGORITMOS_DE_ESCALONAMENTO[self.algoritmo]['funcao'](tarefa, job)
        # Busca no registro a função do algoritmo atual e a chama com a tarefa e o job. Para RM devolve o período, para EDF o prazo absoluto.

    def _chave_job(self, jid, incumbentes):
        """Prioridade do algoritmo, rodízio do quantum e desempates 1 a 4 (req. 4.3)."""
        job = self.jobs[jid]
        # Job a ser avaliado.
        tarefa = self.tarefas_por_id[job.tarefa]
        # Tarefa dona do job, usada nos desempates finais.
        primaria = self._prioridade_primaria(jid)
        # Critério principal, vindo do algoritmo (RM ou EDF).
        # Rodízio (quantum): quem esgotou a fatia fica atrás dos jobs de mesma
        # prioridade que ainda não esgotaram. Entre os que esgotaram, sai
        # primeiro quem foi para o fim da fila antes (FIFO, como no round-robin).
        # Isso só reordena empates da prioridade primária, então RM/EDF seguem
        # valendo entre prioridades diferentes.
        rodizio = (0, 0) if job.fim_fila_desde is None else (1, job.fim_fila_desde)
        # Se o job não está no fim da fila, a chave é (0, 0): fica à frente. Se está, é (1, tick em que foi para o fim): os que foram antes saem primeiro.
        # Critério 1 (quem já executava fica) só protege quem ainda tem quantum;
        # sem essa exceção o job que esgotou a fatia nunca sairia da CPU.
        incumbente = 0 if (jid in incumbentes and job.fim_fila_desde is None) else 1
        # 0 = já estava na CPU e ainda tem quantum (ganha o empate). 1 = qualquer outro caso. Quem esgotou a fatia perde esse benefício.
        return (primaria, rodizio, incumbente,
                job.prazo_abs, tarefa.ingresso, tarefa.duracao)
        # Tupla comparada pelo sort: prioridade do algoritmo, depois rodízio, depois incumbência, depois prazo absoluto, depois ingresso e duração (desempates finais).

    def _aplicar_quantum(self, elegiveis):
        """Manda para o fim da fila quem esgotou o quantum (req. 3.3: quantum é o
        tempo máximo que uma tarefa executa sem ser reescalonada).

        Só faz sentido trocar se existir outro job elegível com a MESMA
        prioridade primária para revezar. Sem esse par, o job ganha um quantum
        novo e continua: tirá-lo da CPU deixaria um processador ocioso (req.
        1.2) ou daria a CPU a alguém menos prioritário, violando RM/EDF."""
        prioridade = {jid: self._prioridade_primaria(jid) for jid in elegiveis}
        # Calcula de uma vez a prioridade de todos os elegíveis, para não recalcular a cada comparação.
        for jid in elegiveis:
            job = self.jobs[jid]
            # Job atual do laço.
            if job.estado != 'executando' or job.fatia_usada < self.quantum:
                # Só interessa quem está executando e já usou pelo menos 'quantum' ticks. Os demais são ignorados.
                continue
            tem_par = any(outro != jid and prioridade[outro] == prioridade[jid]
                          for outro in elegiveis)
            # Verifica se existe algum outro elegível com a mesma prioridade. Sem esse par não há com quem revezar.
            if tem_par:
                if job.fim_fila_desde is None:
                    # Só marca se ainda não estava marcado, para não reiniciar a contagem de fila.
                    job.fim_fila_desde = self.tick
                    # Guarda o tick em que foi para o fim da fila.
            else:
                job.fatia_usada = 0
                # Sem par: zera a fatia, e o job continua na CPU com um quantum novo.

    def _jobs_mais_antigos_por_tarefa(self):
        """Ids das ativações que podem competir por CPU.

        Uma tarefa é um fluxo sequencial de execução: só a ativação não
        concluída mais antiga de cada tarefa pode ocupar uma CPU. As mais
        novas ficam na fila aguardando a predecessora terminar. Sem isso, a
        mesma tarefa executaria em duas CPUs ao mesmo tempo quando a duração
        excede o período."""
        mais_antigo = {}
        # Dicionário: id da tarefa -> id do job mais antigo ainda não concluído dela.
        for jid, j in self.jobs.items():
            if j.estado == 'concluido':
                # Jobs concluídos não concorrem por CPU.
                continue
            atual = mais_antigo.get(j.tarefa)
            # O job mais antigo registrado até agora para esta tarefa (ou None).
            if atual is None or j.numero < self.jobs[atual].numero:
                # Primeiro job visto da tarefa, ou um mais antigo que o registrado: troca.
                mais_antigo[j.tarefa] = jid
        return set(mais_antigo.values())
        # Devolve o conjunto dos ids de um job por tarefa: o que pode disputar CPU.

    def _escalonar(self):
        """Aplica RM/EDF, o rodízio por quantum e os cinco desempates do enunciado."""
        eventos = []
        # Lista de eventos gerados por esta rodada de escalonamento.
        mais_antigo = self._jobs_mais_antigos_por_tarefa()
        # Conjunto dos jobs que podem competir (um por tarefa).
        elegiveis = [jid for jid, j in self.jobs.items()
                     if jid in mais_antigo and j.estado in ('pronta', 'executando')]
        # Candidatos: jobs elegíveis que estão prontos ou já executando.
        self._aplicar_quantum(elegiveis)
        # Marca quem esgotou o quantum e precisa ceder vez.
        incumbentes = {cpu.get('job') for cpu in self.cpus if cpu.get('job') is not None}
        # Conjunto dos jobs que estão nas CPUs agora, usado no critério de incumbência.
        elegiveis.sort(key=lambda jid: self._chave_job(jid, incumbentes))
        # Ordena os candidatos do mais prioritário para o menos prioritário.
        vagas = min(self.num_cpus, len(elegiveis))
        # Quantas CPUs podem ser ocupadas: o menor entre as CPUs existentes e os candidatos.

        # Critério 5: sorteio, só quando há empate na fronteira das vagas.
        if 0 < vagas < len(elegiveis):
            # Há mais candidatos do que CPUs, então existe uma fronteira entre quem entra e quem fica de fora.
            fronteira = self._chave_job(elegiveis[vagas - 1], incumbentes)
            # Chave do último job que ainda entra.
            empatados = [jid for jid in elegiveis
                         if self._chave_job(jid, incumbentes) == fronteira]
            # Todos os jobs com a mesma chave da fronteira: estão empatados.
            inicio = min((elegiveis.index(jid) for jid in empatados), default=vagas)
            # Posição do primeiro empatado na lista ordenada. 'default' evita erro se a lista estiver vazia.
            disputadas = vagas - inicio
            # Quantas vagas ainda precisam ser disputadas entre os empatados.
            if 0 < disputadas < len(empatados):
                # Há disputa real: mais empatados do que vagas disponíveis.
                escolhidos = self.rng.sample(empatados, disputadas)
                # Sorteia, sem repetição, quais empatados ocupam as vagas restantes.
                antes = [jid for jid in elegiveis[:inicio] if jid not in empatados]
                # Jobs mais prioritários que a disputa, que entram com certeza.
                depois = [jid for jid in elegiveis if jid not in empatados]
                # Jobs que ficaram depois da disputa (ou que não são empatados).
                elegiveis = antes + escolhidos + [jid for jid in depois if jid not in antes]
                # Remonta a lista: primeiro os certos, depois os sorteados, depois o resto. Assim, os sorteados ocupam a posição da disputa.
                for jid in escolhidos:
                    eventos.append({'tipo': 'sorteio',
                                    'tarefa': self.jobs[jid].tarefa, 'job': jid})
                    # Registra um evento de sorteio para cada job escolhido, para o Gantt mostrar a letra S.

        selecionados = elegiveis[:vagas]
        # Os primeiros da lista, em número igual às vagas, são os que vão executar.

        # Cada job mantém a CPU em que já estava (evita migrações artificiais).
        anteriores = {cpu.get('job'): idx for idx, cpu in enumerate(self.cpus)
                      if cpu.get('job') is not None}
        # Dicionário: id do job -> índice da CPU onde ele estava executando.
        atribuicoes = {}
        # Dicionário final: índice da CPU -> id do job que vai ocupá-la.
        restantes = list(selecionados)
        # Cópia da lista de selecionados, para ir removendo os que já ganharam uma CPU.
        for jid in list(restantes):
            # Percorre uma cópia, pois a lista original é alterada dentro do laço.
            if jid in anteriores:
                # O job já estava em uma CPU: ele mantém a mesma CPU.
                atribuicoes[anteriores[jid]] = jid
                restantes.remove(jid)
        livres = [i for i in range(self.num_cpus) if i not in atribuicoes]
        # Lista das CPUs ainda sem job atribuído.
        for idx, jid in zip(livres, restantes):
            # Emparelha as CPUs livres com os jobs que ainda não têm CPU, na ordem em que aparecem.
            atribuicoes[idx] = jid

        # Preempção: quem executava e não foi selecionado volta para a fila.
        # O evento diz o motivo, para o Gantt mostrar um símbolo para cada um:
        # fim do quantum (rodízio) ou chegada de alguém mais prioritário.
        for jid, job in self.jobs.items():
            if job.estado == 'executando' and jid not in selecionados:
                # Estava executando, mas não foi selecionado: foi preemptado.
                tipo = 'fim_quantum' if job.fim_fila_desde is not None else 'preempcao'
                # Se está marcado como fim de fila, saiu pelo quantum. Caso contrário, saiu porque chegou alguém mais prioritário.
                eventos.append({'tipo': tipo, 'tarefa': job.tarefa, 'job': jid})
                # Registra o evento com o motivo.
                job.estado = 'pronta'
                # Volta para a fila de prontos.
                job.cpu = None
                # Não está mais em nenhuma CPU.
                job.execucao_continua_desde = None
                # A execução contínua acabou.

        for idx, cpu in enumerate(self.cpus):
            # Atualiza cada CPU com o job que lhe foi atribuído.
            jid = atribuicoes.get(idx)
            # Job atribuído a esta CPU, ou None se ela ficou livre.
            if jid is None:
                cpu.update({'ligada': False, 'tarefa': None, 'job': None})
                # Sem job: a CPU é desligada.
                continue
                # Vai para a próxima CPU.
            job = self.jobs[jid]
            # Job que vai executar nesta CPU.
            nova_fatia = job.estado != 'executando' or job.cpu != idx
            # É uma nova fatia se o job não estava executando ou se mudou de CPU. Nova fatia = troca de contexto.
            cpu.update({'ligada': True, 'tarefa': job.tarefa, 'job': jid})
            # Liga a CPU e registra a tarefa e o job que estão nela.
            job.estado = 'executando'
            # Marca o job como executando.
            job.cpu = idx
            # Registra em qual CPU ele está.
            if nova_fatia:
                job.trocas += 1   # troca de contexto: Pronta -> Executando
                # Conta mais uma troca de contexto nas métricas.
                job.execucao_continua_desde = self.tick
                # Marca o tick em que começou esta execução contínua.
                job.fatia_usada = 0          # entrou na CPU: quantum novo
                # Zera o contador de quantum, pois esta é uma fatia nova.
                job.fim_fila_desde = None
                # Não está mais no fim da fila, porque acabou de ganhar a CPU.
            elif job.fim_fila_desde is not None:
                # Continua na mesma CPU, mas estava marcado como expirado. Isso acontece quando havia CPU para todos os de mesma prioridade.
                # Esgotou o quantum mas continua, porque havia CPU para todos
                # os de mesma prioridade: começa um quantum novo sem troca.
                job.fatia_usada = 0
                # Recebe um quantum novo.
                job.fim_fila_desde = None
                # Sai da marcação de fim de fila. Não há troca de contexto, pois não houve interrupção.

        self._sincronizar_tcbs()
        # Atualiza os TCBs com o resultado do escalonamento.
        return eventos
        # Devolve os eventos gerados por esta rodada.

    def passo(self):
        """Executa exatamente um tick: [tick, tick+1)."""
        if self.finalizado:
            # Se a simulação já terminou, não há o que avançar.
            return False
            # Sinaliza que nada foi feito.
        inicio, fim = self.tick, self.tick + 1
        # O tick atual vai de 'inicio' até 'fim' (intervalo semiaberto de duração 1).
        blocos = []
        # Lista dos blocos de execução e suspensão deste tick, para o Gantt.
        for idx, cpu in enumerate(self.cpus):
            # Para cada CPU, verifica se há um job rodando.
            jid = cpu.get('job')
            if jid is not None:
                job = self.jobs[jid]
                # Job que está executando nesta CPU.
                job.restante -= 1
                # Consome um tick do tempo de CPU que falta.
                job.tempo_cpu += 1
                # Conta mais um tick de CPU consumido no total (usado em eventos e métricas).
                job.fatia_usada += 1          # consome o quantum
                # Conta mais um tick da fatia atual, que é o que o quantum limita.
                if job.primeira_execucao is None:
                    job.primeira_execucao = inicio   # tempo de resposta (tr)
                    # Na primeira vez que executa, registra o tick. Usado na métrica tr (tempo de resposta).
                blocos.append((job.tarefa, idx, inicio, fim, 'executando'))
                # Registra o bloco de execução: tarefa, CPU, início, fim e estado.
        for job in self.jobs.values():
            # Para os demais jobs (não executando), registra espera ou suspensão.
            if job.estado == 'suspensa':
                blocos.append((job.tarefa, None, inicio, fim, 'suspensa'))
                # Bloco de suspensão. Não tem CPU, por isso o segundo campo é None.
            elif job.estado == 'pronta' and job.conclusao is None:
                job.tempo_espera += 1                # tempo de espera (tw)
                # Um job pronto e ainda não concluído está esperando por CPU neste tick.
        self.tick = fim
        # Avança o relógio.
        eventos = self._processar_tick(self.tick)
        # Processa o novo tick: conclusões, desbloqueios, deadlines, eventos e chegadas.
        eventos += self._escalonar()
        # Decide quem executa no novo tick e acrescenta os eventos de escalonamento.
        self._sincronizar_tcbs()
        # Atualiza os TCBs agregados.
        self.finalizado = all(
            self.estado_tarefas[t.id]['instancias_liberadas'] >= ATIVACOES_POR_TAREFA and
            self.estado_tarefas[t.id]['concluidas'] >= ATIVACOES_POR_TAREFA
            for t in self.definicoes
        )
        # A simulação termina quando TODAS as tarefas liberaram e concluíram as 10 ativações.
        self._registrar_snapshot(eventos, blocos)
        # Grava o estado deste tick, com os eventos e blocos, no histórico.
        return True
        # Sinaliza que um tick foi executado.

    def executar_completo(self, limite_de_seguranca=200000):
        # Roda a simulação inteira de uma vez, até o fim.
        # Se o usuário retrocedeu antes, volta ao fim do histórico: sem isso os
        # passos novos seriam anexados depois de snapshots antigos e o Gantt
        # mostraria blocos e eventos duplicados.
        if self.indice_historico < len(self.historico) - 1:
            # O usuário está em algum ponto antigo do histórico.
            self._restaurar_snapshot(len(self.historico) - 1)
            # Volta para o último snapshot antes de continuar.
        passos = 0
        # Contador de ticks executados nesta chamada.
        while not self.finalizado:
            # Repete até a simulação terminar.
            if passos >= limite_de_seguranca:
                # Proteção contra laço infinito caso algo dê errado.
                raise RuntimeError('A simulação excedeu o limite de segurança de passos.')
                # Interrompe com erro explicativo.
            self.passo()
            # Executa um tick.
            passos += 1
            # Conta o tick.
        self.indice_historico = len(self.historico) - 1
        # Posiciona a exibição no último tick.

    # ------------------------------ histórico ------------------------------
    def _restaurar_snapshot(self, indice):
        snap = self.historico[indice]
        # Pega o snapshot da posição pedida.
        self.tick = snap['tick']
        # Volta o relógio para o tick salvo.
        self.estado_tarefas = copy.deepcopy(snap['estado_tarefas'])
        # Cópia independente dos TCBs, para que alterações futuras não toquem o snapshot.
        self.jobs = copy.deepcopy(snap['jobs'])
        # Cópia independente dos jobs.
        self.cpus = copy.deepcopy(snap['cpus'])
        # Cópia independente das CPUs.
        self.proximo_job_id = snap['proximo_job_id']
        # Restaura o contador de ids.
        self.finalizado = snap['finalizado']
        # Restaura o indicador de término.
        self.rng.setstate(snap['rng_state'])
        # Restaura o estado do gerador de sorteios, para que os próximos sorteios sejam os mesmos de antes.
        self.indice_historico = indice
        # Atualiza a posição exibida.

    def avancar(self):
        if self.indice_historico < len(self.historico) - 1:
            # Ainda há snapshots futuros já calculados.
            self._restaurar_snapshot(self.indice_historico + 1)
            # Só restaura o próximo, sem recalcular.
            return True
        return self.passo()
        # Está no fim do histórico: calcula um tick novo.

    def retroceder(self):
        if self.indice_historico <= 0:
            # Já está no primeiro snapshot: não há para onde voltar.
            return False
        self._restaurar_snapshot(self.indice_historico - 1)
        # Volta um snapshot.
        return True

    def aplicar_edicao_e_reconstruir(self, indice_alvo=None):
        """Reconstrói com os parâmetros novos até o tick selecionado.

        Limitação conhecida: o passado também é recalculado com os parâmetros
        novos."""
        alvo_tick = self.tick if indice_alvo is None else self.historico[indice_alvo]['tick']
        # Tick até o qual a simulação deve ser reconstruída. Se não foi informado um índice, usa o tick atual.
        self.tarefas_por_id = {t.id: t for t in self.definicoes}
        # Reconstrói o dicionário de tarefas por id, caso as definições tenham mudado.
        self.reiniciar()
        # Recomeça do zero com os parâmetros novos.
        while self.tick < alvo_tick and not self.finalizado:
            # Avança até chegar ao tick alvo.
            self.passo()
        self.indice_historico = len(self.historico) - 1
        # Exibe o último tick calculado.

    def alterar_estado_tarefa(self, tid, novo_estado):
        """Altera o job visível da tarefa no ponto atual e cria uma ramificação."""
        if novo_estado not in ('pronta', 'suspensa'):
            # Só são permitidos esses dois estados manuais. 'executando' é decidido pelo escalonador.
            raise ValueError('O estado manual deve ser pronta ou suspensa.')
        job = self._job_visivel(tid)
        # Job que a interface está mostrando para a tarefa.
        if job is None:
            # Sem job pendente, não há o que alterar.
            raise ValueError('A tarefa não possui ativação pendente neste tick.')
        self.historico = self.historico[:self.indice_historico + 1]   # descarta o futuro
        # Corta o histórico no ponto atual: o futuro, já calculado, deixa de valer e é descartado.
        self._desvincular_job(job.id)
        # Tira o job da CPU, se ele estiver em uma.
        job.estado = novo_estado
        # Aplica o novo estado.
        job.bloqueio_fim = self.tick + 1 if novo_estado == 'suspensa' else None
        # Se for suspensão manual, dura um tick. Se for 'pronta', não há bloqueio.
        self.finalizado = False
        # Como houve alteração, a simulação não está mais finalizada.
        eventos = self._escalonar()
        # Recalcula quem executa a partir da nova situação.
        self._sincronizar_tcbs()
        # Atualiza os TCBs.
        self._substituir_snapshot_atual(eventos)
        # Regrava o snapshot atual com o novo resultado.

    def _substituir_snapshot_atual(self, eventos):
        anterior = self.historico[self.indice_historico]
        # Snapshot que está sendo substituído.
        novo = self._criar_snapshot(anterior.get('eventos', []) + eventos,
                                    anterior.get('blocos_intervalo', []))
        # Cria o novo snapshot mantendo os eventos e blocos antigos e acrescentando os novos eventos.
        self.historico[self.indice_historico] = novo
        # Troca o snapshot antigo pelo novo na mesma posição.

    def _criar_snapshot(self, eventos, blocos_intervalo):
        return {
            'tick': self.tick,
            # Tick em que o snapshot foi tirado.
            'estado_tarefas': copy.deepcopy(self.estado_tarefas),
            # Cópia dos TCBs (deepcopy para não compartilhar objetos com o estado atual).
            'jobs': copy.deepcopy(self.jobs),
            # Cópia dos jobs.
            'cpus': copy.deepcopy(self.cpus),
            # Cópia das CPUs.
            'eventos': copy.deepcopy(eventos),
            # Eventos deste tick.
            'blocos_intervalo': copy.deepcopy(blocos_intervalo),
            # Blocos de execução e suspensão deste tick.
            'proximo_job_id': self.proximo_job_id,
            # Próximo id disponível.
            'finalizado': self.finalizado,
            # Se a simulação havia terminado neste tick.
            'rng_state': self.rng.getstate(),   # sem isso o sorteio não se repete ao voltar
            # Estado do gerador de sorteios neste tick, para que voltar no tempo mantenha os mesmos sorteios.
        }

    def _registrar_snapshot(self, eventos, blocos_intervalo):
        self.historico.append(self._criar_snapshot(eventos, blocos_intervalo))
        # Cria o snapshot e o acrescenta ao final do histórico.
        self.indice_historico = len(self.historico) - 1
        # Aponta a exibição para o snapshot recém-criado.

    def obter_todos_os_blocos(self, ate_indice=None):
        if ate_indice is None:
            # Sem índice informado, considera o histórico inteiro.
            ate_indice = len(self.historico) - 1
        blocos, eventos = [], []
        # Listas acumuladoras de todos os blocos e eventos até o índice pedido.
        for i in range(0, ate_indice + 1):
            # Percorre os snapshots de 0 até ate_indice.
            blocos.extend(self.historico[i]['blocos_intervalo'])
            # Acrescenta os blocos deste snapshot.
            for ev in self.historico[i]['eventos']:
                eventos.append(dict(ev, tick=self.historico[i]['tick']))
                # Copia o evento e acrescenta o tick em que ocorreu. dict(ev, tick=...) cria um dicionário novo, sem alterar o original.
        return blocos, eventos
        # Devolve todos os blocos e eventos juntos, para o Gantt desenhar de uma vez.

    # --------------------------- métricas do livro ---------------------------
    def calcular_metricas(self):
        """Tt, Tw, tr e trocas de contexto (capítulo 6) e aproveitamento das CPUs."""
        linhas = []
        # Uma linha de métricas por tarefa.
        total_trocas = 0
        # Soma de todas as trocas de contexto do sistema.
        for t in sorted(self.definicoes, key=lambda x: x.id):
            # Percorre as tarefas em ordem de id, para o relatório sair ordenado.
            jobs = [j for j in self.jobs.values()
                    if j.tarefa == t.id and j.estado == 'concluido']
            # Só os jobs concluídos entram nas médias. Ativações ainda em andamento não têm tempo de término.
            if not jobs:
                # Tarefa sem nenhuma ativação concluída: não há o que calcular.
                continue
            tt = sum((j.conclusao - j.ingresso) for j in jobs) / len(jobs)
            # Tempo de turnaround médio: do ingresso até a conclusão, em média.
            tw = sum(j.tempo_espera for j in jobs) / len(jobs)
            # Tempo de espera médio: ticks em que o job esteve pronto sem CPU, em média.
            tr = sum((j.primeira_execucao - j.ingresso)
                     for j in jobs if j.primeira_execucao is not None)
            # Soma dos tempos até a primeira execução de cada job (tempo de resposta).
            com_resposta = sum(1 for j in jobs if j.primeira_execucao is not None)
            # Quantos jobs já tiveram alguma execução.
            trocas = sum(j.trocas for j in jobs)
            # Trocas de contexto somadas nos jobs desta tarefa.
            total_trocas += trocas
            # Acumula no total geral.
            linhas.append({
                'tarefa': t.id, 'periodo': t.periodo, 'duracao': t.duracao,
                'prazo': t.prazo, 'ativacoes': len(jobs),
                # Dados de identificação e de quantos jobs entraram na conta.
                'tt': tt, 'tw': tw,
                'tr': (tr / com_resposta) if com_resposta else 0.0,
                # Média de tr. Se nenhum job executou, devolve 0.0 para evitar divisão por zero.
                'trocas': trocas,
                'deadlines_perdidos': sum(1 for j in jobs if j.deadline_perdido),
                # Quantos jobs desta tarefa estouraram o prazo.
            })

        if not self.historico:
            # Sem histórico, não há horizonte para calcular o aproveitamento.
            return {'linhas': linhas, 'resumo': {}}
        tick_final = self.historico[-1]['tick']
        # Último tick registrado.
        tick_inicial = self.historico[0]['tick']
        # Primeiro tick registrado.
        horizonte = max(1, tick_final - tick_inicial)
        # Duração total da simulação. max(1, ...) evita divisão por zero.
        tempo_processamento = sum(j.tempo_cpu for j in self.jobs.values())
        # Total de ticks de CPU realmente usados, somando todos os jobs.
        capacidade = max(1, self.num_cpus * horizonte)
        # Capacidade total disponível: número de CPUs vezes o horizonte.
        resumo = {
            'algoritmo': self.algoritmo,
            'tick_inicial': tick_inicial, 'tick_final': tick_final,
            'horizonte': horizonte,
            'tempo_processamento': tempo_processamento,
            'capacidade_cpu': capacidade,
            'aproveitamento': tempo_processamento / capacidade,
            # Fração da capacidade usada. Ex.: 0.75 significa 75% das CPUs ocupadas.
            'ociosidade': 1 - (tempo_processamento / capacidade),
            # Fração ociosa: o complemento do aproveitamento.
            'trocas_totais': total_trocas,
            'deadlines_perdidos': sum(1 for j in self.jobs.values() if j.deadline_perdido),
        }
        return {'linhas': linhas, 'resumo': resumo}
        # Devolve as linhas por tarefa e o resumo geral.

    def texto_metricas(self):
        """Formata as métricas para exibição na interface."""
        dados = self.calcular_metricas()
        # Calcula as métricas.
        resumo = dados.get('resumo') or {}
        # Pega o resumo, ou dicionário vazio se não houver.
        partes = []
        # Lista de linhas de texto que serão unidas no final.
        if resumo:
            # Só monta o cabeçalho se houver resumo (ou seja, se houver histórico).
            partes.append(
                f"Algoritmo: {resumo['algoritmo']}  |  "
                f"Ticks: {resumo['tick_inicial']} a {resumo['tick_final']} "
                f"({resumo['horizonte']})  |  CPUs: {self.num_cpus}")
            # Primeira linha do resumo: algoritmo, intervalo de ticks e CPUs.
            partes.append(
                f"Tempo de processamento: {resumo['tempo_processamento']}  |  "
                f"Capacidade: {resumo['capacidade_cpu']}  |  "
                f"Aproveitamento: {resumo['aproveitamento']:.1%}  |  "
                f"Ociosidade: {resumo['ociosidade']:.1%}")
            # Segunda linha: uso das CPUs. ':.1%' formata a fração como porcentagem com uma casa decimal.
            partes.append(
                f"Trocas de contexto: {resumo['trocas_totais']}  |  "
                f"Deadlines perdidos: {resumo['deadlines_perdidos']}")
            # Terceira linha: trocas e prazos perdidos.
        partes.append("")
        # Linha em branco separando o resumo da tabela.
        partes.append(f"{'Tar':>4} {'Ativ':>5} {'Tt':>7} {'Tw':>7} {'Tr':>7} "
                      f"{'Trocas':>7} {'Perdas':>7}")
        # Cabeçalho da tabela. ':>4' alinha o texto à direita em 4 caracteres, para as colunas ficarem alinhadas.
        for linha in dados['linhas']:
            # Uma linha da tabela por tarefa.
            partes.append(
                f"{linha['tarefa']:>4} {linha['ativacoes']:>5} "
                f"{linha['tt']:>7.1f} {linha['tw']:>7.1f} {linha['tr']:>7.1f} "
                f"{linha['trocas']:>7} {linha['deadlines_perdidos']:>7}")
            # Formata cada valor com a largura do cabeçalho. ':>7.1f' é um número com uma casa decimal, alinhado à direita.
        return "\n".join(partes)
        # Une todas as linhas em um único texto, separadas por quebra de linha.