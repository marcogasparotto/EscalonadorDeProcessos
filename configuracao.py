# -*- coding: utf-8 -*-
# Declara a codificação do arquivo como UTF-8, para aceitar acentos em português nos comentários e mensagens.

"""Leitura e validação do arquivo de configuração (requisito 3.3)."""
# Docstring do módulo: resume a responsabilidade deste arquivo, que é ler o arquivo de entrada e checar se ele está correto.

import os
# Importa o módulo padrão do Python para lidar com caminhos e arquivos (abspath, expanduser, isfile).

from constantes import MAX_CPUS, PALETA_CORES_PADRAO
# Importa dois valores de constantes.py: o limite máximo de CPUs e a lista de cores sugeridas para tarefas sem cor válida.
# ATENÇÃO: veja a observação 1 no fim. Na versão de constantes.py que você me enviou antes, PALETA_CORES_PADRAO não existe.

from escalonadores import ALGORITMOS_DE_ESCALONAMENTO
# Importa o dicionário de algoritmos registrados (RM, EDF...). Usado para validar o nome do algoritmo lido no arquivo.

from tarefa import Tarefa
# Importa a classe Tarefa, que guarda os dados estáticos de cada tarefa lida.


class Configuracao:
    # Classe "de transporte": só guarda o resultado da leitura para entregar ao resto do programa.
    """Resultado de uma leitura: parâmetros gerais, tarefas e avisos."""

    def __init__(self, algoritmo, quantum, num_cpus, tarefas, avisos):
        # Construtor: recebe os dados já validados e os armazena no objeto.
        self.algoritmo = algoritmo    # nome do algoritmo, em maiúsculas (ex.: 'RM')
        self.quantum = quantum        # tamanho da fatia de CPU, inteiro maior que zero
        self.num_cpus = num_cpus      # quantidade de CPUs que a simulação vai usar
        self.tarefas = tarefas        # lista de objetos Tarefa, já com cores resolvidas
        self.avisos = avisos          # mensagens que não impedem a leitura (aperiódicas ignoradas, cores trocadas)


