import os
from flask import Flask, render_template, request
import psycopg2
from datetime import datetime

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    # O Render exige sslmode='require' para conexões externas
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# Criar a tabela assim que o servidor ligar
with app.app_context():
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

@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT func_id, horario FROM registros ORDER BY horario DESC LIMIT 50")
        dados = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('index.html', pontos=dados)
    except Exception as e:
        return f"Erro ao acessar o banco: {e}"

@app.route('/iclock/cdata', methods=['POST', 'GET'])
def receber_ponto():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO registros (func_id, horario) VALUES (%s, %s)", 
                    ("Funcionario_Fazenda", datetime.now()))
        conn.commit()
        cur.close()
        conn.close()
        return "OK"
    except Exception as e:
        return f"Erro ao salvar: {e}"

# Removemos o if __name__ == '__main__': daqui para o Render não se confundir
