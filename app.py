# --- Importações de Bibliotecas ---
# os: Para interagir com o sistema operacional, como pegar variáveis de ambiente.
import os
# flask: É o framework web que estamos usando. Importamos várias funções dele:
# - Flask: A classe principal para criar a aplicação.
# - render_template: Para carregar e exibir arquivos HTML (templates).
# - request: Para acessar os dados de uma requisição web (ex: formulários).
# - make_response: Para criar uma resposta HTTP customizada (usado no export).
# - session: Para armazenar informações do usuário entre requisições (login).
# - redirect, url_for: Para redirecionar o usuário para outras páginas.
# - flash: Para exibir mensagens temporárias para o usuário.
from flask import Flask, render_template, request, make_response, session, redirect, url_for, flash, jsonify, Response
# flask_sock: Biblioteca para adicionar suporte a WebSocket ao Flask.
from flask_sock import Sock
# psycopg2: O "driver" que permite que o Python se conecte a um banco de dados PostgreSQL.
import psycopg2
# pandas: Uma biblioteca poderosa para manipulação e análise de dados. Usamos para criar o arquivo Excel.
import pandas as pd
# datetime, time, timedelta: Módulos padrão do Python para trabalhar com datas e horas.
from datetime import datetime, time, timedelta
# BytesIO: Permite tratar dados em memória (como um arquivo Excel) como se fosse um arquivo em disco.
from io import BytesIO
# groupby: Uma ferramenta útil para agrupar elementos de uma lista (usada para agrupar registros por funcionário/dia).
from itertools import groupby
# lru_cache: Para cachear resultados de funções (como busca de feriados).
from functools import lru_cache
# json: Biblioteca para manipular dados no formato JSON.
import json
# requests: Para fazer requisições HTTP para as APIs de feriados.
import requests

# --- Configuração Inicial do Aplicativo Flask ---
# Cria a instância principal do nosso aplicativo web.
app = Flask(__name__)
# Inicializa o Flask-Sock para adicionar suporte a WebSockets ao aplicativo.
sock = Sock(app)
# Define uma "chave secreta" que o Flask usa para proteger as sessões dos usuários.
# É importante que seja um valor longo, aleatório и secreto em um ambiente de produção.
app.secret_key = 'sua_senha_super_secreta_aqui' # Troque por uma senha mais forte

# --- Conexão com o Banco de Dados ---
# Pega a URL de conexão do banco de dados a partir das "variáveis de ambiente" do sistema.
# Em ambientes como o Render ou Heroku, esta variável é configurada no painel de controle.
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Cria e retorna uma nova conexão com o banco de dados PostgreSQL."""
    # A opção sslmode='require' é frequentemente necessária para conexões seguras em serviços de nuvem.
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def update_device_communication(sn):
    """
    Atualiza ou insere o horário da última comunicação de um dispositivo no banco de dados.
    Usa a cláusula ON CONFLICT para realizar um UPSERT (update ou insert).
    """
    if not sn:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO dispositivos (sn, last_communication)
            VALUES (%s, %s)
            ON CONFLICT (sn) DO UPDATE
            SET last_communication = EXCLUDED.last_communication
        """, (sn, datetime.now()))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao atualizar status do dispositivo {sn}: {e}")

def init_db():
    """
    Inicializa o banco de dados. Cria a tabela 'registros' se ela ainda não existir.
    Isso garante que a aplicação não quebre na primeira vez que for executada.
    """
    try:
        # Abre uma conexão.
        conn = get_db_connection()
        # Cria um "cursor", que é o objeto usado para executar comandos SQL.
        cur = conn.cursor()
        # Executa o comando SQL para criar a tabela.
        # "IF NOT EXISTS" previne um erro se a tabela já foi criada.
        # "SERIAL PRIMARY KEY" cria um ID numérico que se auto-incrementa.
        cur.execute('''
            CREATE TABLE IF NOT EXISTS registros (
                id SERIAL PRIMARY KEY,
                func_id TEXT NOT NULL,
                horario TIMESTAMP NOT NULL
            )
        ''')
        # Salva as alterações no banco de dados.
        conn.commit()
        # Fecha o cursor e a conexão para liberar os recursos.
        cur.close()
        conn.close()
        print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        # Se ocorrer qualquer erro, ele será impresso no console do servidor.
        print(f"Erro ao inicializar banco: {e}")

