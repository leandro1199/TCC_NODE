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


# ================= BASE =================

BASE_DIR = Path(__file__).resolve().parent


CONFIG = {

    "ERROR_THRESHOLD": float(
        os.getenv("ERROR_THRESHOLD", 0.35)
    ),

    "HIGH_CONFIDENCE_THRESHOLD": float(
        os.getenv("HIGH_CONFIDENCE_THRESHOLD", 0.70)
    ),

    "MODEL_PATH": BASE_DIR / "model_chatbot.keras",

    "CLASSES_PATH": BASE_DIR / "classes.pkl",

    "INTENTS_PATH": BASE_DIR / "json" / "intents.json",

    "EMBEDDING_MODEL_NAME": os.getenv(
        "EMBEDDING_MODEL_NAME",
        "all-MiniLM-L6-v2"
    )
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

    # ================= LOAD =================

    def _load_files(self):

        if not CONFIG["MODEL_PATH"].exists():
            raise FileNotFoundError(
                f"Modelo não encontrado em: "
                f"{CONFIG['MODEL_PATH']}"
            )

        if not CONFIG["INTENTS_PATH"].exists():
            raise FileNotFoundError(
                f"Arquivo intents não encontrado: "
                f"{CONFIG['INTENTS_PATH']}"
            )

        if not CONFIG["CLASSES_PATH"].exists():
            raise FileNotFoundError(
                f"Arquivo classes não encontrado: "
                f"{CONFIG['CLASSES_PATH']}"
            )

        # ===== MODEL =====

        self.model = keras.models.load_model(
            str(CONFIG["MODEL_PATH"]),
            compile=False
        )

        # ===== INTENTS =====

        with open(
            CONFIG["INTENTS_PATH"],
            "r",
            encoding="utf-8"
        ) as f:

            self.intents = json.load(f)

        # ===== CLASSES =====

        with open(
            CONFIG["CLASSES_PATH"],
            "rb"
        ) as f:

            loaded = pickle.load(f)

        self.classes = (
            loaded["classes"]
            if isinstance(loaded, dict)
            and "classes" in loaded
            else loaded
        )

        # ===== EMBEDDINGS =====

        self.embedding_model = SentenceTransformer(
            CONFIG["EMBEDDING_MODEL_NAME"]
        )

        logger.info("Chatbot carregado com sucesso.")

    # ================= TEXTO =================

    def normalize_text(self, text: str) -> str:

        text = text.lower().strip()

        text = unicodedata.normalize(
            "NFKD",
            text
        ).encode(
            "ascii",
            "ignore"
        ).decode(
            "utf-8"
        )

        text = re.sub(
            r"[^a-zA-Z0-9\s]",
            "",
            text
        )

        return text

    # ================= BAG OF WORDS =================

    def bag_of_words(
        self,
        sentence: str
    ) -> np.ndarray:

        words = self.normalize_text(sentence).split()

        bag = [0] * len(self.classes)

        for w in words:

            for i, word in enumerate(self.classes):

                if word == w:
                    bag[i] = 1

        return np.array(bag)

    # ================= PREDIÇÃO =================

    def predict_class(
        self,
        sentence: str
    ) -> List[dict]:

        bow = self.bag_of_words(sentence)

        res = self.model.predict(
            np.array([bow]),
            verbose=0
        )[0]

        ERROR_THRESHOLD = CONFIG["ERROR_THRESHOLD"]

        results = [
            [i, r]
            for i, r in enumerate(res)
            if r > ERROR_THRESHOLD
        ]

        results.sort(
            key=lambda x: x[1],
            reverse=True
        )

        return_list = []

        for r in results:

            return_list.append({
                "intent": self.classes[r[0]],
                "probability": str(r[1])
            })

        return return_list

    # ================= RESPOSTA =================

    def get_response(
        self,
        intents_list: List[dict]
    ) -> Tuple[str, str]:

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

        list_of_intents = self.intents["intents"]

        for intent in list_of_intents:

            if intent["tag"] == tag:

                resposta = random.choice(
                    intent["responses"]
                )

                return resposta, tag

        return (
            "Não encontrei uma resposta adequada.",
            "fora_do_escopo"
        )

    # ================= CHAT =================

    def responder(
        self,
        mensagem: str,
        contexto_anterior: Optional[str] = None
    ) -> Tuple[str, str]:

        mensagem = self.normalize_text(mensagem)

        intents = self.predict_class(mensagem)

        resposta, contexto = self.get_response(intents)

        return resposta, contexto


# ================= INSTÂNCIA GLOBAL =================

chatbot_instance = ChatBot()


# ================= FUNÇÃO EXPORTADA =================

def responder_chatbot(
    mensagem: str,
    contexto_anterior: Optional[str] = None
):

    return chatbot_instance.responder(
        mensagem,
        contexto_anterior
    )