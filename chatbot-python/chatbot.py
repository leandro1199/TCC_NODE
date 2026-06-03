import os
import json
import logging
import pickle
import random
import re
import unicodedata

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer
from tensorflow import keras


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent

CONFIG = {
    "ERROR_THRESHOLD": float(os.getenv("ERROR_THRESHOLD", 0.35)),
    "HIGH_CONFIDENCE_THRESHOLD": float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", 0.70)),
    "MODEL_PATH": BASE_DIR / "model_chatbot.keras",
    "CLASSES_PATH": BASE_DIR / "classes.pkl",
    "INTENTS_PATH": BASE_DIR.parent / "json" / "intents.json"
}


class ChatBot:

    def __init__(self):
        self.model = None
        self.intents = None
        self.classes = None
        self.embedding_model = None

        self.allowed_intents = {
            "saudacao",
            "despedida",
            "agradecimento",
            "capacidades",
            "medicamento_esquecido",
            "medicamento_horario",
            "efeito_colateral_remedio",
            "explicacao_hipertensao",
            "explicacao_diabetes",
            "explicacao_artrose",
            "explicacao_osteoporose",
            "dor_articulacao",
            "dor_coluna_costas",
            "dor_cabeca",
            "tontura_mal_estar",
            "pressao_alta_baixa",
            "glicose_diabetes_controle",
            "exercicio_dor_joelho",
            "exercicio_dor_coluna",
            "exercicio_equilibrio",
            "prevencao_quedas",
            "memoria_esquecimento",
            "sono_insonia",
            "hidratacao",
            "alimentacao_idoso",
            "ansiedade_emocional",
            "solidao",
            "luto_tristeza",
            "emergencia_sinais_graves",
            "fora_do_escopo"
        }

        self._load_files()

    def _load_files(self):
        if not CONFIG["MODEL_PATH"].exists():
            raise FileNotFoundError(f"Modelo não encontrado em: {CONFIG['MODEL_PATH']}")

        if not CONFIG["INTENTS_PATH"].exists():
            raise FileNotFoundError(f"Arquivo intents não encontrado: {CONFIG['INTENTS_PATH']}")

        if not CONFIG["CLASSES_PATH"].exists():
            raise FileNotFoundError(f"Arquivo classes não encontrado: {CONFIG['CLASSES_PATH']}")

        logger.info(f"Carregando modelo: {CONFIG['MODEL_PATH']}")

        self.model = keras.models.load_model(
            str(CONFIG["MODEL_PATH"]),
            compile=False,
            safe_mode=False
        )

        with open(CONFIG["INTENTS_PATH"], "r", encoding="utf-8") as f:
            self.intents = json.load(f)

        with open(CONFIG["CLASSES_PATH"], "rb") as f:
            loaded = pickle.load(f)

        if isinstance(loaded, dict):
            self.classes = loaded.get("classes", [])
            embedding_model_name = loaded.get(
                "embedding_model_name",
                "all-MiniLM-L6-v2"
            )
        else:
            self.classes = loaded
            embedding_model_name = "all-MiniLM-L6-v2"

        if not self.classes:
            raise ValueError("Nenhuma classe foi carregada do arquivo classes.pkl.")

        logger.info(f"Carregando SentenceTransformer: {embedding_model_name}")

        self.embedding_model = SentenceTransformer(embedding_model_name)

        logger.info("Chatbot carregado com sucesso.")

    def normalize_text(self, text: str) -> str:
        text = str(text).lower().strip()

        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("utf-8")

        text = re.sub(r"[^\w\s?/-]", "", text)
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def predict_class(self, sentence: str) -> List[dict]:
        sentence = self.normalize_text(sentence)

        if not sentence:
            return []

        vec = self.embedding_model.encode(
            [sentence],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype(np.float32)

        res = self.model.predict(vec, verbose=0)[0]

        error_threshold = CONFIG["ERROR_THRESHOLD"]

        results = [
            [i, r]
            for i, r in enumerate(res)
            if r > error_threshold
        ]

        results.sort(
            key=lambda x: x[1],
            reverse=True
        )

        return_list = []

        for r in results:
            return_list.append({
                "intent": self.classes[r[0]],
                "probability": str(float(r[1]))
            })

        return return_list

    def get_response(self, intents_list: List[dict]) -> Tuple[str, str]:
        if not intents_list:
            return (
                "Desculpe, não consegui entender sua pergunta.",
                "fora_do_escopo"
            )

        tag = intents_list[0]["intent"]

        if tag not in self.allowed_intents:
            return (
                "Desculpe, não consigo responder isso.",
                "fora_do_escopo"
            )

        list_of_intents = self.intents.get("intents", [])

        for intent in list_of_intents:
            if intent.get("tag") == tag:
                respostas = intent.get("responses", [])

                if respostas:
                    return random.choice(respostas), tag

        return (
            "Não encontrei uma resposta adequada.",
            "fora_do_escopo"
        )

    def responder(
        self,
        mensagem: str,
        contexto_anterior: Optional[str] = None
    ) -> Tuple[str, str]:

        intents = self.predict_class(mensagem)

        resposta, contexto = self.get_response(intents)

        return resposta, contexto


chatbot_instance = None


def get_chatbot():
    global chatbot_instance

    if chatbot_instance is None:
        logger.info("Carregando modelo do chatbot...")
        chatbot_instance = ChatBot()
        logger.info("Modelo carregado com sucesso.")

    return chatbot_instance


def responder_chatbot(
    mensagem: str,
    contexto_anterior: Optional[str] = None
):
    chatbot = get_chatbot()

    return chatbot.responder(
        mensagem,
        contexto_anterior
    )