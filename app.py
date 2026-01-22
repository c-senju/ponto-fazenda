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
from flask import Flask, render_template, request, make_response, session, redirect, url_for, flash, jsonify
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
# json: Biblioteca para manipular dados no formato JSON.
import json

# --- Configuração Inicial do Aplicativo Flask ---
# Cria a instância principal do nosso aplicativo web.
app = Flask(__name__)
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

            if dia_semana == 6: # Se for domingo...
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

# --- Rotas e Funções para Webhook EVO ---

def get_cloud_time():
    """
    Gera e retorna a data e hora atual no formato específico (YYYY-MM-DD HH:MM:SS)
    exigido pelo dispositivo EVO em suas respostas.
    """
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def evo_exact_response():
    """
    Monta e retorna a resposta JSON exata que o dispositivo EVO espera.
    - Sem campos extras.
    - JSON puro.
    - HTTP 200.
    """
    return {
        "ret": "reg",
        "result": 1,
        "cloudtime": get_cloud_time(),
    }

def log_body_fully(tag, body):
    """
    Registra o corpo (body) de uma requisição no console para depuração.
    Tenta decodificar o corpo como texto e o exibe, truncando se for muito longo.
    """
    MAX_LOG_CHARS = 12000
    PREVIEW_CHARS = 800

    try:
        # O corpo da requisição em Flask (request.data) vem como bytes.
        # Tentamos decodificá-lo como UTF-8, que é o padrão mais comum.
        body_str = body.decode('utf-8')
    except Exception as e:
        # Se a decodificação falhar, usamos a representação de string dos bytes.
        body_str = str(body)
        print(f"[EVO] Falha ao decodificar body como UTF-8: {e}")

    print(f"[EVO] {tag} typeof: {type(body)}")
    print(f"[EVO] {tag} length: {len(body_str)}")
    print(f"[EVO] {tag} preview: {body_str[:PREVIEW_CHARS]}")

    if len(body_str) <= MAX_LOG_CHARS:
        print(f"[EVO] {tag} FULL: {body_str}")
    else:
        print(f"[EVO] {tag} FULL (TRUNCATED to {MAX_LOG_CHARS} chars): {body_str[:MAX_LOG_CHARS]}")

