import os

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


# ================= HOME =================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "mensagem": "API do chatbot funcionando"
    })


# ================= CHAT =================

@app.route("/chat", methods=["POST"])
def chat_api():

    try:

        # Carrega somente quando necessário
        from chatbot import responder_chatbot

        data = request.get_json(silent=True)

        if not data:

            return jsonify({
                "resposta": "JSON inválido.",
                "contexto": "erro_json"
            }), 400

        mensagem = data.get(
            "mensagem",
            ""
        ).strip()

        contexto_anterior = data.get(
            "contexto_anterior"
        )

        if not mensagem:

            return jsonify({
                "resposta": "Digite uma mensagem válida.",
                "contexto": "vazio"
            }), 400

        resposta, novo_contexto = responder_chatbot(
            mensagem=mensagem,
            contexto_anterior=contexto_anterior
        )

        return jsonify({
            "resposta": resposta,
            "contexto": novo_contexto
        })

    except Exception as erro:

        print(f"Erro na API chatbot: {erro}")

        return jsonify({
            "resposta": "Erro interno na API do chatbot.",
            "contexto": "erro_servidor"
        }), 500


# ================= MAIN =================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )