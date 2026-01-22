import os
from flask import Flask, render_template, request, make_response, session, redirect, url_for, flash
import psycopg2
import pandas as pd
from datetime import datetime, time, timedelta
from io import BytesIO
from itertools import groupby

app = Flask(__name__)
app.secret_key = 'sua_senha_super_secreta_aqui' # Troque por uma senha mais forte

# Pega a URL que você configurou no Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    # Conecta ao PostgreSQL usando a URL da variável de ambiente
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# Esta função cria a tabela no Postgres se ela não existir
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS registros (
                id SERIAL PRIMARY KEY,
                func_id TEXT NOT NULL,
                horario TIMESTAMP NOT NULL
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
        print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar banco: {e}")

# Chamamos a inicialização assim que o script carrega
init_db()

# Dicionário para mapear IDs de funcionários para nomes
funcionarios = {
    "1": "João",
    "2": "Maria",
}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Senha hardcoded para simplicidade
        if request.form['password'] == 'admin':
            session['logged_in'] = True
            flash('Login realizado com sucesso!')
            return redirect(url_for('index'))
        else:
            flash('Senha incorreta!')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Você foi desconectado.')
    return redirect(url_for('login'))

def processar_pontos_faltantes(registros_brutos, funcionarios_map):
    """
    Processa os registros de ponto para identificar batidas faltantes.
    Uma batida é considerada faltante se não houver nenhum registro dentro de uma
    janela de 90 minutos (antes ou depois) do horário esperado para um dia
    em que o funcionário registrou pelo menos um ponto.
    """
    # Horários de batida esperados
    horarios_semana = [time(7, 0), time(11, 0), time(13, 0), time(17, 0)]
    horarios_sabado = [time(7, 0), time(11, 0)]

    batidas_faltantes = []

    # Agrupa os registros por funcionário para facilitar o processamento
    registros_por_id = sorted(registros_brutos, key=lambda x: (x[0], x[1]))
    grupos_por_funcionario = groupby(registros_por_id, key=lambda x: x[0])

    for func_id, registros_funcionario_raw in grupos_por_funcionario:
        nome_funcionario = funcionarios_map.get(func_id, "Desconhecido")

        # Agrupa os registros deste funcionário por dia
        registros_por_dia = groupby(registros_funcionario_raw, key=lambda x: x[1].date())

        for data, registros_dia_raw in registros_por_dia:
            registros_do_dia = [r[1] for r in registros_dia_raw]

            # Pula domingos
            if data.weekday() == 6:
                continue

            horarios_esperados = horarios_sabado if data.weekday() == 5 else horarios_semana

            # Verifica cada batida esperada para ESTE dia
            for esperado in horarios_esperados:
                encontrado = False
                horario_esperado_dt = datetime.combine(data, esperado)

                for batida in registros_do_dia:
                    # Define uma janela de 90 minutos para cada lado
                    if abs(batida - horario_esperado_dt) <= timedelta(minutes=90):
                        encontrado = True
                        break

                if not encontrado:
                    # Adiciona à lista se nenhuma batida correspondente foi encontrada
                    batidas_faltantes.append({
                        "funcionario": nome_funcionario,
                        "data": data.strftime('%d/%m/%Y'),
                        "horario_faltante": esperado.strftime('%H:%M')
                    })

    return batidas_faltantes

def calcular_horas_trabalhadas(registros_brutos, funcionarios_map):
    """
    Calcula as horas normais, extras 50% e extras 100% para cada funcionário.
    """
    resumo_horas = {nome: {'normal': timedelta(), 'extra50': timedelta(), 'extra100': timedelta()} for nome in funcionarios_map.values()}

    # Agrupa registros por funcionário e depois por dia
    registros_por_id = sorted(registros_brutos, key=lambda x: (x[0], x[1]))
    grupos_por_funcionario = groupby(registros_por_id, key=lambda x: x[0])

    for func_id, registros_funcionario in grupos_por_funcionario:
        nome_funcionario = funcionarios_map.get(func_id, "Desconhecido")

        registros_por_dia = groupby(registros_funcionario, key=lambda x: x[1].date())

        for data, registros_dia_raw in registros_por_dia:
            registros_dia = sorted([r[1] for r in registros_dia_raw])

            # Ignora o último ponto se o número de batidas for ímpar, pois não forma um par
            if len(registros_dia) % 2 != 0:
                registros_dia = registros_dia[:-1]

            horas_trabalhadas_dia = timedelta()
            for i in range(0, len(registros_dia), 2):
                entrada = registros_dia[i]
                saida = registros_dia[i+1]
                horas_trabalhadas_dia += saida - entrada

            # Lógica para horas extras
            dia_semana = data.weekday() # Segunda = 0, Domingo = 6

            if dia_semana == 6: # Domingo
                resumo_horas[nome_funcionario]['extra100'] += horas_trabalhadas_dia
            else:
                limite_normal = timedelta(hours=8) if dia_semana < 5 else timedelta(hours=4)

                if horas_trabalhadas_dia > limite_normal:
                    resumo_horas[nome_funcionario]['normal'] += limite_normal
                    resumo_horas[nome_funcionario]['extra50'] += horas_trabalhadas_dia - limite_normal
                else:
                    resumo_horas[nome_funcionario]['normal'] += horas_trabalhadas_dia

    # Formata o resultado para um formato mais legível (ex: "10h 30m")
    resultado_formatado = {}
    for nome, horas in resumo_horas.items():
        resultado_formatado[nome] = {
            'normal': f"{int(horas['normal'].total_seconds() // 3600)}h {int((horas['normal'].total_seconds() % 3600) // 60)}m",
            'extra50': f"{int(horas['extra50'].total_seconds() // 3600)}h {int((horas['extra50'].total_seconds() % 3600) // 60)}m",
            'extra100': f"{int(horas['extra100'].total_seconds() // 3600)}h {int((horas['extra100'].total_seconds() % 3600) // 60)}m",
        }

    return resultado_formatado

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    registros_brutos = []
    try:
        # Tenta conectar ao banco de dados e buscar os registros
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT func_id, horario FROM registros ORDER BY horario DESC")
        registros_brutos = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"ALERTA: Não foi possível conectar ao banco de dados: {e}")
        print("Usando dados fictícios para visualização.")

        # --- DADOS FICTÍCIOS ESTRUTURADOS (Fallback) ---
        hoje = datetime.now().date()
        segunda_feira_passada = hoje - timedelta(days=hoje.weekday())
        registros_brutos = [
            ('1', datetime.combine(segunda_feira_passada, time(7, 5))),
            ('1', datetime.combine(segunda_feira_passada, time(11, 2))),
            ('1', datetime.combine(segunda_feira_passada, time(13, 1))),
            ('1', datetime.combine(segunda_feira_passada, time(17, 8))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 1))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 5))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=1), time(18, 2))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=5), time(11, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(8, 0))),
            ('1', datetime.combine(segunda_feira_passada + timedelta(days=6), time(10, 0))),
            ('2', datetime.combine(segunda_feira_passada, time(7, 3))),
            ('2', datetime.combine(segunda_feira_passada, time(11, 1))),
            ('2', datetime.combine(segunda_feira_passada, time(13, 0))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(7, 6))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(11, 4))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(13, 2))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=1), time(17, 9))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(7, 0))),
            ('2', datetime.combine(segunda_feira_passada + timedelta(days=5), time(13, 0))),
        ]

    # Processa os dados (sejam eles do banco ou fictícios)
    pontos_faltantes = processar_pontos_faltantes(registros_brutos, funcionarios)
    resumo_horas = calcular_horas_trabalhadas(registros_brutos, funcionarios)
    dados_mapeados = sorted(
        [(funcionarios.get(str(r[0]), "Desconhecido"), r[1]) for r in registros_brutos],
        key=lambda x: x[1],
        reverse=True
    )

    return render_template('index.html',
                           pontos=dados_mapeados,
                           pontos_faltantes=pontos_faltantes,
                           resumo_horas=resumo_horas)

