import os
from flask import Flask, render_template, request, make_response, session, redirect, url_for, flash
import psycopg2
import pandas as pd
from datetime import datetime
from io import BytesIO

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

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    # --- DADOS FICTÍCIOS PARA VISUALIZAÇÃO ---
    # Este bloco substitui a consulta ao banco de dados para permitir o desenvolvimento do frontend.
    try:
        from datetime import datetime, timedelta

        # Dados fictícios para simulação
        dados_mapeados = [
            ("João", datetime.now() - timedelta(hours=0, minutes=15)),
            ("Maria", datetime.now() - timedelta(hours=0, minutes=5)),
            ("João", datetime.now() - timedelta(hours=4, minutes=30)),
            ("Maria", datetime.now() - timedelta(hours=4, minutes=25)),
            ("João", datetime.now() - timedelta(hours=6, minutes=10)),
            ("Maria", datetime.now() - timedelta(hours=6, minutes=2)),
            ("João", datetime.now() - timedelta(hours=10, minutes=40)),
            ("Maria", datetime.now() - timedelta(hours=10, minutes=35)),
            ("João", datetime.now() - timedelta(days=1, hours=0, minutes=5)),
            ("Maria", datetime.now() - timedelta(days=1, hours=0, minutes=1)),
            ("João", datetime.now() - timedelta(days=1, hours=4, minutes=20)),
            ("Maria", datetime.now() - timedelta(days=1, hours=4, minutes=15)),
        ]

        # Ordena por data, do mais recente para o mais antigo
        dados_mapeados.sort(key=lambda x: x[1], reverse=True)

        return render_template('index.html', pontos=dados_mapeados)
    except Exception as e:
        # Manter um tratamento de erro básico
        return f"Erro ao gerar dados fictícios: {e}"

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
