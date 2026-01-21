import os
from flask import Flask, render_template, request
import psycopg2
from datetime import datetime

app = Flask(__name__)

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

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # No Postgres, não usamos a função datetime(), apenas o nome da coluna
        cur.execute("SELECT func_id, horario FROM registros ORDER BY horario DESC LIMIT 50")
        dados = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('index.html', pontos=dados)
    except Exception as e:
        return f"Erro ao carregar os dados: {e}"

@app.route('/iclock/cdata', methods=['POST', 'GET'])
def receber_ponto():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Registra uma batida de teste
        cur.execute("INSERT INTO registros (func_id, horario) VALUES (%s, %s)", 
                    ("Funcionario_Fazenda", datetime.now()))
        conn.commit()
        cur.close()
        conn.close()
        return "OK"
    except Exception as e:
        return f"Erro ao salvar ponto: {e}"

if __name__ == '__main__':
    app.run()