@app.route('/iclock/cdata', methods=['POST', 'GET'])
def receber_ponto():
    # O ZKTeco envia os dados no corpo da requisição, não como formulário
    raw_data = request.get_data(as_text=True)
    print(f"Dados recebidos do relógio: {raw_data}") # Log para depuração

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Os dados podem ter várias linhas, separadas por \r\n
        lines = raw_data.strip().split('\r\n')
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 2:
                # O formato é: YYYY-MM-DD HH:MM:SS\tID_do_Funcionario\t...
                horario_str = parts[0]
                func_id = parts[1]

                # Converte a string para um objeto datetime
                horario = datetime.strptime(horario_str, '%Y-%m-%d %H:%M:%S')

                cur.execute("INSERT INTO registros (func_id, horario) VALUES (%s, %s)",
                            (func_id, horario))
        conn.commit()
        cur.close()
        conn.close()
        return "OK"
    except Exception as e:
        print(f"Erro ao salvar ponto: {e}") # Log do erro no servidor
        return f"Erro ao salvar ponto: {e}"

@app.route('/export')
def export_excel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        # Seleciona todos os registros, sem limite
        df = pd.read_sql_query("SELECT func_id, horario FROM registros ORDER BY horario DESC", conn)
        conn.close()

        # Mapeia os IDs para nomes no DataFrame
        df['func_id'] = df['func_id'].map(funcionarios).fillna(df['func_id'])
        df.rename(columns={'func_id': 'Funcionário', 'horario': 'Data e Hora'}, inplace=True)

        # Cria um arquivo Excel em memória
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Registros')

        output.seek(0)

        # Prepara a resposta para download
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=registros_ponto.xlsx"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return response

    except Exception as e:
        return f"Erro ao exportar dados: {e}"

if __name__ == '__main__':
    app.run()