@app.route('/api/v1/evo', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def evo_webhook():
    """
    Endpoint para receber webhooks do dispositivo EVO.
    - Em requisições GET, funciona como um health check.
    - Em requisições POST:
      - Se o corpo (body) for um JSON com {"cmd": "reg"}, responde com a hora do servidor.
      - Se o corpo for um JSON com a chave "record", processa os registros de ponto.
      - Em outros casos ou erros, responde de forma a não causar reenvio pelo dispositivo.
    """
    # Healthcheck simples (não interfere no POST)
    if request.method == 'GET':
        return jsonify({"ok": True})

    try:
        # Para qualquer método diferente de GET, a lógica é a mesma.
        print("[EVO] HEADERS", request.headers)
        body_bytes = request.data
        log_body_fully("BODY", body_bytes)

        # Tenta decodificar o corpo da requisição como JSON.
        try:
            body_text = body_bytes.decode('utf-8')
            data = json.loads(body_text)
            print("[EVO] JSON decodificado com sucesso.")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Se o corpo não for um JSON válido, registra o erro e responde
            # com um status genérico para evitar reenvios.
            print(f"[EVO] Erro ao decodificar JSON: {e}")
            return jsonify({"status": "error", "message": "Invalid JSON"}), 200

        # --- Lógica Condicional ---
        # 1. Verifica se o comando é 'reg'
        if data and data.get('cmd') == 'reg':
            # Acessa o dicionário 'devinfo' e depois busca o campo 'time'
            device_info = data.get('devinfo', {})
            tempo_dispositivo = device_info.get('time')
        
            payload = {
                "ret": "reg",
                "result": 1,
                "cloudtime": tempo_dispositivo,
            }

    print(f"[EVO] Comando 'reg' recebido. Cloudtime extraído: {tempo_dispositivo}")
    return jsonify(payload)
        # 2. Verifica se há registros de ponto para processar
        if data and 'record' in data and isinstance(data['record'], list):
            conn = None
            cur = None
            try:
                device_sn = data.get('sn')
                conn = get_db_connection()
                cur = conn.cursor()

                for record in data['record']:
                    sql = """
                        INSERT INTO access_logs (
                            device_sn, enroll_id, user_name, event_time,
                            mode, inout_mode, event_code, image_base64
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    params = (
                        device_sn,
                        record.get('enrollid'),
                        record.get('name'),
                        record.get('time'),
                        record.get('mode'),
                        record.get('inout'),
                        record.get('event'),
                        record.get('image')
                    )
                    cur.execute(sql, params)

                conn.commit()
                print(f"[EVO] {len(data['record'])} registros salvos com sucesso.")
                # Responde com um 'OK' genérico para confirmar o recebimento.
                return jsonify({"status": "ok"}), 200

            except psycopg2.Error as db_err:
                print(f"[EVO] Erro no banco de dados: {db_err}")
                if conn:
                    conn.rollback()
                # Resposta de erro, mas com status 200 para não reenviar.
                return jsonify({"status": "error", "message": "Database error"}), 200
            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()

        # 3. Se não for 'reg' nem contiver 'record', é um caso não esperado.
        # Retorna uma resposta genérica para que o dispositivo não reenvie.
        print("[EVO] Payload JSON não continha 'cmd: reg' ou 'record'. Payload:", data)
        return jsonify({"status": "ok", "message": "No action taken"}), 200

    except Exception as err:
        # Erro geral e inesperado no processamento do webhook.
        print(f"[EVO] Erro inesperado no webhook: {err}")
        # Responde de forma genérica para evitar reenvios.
        return jsonify({"status": "error", "message": "Unexpected server error"}), 200

# --- Rota Principal da Aplicação ---

@app.route('/')
def index():
    """Rota principal que exibe o dashboard com todos os dados."""
    # Verifica se o usuário está logado (verificando a sessão). Se não, redireciona para a página de login.
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    registros_brutos = []
    try:
        # Bloco principal: tenta conectar ao banco de dados e buscar os registros.
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT func_id, horario FROM registros ORDER BY horario DESC")
        registros_brutos = cur.fetchall() # Pega todos os resultados da consulta.
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
        registros_brutos = [
            # Registros do João (ID '1')
            ('1', datetime.combine(segunda_feira_passada, time(7, 5))),   # Segunda
            ('1', datetime.combine(segunda_feira_passada, time(11, 2))),
            ('1', datetime.combine(segunda_feira_passada, time(13, 1))),
            ('1', datetime.combine(segunda_feira_passada, time(17, 8))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 1))), # Terça (com hora extra)
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 5))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(18, 2))), # Saiu mais tarde
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0))), # Sábado
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(11, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(8, 0))), # Domingo (extra 100%)
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(10, 0))),
            # Registros da Maria (ID '2')
            ('2', datetime.combine(segunda_feira_passada, time(7, 3))),   # Segunda (faltou uma batida)
            ('2', datetime.combine(segunda_feira_passada, time(11, 1))),
            ('2', datetime.combine(segunda_feira_passada, time(13, 0))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 6))), # Terça
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 4))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 2))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(17, 9))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0))), # Sábado (esqueceu de bater a saída)
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(13, 0))), # Esta batida será ignorada
        ]

    # --- Processamento dos Dados ---
    # Independentemente de os dados virem do banco ou serem fictícios, eles são processados aqui.

    # Chama a função para encontrar pontos faltantes.
    pontos_faltantes = processar_pontos_faltantes(registros_brutos, funcionarios)
    # Chama a função para calcular as horas trabalhadas.
    resumo_horas = calcular_horas_trabalhadas(registros_brutos, funcionarios)
    # Mapeia os IDs para nomes e ordena os registros por data/hora para exibição na tabela.
    dados_mapeados = sorted(
        [(funcionarios.get(str(r[0]), "Desconhecido"), r[1]) for r in registros_brutos],
        key=lambda x: x[1],
        reverse=True
    )

    # Renderiza o template 'index.html', passando todas as informações processadas para ele.
    return render_template('index.html',
                           pontos=dados_mapeados,
                           pontos_faltantes=pontos_faltantes,
                           resumo_horas=resumo_horas)

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
                cur.execute("INSERT INTO registros (func_id, horario) VALUES (%s, %s)",
                            (func_id, horario))
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
    """
    # Protege a rota, exigindo que o usuário esteja logado.
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        # Usa o pandas para executar a consulta SQL e carregar os resultados diretamente em um DataFrame.
        df = pd.read_sql_query("SELECT func_id, horario FROM registros ORDER BY horario DESC", conn)
        conn.close()

        # Usa o método '.map()' do pandas para trocar os IDs dos funcionários pelos seus nomes.
        df['func_id'] = df['func_id'].map(funcionarios).fillna(df['func_id'])
        # Renomeia as colunas para ficarem mais apresentáveis no Excel.
        df.rename(columns={'func_id': 'Funcionário', 'horario': 'Data e Hora'}, inplace=True)

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

# --- Ponto de Entrada para Execução do Servidor ---
# Este bloco só é executado quando o script é rodado diretamente (ex: `python app.py`).
if __name__ == '__main__':
    # Inicia o servidor de desenvolvimento do Flask.
    app.run()
