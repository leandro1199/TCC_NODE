from flask import Flask, request, jsonify
from flask_cors import CORS
from chatbot import responder_chatbot

app = Flask(__name__)
CORS(app)

@app.route("/chat", methods=["POST"])
def chat_api():
    data = request.get_json()

    mensagem = data.get("mensagem", "")
    contexto_anterior = data.get("contexto_anterior")

    resposta, novo_contexto = responder_chatbot(
        mensagem=mensagem,
        contexto_anterior=contexto_anterior
    )

    return jsonify({
        "resposta": resposta,
        "contexto": novo_contexto
    })

if __name__ == "__main__":
    app.run(port=5001, debug=True)