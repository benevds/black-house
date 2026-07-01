from datetime import datetime

from flask import Flask, request, render_template, jsonify
import traceback
from twilio.twiml.messaging_response import MessagingResponse

import database as db
from database import init_db
from agent import processar_mensagem
from config import NOME_ARENA, QUADRAS, HORARIOS, PRECO_HORA

app = Flask(__name__)
init_db()

@app.route("/", methods=["GET"])
def home():
    return "Servidor da Arena Marina rodando! 🏐 Webhook em /webhook"

@app.route("/webhook", methods=["POST"])
def webhook():
    # ... (mantenha seu código webhook original aqui) ...
    mensagem = request.values.get("Body", "").strip()
    telefone = request.values.get("From", "") 

    resp = MessagingResponse()
    try:
        texto_resposta = processar_mensagem(telefone, mensagem)
    except Exception as e:
        print(f"[ERRO] Falha ao processar mensagem de {telefone}: {e}")
        texto_resposta = "Ops, tivemos um probleminha técnico aqui."

    resp.message(texto_resposta)
    return str(resp)

# ==========================================
# NOVAS ROTAS PARA O FRONT-END WEB
# ==========================================

@app.route("/chat", methods=["GET"])
def pagina_chat():
    """Renderiza a interface visual do chat."""
    return render_template("index.html")

@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        # Pega a mensagem enviada pelo frontend
        dados = request.json
        mensagem = dados.get('mensagem')
        
        # Chama o seu agente (a mesma função usada no WhatsApp)
        # Como estamos na web, passei "web-usuario" no lugar do número de telefone
        texto_resposta = processar_mensagem("web-usuario", mensagem)

        # Devolve a resposta correta para o frontend
        return jsonify({"resposta": texto_resposta})

    except Exception as e:
        print(f"[ERRO WEB] Connection error: {e}")
        print(traceback.format_exc())
        return jsonify({"resposta": "Desculpe, estou com problemas de conexão no momento."}), 503

# ==========================================
# PAINEL ADMINISTRATIVO — ARENA BLACK HOUSE
#
# Interface web para a recepção gerenciar os agendamentos das quadras
# em tempo real, lendo e escrevendo no mesmo banco SQLite usado pelo
# agente de WhatsApp. Note que o template usa o nome "dashboard.html"
# (e não "index.html") de propósito: a rota /chat acima já renderiza
# um "index.html" para o widget de chat web, então reaproveitar o
# mesmo nome aqui sobrescreveria aquele arquivo.
# ==========================================

@app.route("/dashboard", methods=["GET"])
def painel_administrativo():
    """Renderiza o painel administrativo (Arena Black House) da recepção."""
    return render_template("dashboard.html")


@app.route("/api/config", methods=["GET"])
def api_config():
    """
    Expõe as regras de negócio fixas (config.py) para o front-end do
    painel, evitando duplicar esses valores em JavaScript — a mesma
    fonte única de verdade usada pelo agente de IA no prompt de sistema.
    """
    return jsonify({
        "nome_arena": NOME_ARENA,
        "quadras": QUADRAS,
        "horarios": HORARIOS,
        "preco_hora": PRECO_HORA,
    })


@app.route("/api/agendamentos", methods=["GET"])
def api_listar_agendamentos():
    """Lista os agendamentos confirmados de uma data (padrão: hoje)."""
    data = request.args.get("data") or datetime.now().strftime("%Y-%m-%d")
    agendamentos = db.listar_agendamentos_por_data(data)
    return jsonify({"data": data, "agendamentos": agendamentos})


@app.route("/api/agendamentos", methods=["POST"])
def api_criar_agendamento():
    """
    Cria um agendamento manual feito pela recepção. Reaproveita a mesma
    função determinística (database.criar_agendamento) usada pelo agente
    de WhatsApp, incluindo a validação de quadra/horário e a proteção
    contra overbooking via índice único do banco — é o mesmo "funil"
    de escrita para os dois canais, então uma reserva feita pelo bot e
    outra feita na recepção no mesmo segundo não conseguem colidir.
    """
    dados = request.get_json(silent=True) or {}

    try:
        quadra = int(dados.get("quadra"))
    except (TypeError, ValueError):
        return jsonify({"sucesso": False, "erro": "Quadra inválida."}), 400

    resultado = db.criar_agendamento(
        quadra=quadra,
        data=dados.get("data", ""),
        horario=dados.get("horario", ""),
        cliente_nome=dados.get("cliente_nome", ""),
        cliente_telefone=dados.get("cliente_telefone", "recepcao-presencial"),
    )
    status_code = 200 if resultado.get("sucesso") else 409
    return jsonify(resultado), status_code


@app.route("/api/agendamentos/<int:id_agendamento>", methods=["DELETE"])
def api_cancelar_agendamento(id_agendamento):
    """Cancela um agendamento pelo ID (ação exclusiva do painel administrativo)."""
    resultado = db.cancelar_agendamento_admin(id_agendamento)
    status_code = 200 if resultado.get("sucesso") else 404
    return jsonify(resultado), status_code


@app.route("/api/disponibilidade", methods=["GET"])
def api_disponibilidade():
    """
    Consulta disponibilidade real (mesma função usada pelo agente de IA)
    para alimentar o seletor de quadras do formulário de novo agendamento.
    """
    data = request.args.get("data") or datetime.now().strftime("%Y-%m-%d")
    horario = request.args.get("horario", "")
    resultado = db.consultar_disponibilidade(data=data, horario=horario)
    return jsonify(resultado)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)