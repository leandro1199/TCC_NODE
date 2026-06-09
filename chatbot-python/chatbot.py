import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import json
import logging
import pickle
import random
import re
import unicodedata

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import tf_keras as keras
from sentence_transformers import SentenceTransformer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent


CONFIG = {
    "ERROR_THRESHOLD": float(os.getenv("ERROR_THRESHOLD", 0.45)),
    "HIGH_CONFIDENCE_THRESHOLD": float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", 0.75)),

    "MODEL_PATH": BASE_DIR / "model_chatbot.keras",
    "CLASSES_PATH": BASE_DIR / "classes.pkl",
    "INTENTS_PATH": BASE_DIR.parent / "json" / "intents.json",

    "DEFAULT_EMBEDDING_MODEL": "paraphrase-multilingual-mpnet-base-v2"
}


class ChatBot:

    def __init__(self):
        self.model = None
        self.embedding_model = None
        self.intents = None
        self.classes = None
        self.embedding_model_name = CONFIG["DEFAULT_EMBEDDING_MODEL"]

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
            raise FileNotFoundError(f"Modelo não encontrado: {CONFIG['MODEL_PATH']}")

        if not CONFIG["INTENTS_PATH"].exists():
            raise FileNotFoundError(f"Intents não encontrado: {CONFIG['INTENTS_PATH']}")

        if not CONFIG["CLASSES_PATH"].exists():
            raise FileNotFoundError(f"Classes não encontrado: {CONFIG['CLASSES_PATH']}")

        self.model = keras.models.load_model(
            str(CONFIG["MODEL_PATH"]),
            compile=False
        )

        with open(CONFIG["INTENTS_PATH"], "r", encoding="utf-8") as f:
            self.intents = json.load(f)

        with open(CONFIG["CLASSES_PATH"], "rb") as f:
            loaded = pickle.load(f)

        if isinstance(loaded, dict):
            self.classes = loaded.get("classes", [])
            self.embedding_model_name = loaded.get(
                "embedding_model_name",
                CONFIG["DEFAULT_EMBEDDING_MODEL"]
            )

            recommended_error = loaded.get("recommended_error_threshold")
            recommended_high = loaded.get("recommended_high_confidence_threshold")

            if recommended_error is not None and "ERROR_THRESHOLD" not in os.environ:
                CONFIG["ERROR_THRESHOLD"] = float(recommended_error)

            if recommended_high is not None and "HIGH_CONFIDENCE_THRESHOLD" not in os.environ:
                CONFIG["HIGH_CONFIDENCE_THRESHOLD"] = float(recommended_high)
        else:
            self.classes = loaded

        if not self.classes:
            raise ValueError("Nenhuma classe foi carregada do classes.pkl.")

        self.embedding_model = SentenceTransformer(
            self.embedding_model_name
        )

        logger.info("Chatbot carregado com sucesso.")
        logger.info("Modelo de embedding: %s", self.embedding_model_name)
        logger.info("Total de classes: %d", len(self.classes))
        logger.info("Threshold: %.2f", CONFIG["ERROR_THRESHOLD"])

    def normalize_text(self, text: str) -> str:
        text = str(text).strip().lower()

        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("utf-8")

        text = re.sub(r"[^\w\s?/-]", "", text)
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    def gerar_embedding(self, sentence: str) -> np.ndarray:
        sentence = self.normalize_text(sentence)

        if not sentence:
            return np.empty((0, 384), dtype=np.float32)

        embedding = self.embedding_model.encode(
            [sentence],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype(np.float32)

        return embedding

    def predict_class(self, sentence: str) -> List[dict]:
        embedding = self.gerar_embedding(sentence)

        if embedding.size == 0:
            return []

        expected_dim = self.model.input_shape[-1]

        if embedding.shape[1] != expected_dim:
            raise ValueError(
                f"Dimensão do embedding incompatível. "
                f"Modelo espera {expected_dim}, mas recebeu {embedding.shape[1]}."
            )

        predictions = self.model.predict(
            embedding,
            verbose=0
        )[0]

        results = []

        for i, prob in enumerate(predictions):
            prob = float(prob)

            if prob >= CONFIG["ERROR_THRESHOLD"]:
                results.append({
                    "intent": self.classes[i],
                    "probability": str(prob)
                })

        results.sort(
            key=lambda x: float(x["probability"]),
            reverse=True
        )

        return results

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

        for intent in self.intents.get("intents", []):
            if intent.get("tag") == tag:
                responses = intent.get("responses", [])

                if responses:
                    return random.choice(responses), tag

                return (
                    "Encontrei o tema, mas não há resposta cadastrada para ele.",
                    tag
                )

        return (
            "Não encontrei uma resposta adequada.",
            "fora_do_escopo"
        )

    def responder(
        self,
        mensagem: str,
        contexto_anterior: Optional[str] = None
    ) -> Tuple[str, str]:

        if not mensagem or not mensagem.strip():
            return (
                "Por favor, envie uma mensagem válida.",
                "fora_do_escopo"
            )

        intents = self.predict_class(mensagem)
        resposta, contexto = self.get_response(intents)

        return resposta, contexto


chatbot_instance = ChatBot()


def responder_chatbot(
    mensagem: str,
    contexto_anterior: Optional[str] = None
):
    return chatbot_instance.responder(
        mensagem,
        contexto_anterior
    )