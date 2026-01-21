from flask import Flask, render_template, request
import sqlite3
from datetime import datetime

app = Flask(__name__)

# Cria o banquinho de dados se ele não existir
def init_db():
    conn = sqlite3.connect('ponto.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS registros (id INTEGER PRIMARY KEY AUTOINCREMENT, func_id TEXT, horario DATETIME)')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    conn = sqlite3.connect('ponto.db')
    cursor = conn.cursor()
    cursor.execute("SELECT func_id, datetime(horario) FROM registros ORDER BY horario DESC")
    dados = cursor.fetchall()
    conn.close()
    return render_template('index.html', pontos=dados)

@app.route('/iclock/cdata', methods=['POST', 'GET'])
def receber_ponto():
    # Quando o aparelho "bater o ponto", ele avisa aqui
    conn = sqlite3.connect('ponto.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO registros (func_id, horario) VALUES (?, ?)", ("Funcionario", datetime.now()))
    conn.commit()
    conn.close()
    return "OK"

if __name__ == '__main__':
    init_db()
    app.run()