class CarregadorConfiguracao:
    # Classe responsável pela leitura. Ela não guarda estado: cada chamada de carregar() lê um arquivo do zero.
    """
    Lê o arquivo texto no formato do enunciado:
        linha 1:     algoritmo_escalonamento;quantum;qtde_cpus
        linhas 2..N: id;cor;ingresso;duracao;periodo;prazo;lista_eventos

    Tolerado (nunca é erro): maiúsculas/minúsculas, espaços, linhas em
    branco, ';' no fim da linha, BOM no início do arquivo e qualquer caminho.
    Erros estruturais levantam ValueError com o motivo. Aperiódicas
    (período 0) viram aviso e são ignoradas (req. 4.4). Cor repetida também
    vira aviso: o arquivo segue o formato (req. 3.3.7), então troca-se a cor
    da tarefa repetida por uma livre em vez de recusar o arquivo.
    """
    # A docstring descreve o contrato: o que é aceito, o que é erro e o que é só aviso.

    @staticmethod
    # Marca o método como estático: ele não recebe 'self', então pode ser chamado como CarregadorConfiguracao.normalizar_cor(...).
    def normalizar_cor(valor):
        """Devolve '#RRGGBB' em maiúsculas, ou None se a cor for inválida."""
        v = valor.strip()
        # Copia o texto da cor sem espaços no começo e no fim. Ex.: "  3366CC " vira "3366CC".
        if not v:
            # Se sobrou string vazia, não há cor nenhuma.
            return None
            # Sinaliza erro devolvendo None; quem chamou decide o que fazer.
        if not v.startswith('#'):
            # Aceita cor sem o '#' inicial, por tolerância ao formato.
            v = '#' + v
            # Acrescenta o '#' na frente.
        if len(v) != 7:
            # Uma cor válida tem 7 caracteres: '#' mais 6 dígitos hexadecimais.
            return None
            # Tamanho errado (ex.: '#FFF' ou '#3366CCAA'): inválido.
        try:
            int(v[1:], 16)
            # Tenta interpretar os 6 caracteres depois do '#' como número em base 16. Se algum caractere não for hexadecimal, levanta ValueError.
            # Ver observação 2: esse teste aceita um sinal '-', o que deixa passar algumas cores inválidas.
        except ValueError:
            # Entra aqui se a conversão falhou, ou seja, há caracteres que não são hexadecimais.
            return None
            # Cor inválida.
        return v.upper()
        # Padroniza em maiúsculas, para que '#3366cc' e '#3366CC' sejam tratadas como a mesma cor.

    @staticmethod
    # Método estático de novo: não depende de atributos do objeto.
    def parsear_eventos(campo, contexto="lista de eventos"):
        """
        Lê "deslocamento:duracao,..." (formato provisório; a lista de eventos
        é definida no Projeto B). Levanta ValueError dizendo o que está errado.
        """
        # 'contexto' é só um texto usado nas mensagens de erro, para o usuário saber de qual tarefa veio o problema.
        campo = campo.strip()
        # Remove espaços das pontas do campo de eventos.
        if campo in ('', '-'):
            # Campo vazio ou '-' significam "sem eventos".
            return []
            # Devolve lista vazia: a tarefa não tem eventos.
        eventos, deslocamentos = [], set()
        # 'eventos' acumula os pares (deslocamento, duração). 'deslocamentos' é um conjunto usado para detectar repetições.
        for parte in campo.split(','):
            # Divide o campo pelas vírgulas. Ex.: "2:1,5:3" vira ["2:1", "5:3"]. Cada parte é tratada uma de cada vez.
            parte = parte.strip()
            # Remove espaços em volta de cada evento.
            if not parte or ':' not in parte:
                # Parte vazia (ex.: "2:1,,5:3") ou sem ':' é formato errado.
                raise ValueError(f"{contexto}: evento inválido '{parte}'. Use deslocamento:duração.")
                # Interrompe a leitura com uma mensagem clara. O ValueError é tratado por quem chamou.
            desloc_str, dur_str = parte.split(':', 1)
            # Separa no primeiro ':'. Ex.: "2:1" vira "2" e "1". O limite 1 evita quebrar em mais de um ':'.
            try:
                desloc, dur = int(desloc_str.strip()), int(dur_str.strip())
                # Converte os dois lados para inteiro. Se algum não for número, cai no except.
            except ValueError as erro:
                # Trata o erro de conversão e relança com mensagem amigável.
                raise ValueError(f"{contexto}: evento inválido '{parte}'; use inteiros.") from erro
                # 'from erro' preserva a causa original, útil para depuração.
            if desloc < 0 or dur <= 0:
                # Deslocamento negativo não faz sentido, e duração precisa ser positiva.
                raise ValueError(f"{contexto}: deslocamento >= 0 e duração > 0 são obrigatórios.")
            if desloc in deslocamentos:
                # Dois eventos no mesmo deslocamento seriam ambíguos: o simulador só trata um por vez.
                raise ValueError(f"{contexto}: dois eventos no deslocamento {desloc} não são permitidos.")
            deslocamentos.add(desloc)
            # Registra o deslocamento como usado, para o próximo teste de repetição.
            eventos.append((desloc, dur))
            # Guarda o evento como tupla (deslocamento, duração).
        return sorted(eventos, key=lambda par: par[0])
        # Ordena pelos deslocamentos, para que os eventos sejam processados em ordem cronológica, independentemente da ordem escrita no arquivo.

    def carregar(self, caminho):
        """Lê o arquivo e devolve uma Configuracao (ou levanta ValueError)."""
        caminho = os.path.abspath(os.path.expanduser(caminho.strip()))
        # Remove espaços, expande '~' para a pasta do usuário e converte em caminho absoluto. Assim funciona com caminhos relativos e com '~/...'.
        if not os.path.isfile(caminho):
            # Confere se existe um arquivo (e não uma pasta) nesse caminho.
            raise ValueError(f"Arquivo não encontrado: {caminho}")
            # Erro claro para a interface mostrar.

        # utf-8-sig descarta um BOM, comum em arquivos salvos no Windows
        with open(caminho, 'r', encoding='utf-8-sig') as arquivo:
            # Abre o arquivo para leitura. O 'with' garante que ele será fechado mesmo se houver erro.
            linhas_brutas = arquivo.readlines()
            # Lê todas as linhas, mantendo os '\n' do fim de cada uma.

        linhas = [linha.strip() for linha in linhas_brutas]
        # Remove espaços e quebras de linha de cada linha. Esta é uma lista por compreensão.
        linhas = [linha for linha in linhas if linha != '']
        # Descarta linhas vazias. Por isso a numeração de erros depois conta só linhas não vazias (observação 4).
        if not linhas:
            # Se não sobrou nenhuma linha, o arquivo está vazio ou só tem espaços.
            raise ValueError("O arquivo de configuração está vazio.")

        avisos = []
        # Lista onde serão acumuladas as mensagens não fatais.
        algoritmo, quantum, num_cpus = self._ler_cabecalho(linhas[0])
        # A primeira linha do arquivo é o cabeçalho. A função devolve os três valores já validados.
        tarefas = self._ler_tarefas(linhas[1:], avisos)
        # Todas as demais linhas são tarefas. Os avisos gerados ao ler as tarefas são preenchidos dentro da própria lista 'avisos'.
        if not tarefas:
            # Se nenhuma tarefa foi aceita (todas aperiódicas, por exemplo), não há o que simular.
            raise ValueError("Nenhuma tarefa periódica válida foi encontrada no arquivo.")
        return Configuracao(algoritmo, quantum, num_cpus, tarefas, avisos)
        # Empacota tudo em um objeto Configuracao e devolve.

    # ------------------------------------------------------------------
    def _ler_cabecalho(self, linha):
        # O underline no início indica método "privado": uso interno da classe.
        if linha.endswith(';'):
            # Aceita um ';' sobrando no fim da linha.
            linha = linha[:-1]
            # Remove o último caractere, que é o ';'.
        campos = [c.strip() for c in linha.split(';')]
        # Divide a linha em campos pelo ';' e limpa espaços de cada um.
        if len(campos) != 3:
            # O cabeçalho exige exatamente três campos.
            raise ValueError(
                "Primeira linha inválida. O formato esperado é: "
                "algoritmo_escalonamento;quantum;qtde_cpus"
            )
            # Mensagem que mostra o formato correto.
        algoritmo_bruto, quantum_bruto, cpus_bruto = campos
        # Desempacota os três campos, mantendo os valores originais para usar nas mensagens de erro.

        algoritmo = algoritmo_bruto.upper()
        # Converte o nome do algoritmo para maiúsculas. Assim 'rm' e 'RM' são aceitos.
        if algoritmo not in ALGORITMOS_DE_ESCALONAMENTO:
            # Verifica se o algoritmo está no registro (RM, EDF e qualquer outro registrado depois).
            disponiveis = ', '.join(sorted(ALGORITMOS_DE_ESCALONAMENTO))
            # Monta a lista de algoritmos válidos para exibir na mensagem de erro.
            raise ValueError(
                f"Algoritmo de escalonamento desconhecido: '{algoritmo_bruto}'. "
                f"Algoritmos disponíveis: {disponiveis}."
            )
            # Erro informando o nome digitado e as opções válidas.
        try:
            quantum = int(quantum_bruto)
            # Converte o quantum para inteiro.
            if quantum <= 0:
                # Quantum zero ou negativo não faz sentido.
                raise ValueError
                # Força o salto para o except logo abaixo, reaproveitando a mesma mensagem de erro.
        except ValueError:
            # Entra aqui se não for número ou se for menor ou igual a zero.
            raise ValueError(f"Quantum inválido na primeira linha: '{quantum_bruto}'.")
            # Mensagem com o valor original digitado.
        try:
            num_cpus = int(cpus_bruto)
            # Converte a quantidade de CPUs para inteiro.
            if num_cpus <= 0 or num_cpus > MAX_CPUS:
                # Precisa estar entre 1 e MAX_CPUS (limite defensivo definido em constantes.py).
                raise ValueError
                # Reaproveita o except abaixo.
        except ValueError:
            raise ValueError(f"Quantidade de CPUs inválida: '{cpus_bruto}'. Use 1 a {MAX_CPUS}.")
            # Mensagem com o intervalo permitido.
        return algoritmo, quantum, num_cpus
        # Devolve os três valores validados como uma tupla.

    def _ler_tarefas(self, linhas, avisos):
        tarefas = []
        # Lista que vai receber os objetos Tarefa aceitos.
        ids_vistos = set()
        # Conjunto com os IDs já lidos, para detectar IDs repetidos em tempo constante.

        for numero_linha, linha in enumerate(linhas, start=2):
            # Percorre as linhas de tarefas. 'start=2' faz a contagem começar em 2, porque a linha 1 é o cabeçalho. Assim as mensagens batem com o arquivo (quando não há linhas vazias).
            if linha.endswith(';'):
                # Tolera o ';' sobrando no fim da linha, igual ao cabeçalho.
                linha = linha[:-1]
                # Remove esse ';'.
            campos = [c.strip() for c in linha.split(';')]
            # Divide a linha nos campos e remove espaços de cada um.

            # Os seis primeiros campos são obrigatórios; lista_eventos pode faltar.
            if len(campos) == 6:
                # Seis campos significam que a coluna de eventos foi omitida. Ela é opcional.
                campos.append('')
                # Acrescenta um campo vazio, que depois será lido como "sem eventos".
            elif len(campos) != 7:
                # Nem 6 nem 7: formato errado.
                raise ValueError(f"Linha {numero_linha}: esperados 7 campos; recebidos {len(campos)}.")

            (id_str, cor_str, ingresso_str, duracao_str,
             periodo_str, prazo_str, eventos_str) = campos
            # Desempacota os sete campos em variáveis com nomes descritivos. Os valores ainda são texto.

            try:
                id_tarefa = int(id_str)
                # Converte o ID para inteiro.
            except ValueError:
                # Se não for número, o ID é inválido.
                raise ValueError(f"Linha {numero_linha}: ID inválido ('{id_str}').")
            if id_tarefa in ids_vistos:
                # Se o ID já apareceu em uma tarefa anterior periódica, é duplicado.
                raise ValueError(f"Linha {numero_linha}: ID {id_tarefa} duplicado.")

            cor = self.normalizar_cor(cor_str)
            # Converte o texto da cor para o formato '#RRGGBB'. Devolve None se for inválida.
            if cor is None:
                raise ValueError(f"Linha {numero_linha}: cor inválida ('{cor_str}').")
                # Cor inválida é erro fatal.

            try:
                ingresso = int(ingresso_str)
                # Instante em que a tarefa chega pela primeira vez.
                if ingresso < 0:
                    # Não existe tempo negativo.
                    raise ValueError
                    # Reaproveita o except.
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: ingresso inválido ('{ingresso_str}').")

            try:
                duracao = int(duracao_str)
                # Tempo de CPU que cada ativação precisa.
                if duracao <= 0:
                    # Uma tarefa precisa de pelo menos 1 tick de CPU.
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: duração inválida ('{duracao_str}').")

            periodo_limpo = periodo_str.strip()
            # Remove espaços do campo período (já sem espaços por causa do strip anterior, mas deixa explícito).
            if periodo_limpo in ('', '0', '-'):
                # Três formas de indicar que a tarefa é aperiódica: campo vazio, '0' ou '-'.
                avisos.append(
                    f"Tarefa {id_tarefa} é aperiódica (sem período definido). O simulador "
                    "não oferece suporte a tarefas aperiódicas; ela foi ignorada."
                )
                # Registra um aviso, sem interromper a leitura.
                continue
                # Pula para a próxima linha. Essa tarefa não entra na lista e não recebe ID em ids_vistos (observação 3).
            try:
                periodo = int(periodo_limpo)
                # Período: intervalo entre liberações.
                if periodo <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: período inválido ('{periodo_str}').")

            try:
                prazo = int(prazo_str)
                # Prazo relativo: quantos ticks após a liberação a ativação precisa estar pronta.
                if prazo <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: prazo inválido ('{prazo_str}').")

            try:
                eventos = self.parsear_eventos(eventos_str, f"Linha {numero_linha}, tarefa {id_tarefa}")
                # Tenta ler a lista de eventos. Se o campo estiver vazio, devolve [].
            except ValueError as erro_eventos:
                # Caso o formato dos eventos esteja errado, a tarefa não é descartada.
                # Projeto A: lista_eventos só é tratada no Projeto B (req. 3.3.5).
                # Conteúdo fora do formato provisório é ignorado com aviso, para
                # nunca recusar um arquivo que respeita o formato do enunciado.
                avisos.append(f"{erro_eventos} Eventos desta tarefa foram ignorados no Projeto A.")
                # Registra o motivo como aviso.
                eventos = []
                # Zera os eventos e segue com a tarefa.

            tarefas.append(Tarefa(id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos))
            # Cria o objeto Tarefa com os valores validados e adiciona à lista.
            ids_vistos.add(id_tarefa)
            # Marca o ID como usado, para detectar duplicatas nas próximas linhas.

        self._resolver_cores_repetidas(tarefas, avisos)
        # Depois de ler todas as tarefas, verifica cores repetidas e troca as que colidem. Precisa ser feito no fim, porque só então se conhece todas as cores.
        return tarefas
        # Devolve a lista de tarefas aceitas.

    @staticmethod
    # Método estático: não usa 'self'.
    def _cor_livre(usadas):
        """Primeira cor da paleta padrão fora de `usadas`; esgotada a paleta,
        gera cores determinísticas (sempre as mesmas para o mesmo arquivo)."""
        # 'usadas' é um conjunto com as cores que não podem ser repetidas.
        for cor in PALETA_CORES_PADRAO:
            # Percorre a paleta na ordem.
            if cor not in usadas:
                # A primeira cor livre serve.
                return cor
                # Devolve e encerra a função.
        passo = 0
        # Contador usado para gerar cores extras quando a paleta acabar.
        while True:
            # Laço infinito, interrompido só pelo 'return' de dentro. Como 'usadas' é finito, ele sempre encontra uma cor livre.
            passo += 1
            # Avança o contador a cada tentativa.
            cor = f"#{(passo * 0x9E3779) & 0xFFFFFF:06X}"
            # Gera uma cor de forma determinística: multiplica pelo número 0x9E3779 (escolhido para espalhar os valores) e mantém só os 24 bits de cor (& 0xFFFFFF). Formata em hexadecimal com 6 dígitos maiúsculos. Mesmo arquivo, mesmas cores.
            if cor not in usadas:
                # Só usa se ainda não estiver em uso.
                return cor
                # Devolve a cor encontrada.

    def _resolver_cores_repetidas(self, tarefas, avisos):
        """Cada tarefa precisa de uma cor diferente no Gantt (req. 2.1). A
        primeira tarefa com a cor fica com ela; as seguintes recebem uma cor
        livre, que também não colide com nenhuma cor escrita no arquivo."""
        usadas = {t.cor for t in tarefas}
        # Conjunto com TODAS as cores do arquivo. Assim a cor nova não colide nem com cores de tarefas que ainda vão aparecer depois.
        vistas = set()
        # Cores já percorridas na ordem do arquivo. Quando uma cor aparece pela segunda vez, é repetida.
        for t in tarefas:
            # Percorre as tarefas na ordem em que foram lidas.
            if t.cor in vistas:
                # Esta cor já foi usada por uma tarefa anterior, então esta tarefa é a repetida.
                nova = self._cor_livre(usadas)
                # Pede uma cor livre.
                avisos.append(
                    f"Tarefa {t.id}: a cor {t.cor} já pertence a outra tarefa. "
                    f"Para o Gantt ficar legível ela recebeu a cor {nova}.")
                # Registra o aviso informando a troca.
                t.cor = nova
                # Troca a cor da tarefa no próprio objeto.
                usadas.add(nova)
                # Marca a nova cor como usada, para que não seja escolhida de novo.
            vistas.add(t.cor)
            # Registra a cor (original ou nova) como vista.