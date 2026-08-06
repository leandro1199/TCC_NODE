import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

# Em produção, informe as origens permitidas em CORS_ORIGINS,
# separadas por vírgula. Ex.: https://meusite.com.br
origins_env = os.getenv("CORS_ORIGINS", "*")
allowed_origins = [item.strip() for item in origins_env.split(",") if item.strip()]
CORS(app, resources={r"/chat": {"origins": allowed_origins}})


@app.get("/")
def home():
    return jsonify({
        "status": "online",
        "mensagem": "API do chatbot funcionando",
    })


@app.post("/chat")
def chat_api():
    try:
        from chatbot import responder_chatbot

        if not request.is_json:
            return jsonify({
                "resposta": "Envie os dados no formato JSON.",
                "contexto": "erro_json",
            }), 415

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({
                "resposta": "JSON inválido.",
                "contexto": "erro_json",
            }), 400

        mensagem = data.get("mensagem", "")
        contexto_anterior = data.get("contexto_anterior")

        if not isinstance(mensagem, str):
            return jsonify({
                "resposta": "O campo 'mensagem' deve ser um texto.",
                "contexto": "erro_validacao",
            }), 400

        if contexto_anterior is not None and not isinstance(contexto_anterior, str):
            return jsonify({
                "resposta": "O campo 'contexto_anterior' deve ser um texto.",
                "contexto": "erro_validacao",
            }), 400

        mensagem = mensagem.strip()
        if not mensagem:
            return jsonify({
                "resposta": "Digite uma mensagem válida.",
                "contexto": "vazio",
            }), 400

        resposta, novo_contexto = responder_chatbot(
            mensagem=mensagem,
            contexto_anterior=contexto_anterior,
        )

        return jsonify({
            "resposta": resposta,
            "contexto": novo_contexto,
        })

    except Exception:
        logger.exception("Erro não tratado na API do chatbot")
        return jsonify({
            "resposta": "Erro interno na API do chatbot.",
            "contexto": "erro_servidor",
        }), 500


@app.errorhandler(413)
def payload_too_large(_error):
    return jsonify({
        "resposta": "A requisição é muito grande.",
        "contexto": "erro_tamanho",
    }), 413


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