# A função init_db() foi removida para garantir que o Alembic seja a única fonte de verdade
# para o esquema do banco de dados.
# init_db()

# --- Dados Estáticos da Aplicação ---
# Dicionário que mapeia o ID do funcionário (como vem do relógio) para o nome.
# Em um sistema real, isso viria de uma tabela de 'funcionarios' no banco de dados.
funcionarios = {
    "1": "João",
    "2": "Maria",
}

# --- Rotas de Autenticação (Login/Logout) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Exibe a página de login e processa a tentativa de login."""
    # Se o usuário enviou o formulário (método POST).
    if request.method == 'POST':
        # Verifica se a senha enviada no formulário é a senha correta.
        # A senha está "hardcoded" (fixa no código) para simplicidade.
        if request.form['password'] == 'admin':
            # Se a senha estiver correta, armazena na "sessão" que o usuário está logado.
            session['logged_in'] = True
            # Cria uma mensagem de sucesso para ser exibida na próxima página.
            flash('Login realizado com sucesso!')
            # Redireciona o usuário para a página principal ('index').
            return redirect(url_for('index'))
        else:
            # Se a senha estiver errada, cria uma mensagem de erro.
            flash('Senha incorreta!')
    # Se o método for GET (usuário apenas acessou a página), exibe o template de login.
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Remove o status de 'logado' da sessão e redireciona para a página de login."""
    # Remove a informação 'logged_in' da sessão do usuário.
    session.pop('logged_in', None)
    # Cria uma mensagem informativa.
    flash('Você foi desconectado.')
    # Redireciona para a tela de login.
    return redirect(url_for('login'))

# --- Funções de Lógica de Negócio ---

@lru_cache(maxsize=10)
def get_feriados(ano, ibge_code="3149800"):
    """
    Busca feriados nacionais, estaduais e municipais.
    Tenta primeiro a API feriados.dev (conforme solicitado).
    Usa BrasilAPI + Feriados Locais Manuais como fallback caso a primeira falhe.
    """
    feriados = {}

    # 1. Tentativa com feriados.dev
    try:
        # Nota: O subdomínio api.feriados.dev é o padrão documentado.
        url = f"https://api.feriados.dev/v1/holidays?year={ano}&ibge_code={ibge_code}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            dados = response.json()
            # Assume que a API retorna uma lista de objetos com 'date' e 'name'.
            for f in dados:
                feriados[f['date']] = f['name']
            print(f"Feriados carregados via feriados.dev para o ano {ano}")
            return feriados
    except Exception as e:
        print(f"Aviso: Erro ao acessar feriados.dev ({e}). Usando fallback.")

    # 2. Fallback: BrasilAPI (Feriados Nacionais)
    try:
        url = f"https://brasilapi.com.br/api/feriados/v1/{ano}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            dados = response.json()
            for f in dados:
                feriados[f['date']] = f['date'] # Chave é a data, valor inicial pode ser o nome
                # Alguns retornos da BrasilAPI usam 'name'
                feriados[f['date']] = f.get('name', 'Feriado Nacional')
    except Exception as e:
        print(f"Erro ao acessar BrasilAPI: {e}")

    # 3. Adição manual de feriados municipais conhecidos de Perdizes - MG
    # 17/12 - Aniversário da Cidade (Lei Estadual 148 de 17/12/1938)
    feriados_locais = [
        (f"{ano}-12-17", "Aniversário de Perdizes"),
    ]

    for data, nome in feriados_locais:
        if data not in feriados:
            feriados[data] = nome

    return feriados

def processar_pontos_faltantes(registros_brutos, funcionarios_map):
    """
    Analisa todos os registros de ponto para encontrar batidas que foram esquecidas.
    A regra é: se um funcionário bateu ponto em um dia, ele deveria ter batido
    nos horários padrão. Esta função verifica se para cada horário padrão, existe
    uma batida real dentro de uma margem de tolerância (90 minutos).

    Args:
        registros_brutos (list): Uma lista de tuplas, onde cada tupla é (id_funcionario, horario).
        funcionarios_map (dict): O dicionário que mapeia ID para nome.

    Returns:
        list: Uma lista de dicionários, cada um representando uma batida faltante.
    """
    # Define os horários de batida esperados para dias de semana e sábados.
    horarios_semana = [time(7, 0), time(11, 0), time(13, 0), time(17, 0)]
    horarios_sabado = [time(7, 0), time(11, 0)]

    # Lista onde armazenaremos as batidas que faltaram.
    batidas_faltantes = []

    # Ordena os registros por funcionário e depois por data/hora para que o 'groupby' funcione corretamente.
    registros_por_id = sorted(registros_brutos, key=lambda x: (x[0], x[1]))
    # Agrupa todos os registros pelo ID do funcionário.
    grupos_por_funcionario = groupby(registros_por_id, key=lambda x: x[0])

    # Itera sobre cada funcionário e seus respectivos registros.
    for func_id, registros_funcionario_raw in grupos_por_funcionario:
        nome_funcionario = funcionarios_map.get(func_id, "Desconhecido")

        # Agora, agrupa os registros deste funcionário por dia.
        registros_por_dia = groupby(registros_funcionario_raw, key=lambda x: x[1].date())

        # Itera sobre cada dia que o funcionário trabalhou.
        for data, registros_dia_raw in registros_por_dia:
            # Converte o grupo de registros para uma lista de horários.
            registros_do_dia = [r[1] for r in registros_dia_raw]

            # Se for um domingo (weekday() == 6), pula para o próximo dia.
            if data.weekday() == 6:
                continue

            # Decide qual lista de horários esperados usar (semana ou sábado).
            horarios_esperados = horarios_sabado if data.weekday() == 5 else horarios_semana

            # Para cada horário que era esperado no dia...
            for esperado in horarios_esperados:
                encontrado = False
                # Cria um objeto datetime completo para o horário esperado.
                horario_esperado_dt = datetime.combine(data, esperado)

                # ...verifica cada batida que realmente aconteceu no dia.
                for batida in registros_do_dia:
                    # Se a diferença entre a batida real e a esperada for de até 90 minutos...
                    if abs(batida - horario_esperado_dt) <= timedelta(minutes=90):
                        # ...consideramos que a batida foi encontrada e podemos parar de procurar.
                        encontrado = True
                        break

                # Se, após verificar todas as batidas do dia, não encontramos uma correspondente...
                if not encontrado:
                    # ...adicionamos um registro à nossa lista de batidas faltantes.
                    batidas_faltantes.append({
                        "funcionario": nome_funcionario,
                        "data": data.strftime('%d/%m/%Y'),
                        "horario_faltante": esperado.strftime('%H:%M')
                    })

    return batidas_faltantes

def calcular_horas_trabalhadas(registros_brutos, funcionarios_map):
    """
    Calcula o total de horas trabalhadas por cada funcionário, separando em
    horas normais, extras com 50% e extras com 100%.

    Regras:
    - Dias de semana: Até 8h são normais, o que passar é extra 50%.
    - Sábados: Até 4h são normais, o que passar é extra 50%.
    - Domingos: Todas as horas são extra 100%.
    - Batidas ímpares: A última batida do dia é ignorada.

    Args:
        registros_brutos (list): Uma lista de tuplas (id_funcionario, horario).
        funcionarios_map (dict): O dicionário que mapeia ID para nome.

    Returns:
        dict: Um dicionário onde as chaves são nomes de funcionários e os valores
              são outros dicionários com as horas formatadas.
    """
    # Cria uma estrutura para armazenar as horas de cada funcionário, iniciando com zero.
    resumo_horas = {nome: {'normal': timedelta(), 'extra50': timedelta(), 'extra100': timedelta()} for nome in funcionarios_map.values()}

    # Busca os feriados para todos os anos presentes nos registros para garantir o cálculo correto.
    anos_presentes = set(r[1].year for r in registros_brutos)
    todos_feriados = {}
    for ano in anos_presentes:
        todos_feriados.update(get_feriados(ano))

    # Agrupa os registros por funcionário, similar à função anterior.
    registros_por_id = sorted(registros_brutos, key=lambda x: (x[0], x[1]))
    grupos_por_funcionario = groupby(registros_por_id, key=lambda x: x[0])

    for func_id, registros_funcionario in grupos_por_funcionario:
        nome_funcionario = funcionarios_map.get(func_id, "Desconhecido")

        # Agrupa os registros do funcionário por dia.
        registros_por_dia = groupby(registros_funcionario, key=lambda x: x[1].date())

        for data, registros_dia_raw in registros_por_dia:
            # Ordena as batidas do dia para garantir que estão em ordem cronológica.
            registros_dia = sorted([r[1] for r in registros_dia_raw])

            # Se o número de batidas for ímpar, a última não tem um par de "saída", então a removemos.
            if len(registros_dia) % 2 != 0:
                registros_dia = registros_dia[:-1]

            # Calcula o total de tempo trabalhado no dia.
            horas_trabalhadas_dia = timedelta()
            # Itera sobre as batidas em pares (entrada, saída).
            for i in range(0, len(registros_dia), 2):
                entrada = registros_dia[i]
                saida = registros_dia[i+1]
                # Soma o intervalo de tempo ao total do dia.
                horas_trabalhadas_dia += saida - entrada

            # Classifica as horas calculadas (normais, extra 50%, extra 100%).
            dia_semana = data.weekday() # Segunda-feira é 0, Domingo é 6.
            data_iso = data.strftime('%Y-%m-%d')

            # Regra: Domingos ou Feriados são 100% extra.
            if dia_semana == 6 or data_iso in todos_feriados:
                resumo_horas[nome_funcionario]['extra100'] += horas_trabalhadas_dia
            else:
                # Define o limite de horas normais para o dia.
                limite_normal = timedelta(hours=8) if dia_semana < 5 else timedelta(hours=4) # < 5 é Seg-Sex

                # Compara o total trabalhado com o limite.
                if horas_trabalhadas_dia > limite_normal:
                    # Adiciona as horas normais até o limite.
                    resumo_horas[nome_funcionario]['normal'] += limite_normal
                    # O que exceder o limite vira hora extra 50%.
                    resumo_horas[nome_funcionario]['extra50'] += horas_trabalhadas_dia - limite_normal
                else:
                    # Se não excedeu o limite, todas as horas são normais.
                    resumo_horas[nome_funcionario]['normal'] += horas_trabalhadas_dia

    # Formata os objetos timedelta para uma string mais legível (ex: "10h 30m").
    resultado_formatado = {}
    for nome, horas in resumo_horas.items():
        resultado_formatado[nome] = {
            'normal': f"{int(horas['normal'].total_seconds() // 3600)}h {int((horas['normal'].total_seconds() % 3600) // 60)}m",
            'extra50': f"{int(horas['extra50'].total_seconds() // 3600)}h {int((horas['extra50'].total_seconds() % 3600) // 60)}m",
            'extra100': f"{int(horas['extra100'].total_seconds() // 3600)}h {int((horas['extra100'].total_seconds() % 3600) // 60)}m",
        }

    return resultado_formatado

# --- Rotas e Funções para Webhook EVO via WebSocket ---
@sock.route('/api/v1/evo')
def evo_webhook(ws):
    """
    Endpoint WebSocket para comunicação com o dispositivo EVO.
    Mantém uma conexão persistente para troca de mensagens como 'reg' e 'sendlog'.
    O parâmetro 'ws' é o objeto da conexão WebSocket fornecido pelo Flask-Sock.
    """
    # Inicia um loop infinito para manter a conexão WebSocket ativa e ouvir as mensagens do dispositivo.
    # Cada iteração do loop processará uma mensagem recebida.
    while True:
        try:
            # Espera por uma mensagem do cliente (dispositivo EVO).
            # A chamada `ws.receive()` é bloqueante, ou seja, o código pausa aqui até uma mensagem chegar.
            message = ws.receive()
            # Converte a mensagem JSON (que é uma string) para um dicionário Python para fácil manipulação.
            data = json.loads(message)
            # Imprime os dados recebidos no console para fins de depuração.
            print(f"Recebido via WebSocket: {data}")

            # Pega o comando e o número de série (SN) da requisição.
            comando = data.get("cmd")
            sn = data.get("sn")

            # Sempre que recebemos uma mensagem válida com SN, atualizamos o status de comunicação.
            if sn:
                update_device_communication(sn)

            # --- LÓGICA PARA O COMANDO 'reg' (REGISTRO/HANDSHAKE) ---
            if comando == "reg":
                print(f"Recebido Handshake do SN: {data.get('sn')}")
                # Prepara a resposta de sucesso para o handshake.
                # Conforme a documentação, a resposta deve conter 'ret', 'result' e 'cloudtime'.
                cloud_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                response_dict = {
                    "ret": "reg",
                    "result": True, # A documentação especifica um booleano `true`.
                    "cloudtime": cloud_time
                }
                # Envia a resposta de volta para o dispositivo no formato de string JSON.
                ws.send(json.dumps(response_dict))
                print(f"Enviado resposta 'reg': {json.dumps(response_dict)}")

            # --- LÓGICA PARA O COMANDO 'sendlog' (ENVIO DE REGISTROS) ---
            elif comando == "sendlog":
                # A documentação indica que os registros vêm na chave 'record'.
                logs = data.get("record", [])
                conn = None
                cur = None
                success = False
                try:
                    conn = get_db_connection()
                    cur = conn.cursor()

                    # Itera sobre cada registro de ponto recebido.
                    for batida in logs:
                        user_id = batida.get("enrollid")
                        horario_str = batida.get("time")
                        horario = datetime.strptime(horario_str, '%Y-%m-%d %H:%M:%S')

                        # Insere o registro no banco de dados.
                        cur.execute("INSERT INTO registros (func_id, horario, origem) VALUES (%s, %s, %s)",
                                    (str(user_id), horario, 'equipamento'))

                        print(f"Ponto registrado! Usuário: {user_id} em {horario_str}")

                    conn.commit()
                    success = True # Marca como sucesso se a transação for concluída.
                except (Exception, psycopg2.Error) as e:
                    print(f"Erro ao processar 'sendlog': {e}")
                    if conn:
                        conn.rollback() # Desfaz a transação em caso de erro.
                finally:
                    if cur:
                        cur.close()
                    if conn:
                        conn.close()

                # Prepara a resposta de confirmação para o 'sendlog'.
                # O dispositivo precisa desta confirmação para limpar os logs da sua memória interna.
                response_dict = {
                    "ret": "sendlog",
                    "result": success
                }
                ws.send(json.dumps(response_dict))
                print(f"Enviado resposta 'sendlog': {json.dumps(response_dict)}")

        except Exception as e:
            # Se ocorrer um erro (ex: o cliente desconecta, JSON inválido), imprime o erro
            # e quebra o loop para fechar a conexão deste lado.
            print(f"Erro na conexão WebSocket: {e}")
            break

# --- Rota Principal da Aplicação ---

@app.route('/')
def index():
    """Rota principal que exibe o dashboard com todos os dados."""
    # Verifica se o usuário está logado (verificando a sessão). Se não, redireciona para a página de login.
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    registros_brutos_completo = []
    last_evo_comm = None
    try:
        # Bloco principal: tenta conectar ao banco de dados e buscar os registros.
        conn = get_db_connection()
        cur = conn.cursor()

        # Busca a última comunicação de qualquer dispositivo EVO.
        cur.execute("SELECT MAX(last_communication) FROM dispositivos")
        row = cur.fetchone()
        if row:
            last_evo_comm = row[0]

        # Busca id, func_id, horario, origem e justificativa.
        cur.execute("SELECT func_id, horario, origem, justificativa, id FROM registros ORDER BY horario DESC")
        registros_brutos_completo = cur.fetchall() # Pega todos os resultados da consulta.
        cur.close()
        conn.close()
    except Exception as e:
        # Bloco de exceção: executado se a conexão com o banco de dados falhar.
        # Isso é útil para poder desenvolver a interface mesmo sem o banco de dados estar acessível.
        print(f"ALERTA: Não foi possível conectar ao banco de dados: {e}")
        print("Usando dados fictícios para visualização.")

        # --- DADOS FICTÍCIOS ESTRUTURADOS (Fallback) ---
        # Cria dados de exemplo para que a página não fique vazia em caso de erro.
        hoje = datetime.now().date()
        segunda_feira_passada = hoje - timedelta(days=hoje.weekday())
        # Formato: (func_id, horario, origem, justificativa, id)
        registros_brutos_completo = [
            # Registros do João (ID '1')
            ('1', datetime.combine(segunda_feira_passada, time(7, 5)), 'equipamento', None, 101),   # Segunda
            ('1', datetime.combine(segunda_feira_passada, time(11, 2)), 'equipamento', None, 102),
            ('1', datetime.combine(segunda_feira_passada, time(13, 1)), 'equipamento', None, 103),
            ('1', datetime.combine(segunda_feira_passada, time(17, 8)), 'equipamento', None, 104),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 1)), 'equipamento', None, 105), # Terça (com hora extra)
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 0)), 'equipamento', None, 106),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 5)), 'equipamento', None, 107),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(18, 2)), 'manual', 'Serviço extra no galpão', 108), # Saiu mais tarde
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0)), 'equipamento', None, 109), # Sábado
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(11, 0)), 'equipamento', None, 110),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(8, 0)), 'equipamento', None, 111), # Domingo (extra 100%)
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(10, 0)), 'equipamento', None, 112),
            # Registros da Maria (ID '2')
            ('2', datetime.combine(segunda_feira_passada, time(7, 3)), 'equipamento', None, 201),   # Segunda (faltou uma batida)
            ('2', datetime.combine(segunda_feira_passada, time(11, 1)), 'equipamento', None, 202),
            ('2', datetime.combine(segunda_feira_passada, time(13, 0)), 'equipamento', None, 203),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 6)), 'equipamento', None, 204), # Terça
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 4)), 'equipamento', None, 205),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 2)), 'equipamento', None, 206),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(17, 9)), 'equipamento', None, 207),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0)), 'equipamento', None, 208), # Sábado (esqueceu de bater a saída)
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(13, 0)), 'equipamento', None, 209), # Esta batida será ignorada
        ]

    # --- Processamento dos Dados ---
    # Independentemente de os dados virem do banco ou serem fictícios, eles são processados aqui.

    # Extrai apenas (func_id, horario) para as funções de processamento legadas.
    registros_para_processar = [(r[0], r[1]) for r in registros_brutos_completo]

    # Chama a função para encontrar pontos faltantes.
    pontos_faltantes = processar_pontos_faltantes(registros_para_processar, funcionarios)
    # Chama a função para calcular as horas trabalhadas.
    resumo_horas = calcular_horas_trabalhadas(registros_para_processar, funcionarios)

    # Mapeia os dados para um formato de dicionário mais fácil de usar no template.
    dados_mapeados = sorted(
        [{
            'id': r[4],
            'nome': funcionarios.get(str(r[0]), "Desconhecido"),
            'func_id': r[0],
            'horario': r[1],
            'origem': r[2],
            'justificativa': r[3]
        } for r in registros_brutos_completo],
        key=lambda x: x['horario'],
        reverse=True
    )

    # Busca os feriados do ano atual para exibir no calendário.
    ano_atual = datetime.now().year
    feriados = get_feriados(ano_atual)

    # Renderiza o template 'index.html', passando todas as informações processadas para ele.
    return render_template('index.html',
                           pontos=dados_mapeados,
                           pontos_faltantes=pontos_faltantes,
                           resumo_horas=resumo_horas,
                           funcionarios=funcionarios,
                           feriados=feriados,
                           last_evo_comm=last_evo_comm,
                           now=datetime.now())

# --- Rota para Recebimento de Dados do Relógio ---

@app.route('/iclock/cdata', methods=['POST', 'GET'])
def receber_ponto():
    """
    Esta é a rota que o relógio de ponto (ZKTeco) acessa para enviar os dados.
    Ela recebe os dados, processa e insere no banco de dados.
    """
    # O equipamento envia os dados no corpo da requisição em formato de texto.
    raw_data = request.get_data(as_text=True)
    # Imprime os dados recebidos no console do servidor. Útil para depuração.
    print(f"Dados recebidos do relógio: {raw_data}")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Os dados podem vir com múltiplas linhas, cada uma sendo um registro.
        # Elas são separadas por '\r\n'.
        lines = raw_data.strip().split('\r\n')
        for line in lines:
            # Cada linha tem colunas separadas por uma tabulação ('\t').
            parts = line.split('\t')
            # Garante que a linha tem pelo menos as duas colunas que precisamos.
            if len(parts) >= 2:
                # A primeira coluna é a data/hora, a segunda é o ID do funcionário.
                horario_str = parts[0]
                func_id = parts[1]

                # Converte a string de data/hora para um objeto datetime do Python.
                horario = datetime.strptime(horario_str, '%Y-%m-%d %H:%M:%S')

                # Executa o comando SQL para inserir o novo registro na tabela.
                # Usar '%s' ajuda a prevenir ataques de "SQL Injection".
                cur.execute("INSERT INTO registros (func_id, horario, origem) VALUES (%s, %s, %s)",
                            (func_id, horario, 'equipamento'))
        # Salva todas as inserções feitas no loop.
        conn.commit()
        cur.close()
        conn.close()
        # O relógio espera uma resposta "OK" para saber que os dados foram recebidos.
        return "OK"
    except Exception as e:
        # Se algo der errado, imprime o erro no log do servidor e retorna uma mensagem de erro.
        print(f"Erro ao salvar ponto: {e}")
        return f"Erro ao salvar ponto: {e}"

# --- Rota para Exportação de Dados ---

@app.route('/export')
def export_excel():
    """
    Busca todos os registros do banco de dados e os exporta como um arquivo Excel.
    Inclui as novas colunas de origem e justificativa.
    """
    # Protege a rota, exigindo que o usuário esteja logado.
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        # Usa o pandas para executar a consulta SQL e carregar os resultados diretamente em um DataFrame.
        df = pd.read_sql_query("SELECT func_id, horario, origem, justificativa FROM registros ORDER BY horario DESC", conn)
        conn.close()

        # Usa o método '.map()' do pandas para trocar os IDs dos funcionários pelos seus nomes.
        df['func_id'] = df['func_id'].map(funcionarios).fillna(df['func_id'])
        # Renomeia as colunas para ficarem mais apresentáveis no Excel.
        df.rename(columns={
            'func_id': 'Funcionário',
            'horario': 'Data e Hora',
            'origem': 'Origem',
            'justificativa': 'Justificativa'
        }, inplace=True)

        # --- Criação do Arquivo Excel em Memória ---
        # Cria um buffer de bytes em memória para salvar o arquivo Excel.
        output = BytesIO()
        # Usa o ExcelWriter do pandas para escrever o DataFrame no buffer.
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Registros')

        # Move o "cursor" do buffer de volta para o início.
        output.seek(0)

        # --- Preparação da Resposta HTTP para Download ---
        # Cria uma resposta HTTP com o conteúdo do buffer.
        response = make_response(output.getvalue())
        # Define os cabeçalhos HTTP para que o navegador entenda que é um arquivo para download.
        response.headers["Content-Disposition"] = "attachment; filename=registros_ponto.xlsx"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return response

    except Exception as e:
        return f"Erro ao exportar dados: {e}"

# --- Novas Rotas para Ponto Manual e Justificativas ---

@app.route('/add_manual_point', methods=['POST'])
def add_manual_point():
    """
    Processa o formulário de inserção manual de ponto.
    """
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    func_id = request.form.get('func_id')
    data = request.form.get('data')
    hora = request.form.get('hora')
    justificativa = request.form.get('justificativa')

    try:
        # Combina data e hora e converte para datetime.
        horario = datetime.strptime(f"{data} {hora}", '%Y-%m-%d %H:%M')

        conn = get_db_connection()
        cur = conn.cursor()
        # Insere o registro marcando como origem 'manual'.
        cur.execute("INSERT INTO registros (func_id, horario, origem, justificativa) VALUES (%s, %s, %s, %s)",
                    (func_id, horario, 'manual', justificativa))
        conn.commit()
        cur.close()
        conn.close()
        flash('Ponto manual adicionado com sucesso!')
    except Exception as e:
        flash(f'Erro ao adicionar ponto manual: {e}')

    return redirect(url_for('index'))

@app.route('/update_justification', methods=['POST'])
def update_justification():
    """
    Atualiza a justificativa de um registro de ponto existente.
    Usado via AJAX (fetch) a partir do dashboard.
    """
    if not session.get('logged_in'):
        return jsonify({'success': False, 'message': 'Não logado'}), 401

    # Em uma requisição AJAX, os dados podem vir no formulário ou como JSON.
    # Aqui vamos usar request.form para simplicidade com o formulário padrão.
    ponto_id = request.form.get('ponto_id')
    justificativa = request.form.get('justificativa')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE registros SET justificativa = %s WHERE id = %s", (justificativa, ponto_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Erro ao atualizar justificativa: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# --- Ponto de Entrada para Execução do Servidor ---
# Este bloco só é executado quando o script é rodado diretamente (ex: `python app.py`).
if __name__ == '__main__':
    # Inicia o servidor de desenvolvimento do Flask.
    app.run()
