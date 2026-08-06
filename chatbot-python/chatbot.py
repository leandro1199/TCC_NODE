import os

os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import logging
import pickle
import random
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

import numpy as np
import tf_keras as keras

from text_utils import load_embedding_model, normalize_text


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

CONFIG = {
    "ERROR_THRESHOLD": float(os.getenv("ERROR_THRESHOLD", "0.55")),
    "HIGH_CONFIDENCE_THRESHOLD": float(
        os.getenv("HIGH_CONFIDENCE_THRESHOLD", "0.80")
    ),
    "MINIMUM_MARGIN": float(os.getenv("MINIMUM_MARGIN", "0.10")),
    "MAX_MESSAGE_LENGTH": int(os.getenv("MAX_MESSAGE_LENGTH", "1000")),
    "MODEL_PATH": BASE_DIR / "model_chatbot.keras",
    "CLASSES_PATH": BASE_DIR / "classes.pkl",
    "INTENTS_PATH": Path(
        os.getenv("INTENTS_PATH", PROJECT_DIR / "json" / "intents.json")
    ),
    "DEFAULT_EMBEDDING_MODEL": "paraphrase-multilingual-mpnet-base-v2",
}


class ChatBot:
    def __init__(self):
        self.model = None
        self.embedding_model = None
        self.intents: Dict = {}
        self.classes: List[str] = []
        self.embedding_model_name = CONFIG["DEFAULT_EMBEDDING_MODEL"]
        self.embedding_dimension = 0
        self.predict_lock = Lock()

        self.allowed_intents = set()

        self.context_hints = {
            "medicamento_esquecido": "esquecimento de medicamento",
            "medicamento_horario": "horário de medicamento",
            "efeito_colateral_remedio": "efeito colateral de medicamento",
            "explicacao_hipertensao": "hipertensão",
            "explicacao_diabetes": "diabetes",
            "explicacao_artrose": "artrose",
            "explicacao_osteoporose": "osteoporose",
            "dor_articulacao": "dor nas articulações",
            "dor_coluna_costas": "dor na coluna e nas costas",
            "dor_cabeca": "dor de cabeça",
            "tontura_mal_estar": "tontura e mal-estar",
            "pressao_alta_baixa": "pressão alta ou baixa",
            "glicose_diabetes_controle": "controle da glicose e diabetes",
            "exercicio_dor_joelho": "exercício para dor no joelho",
            "exercicio_dor_coluna": "exercício para dor na coluna",
            "exercicio_equilibrio": "exercício de equilíbrio",
            "prevencao_quedas": "prevenção de quedas",
            "memoria_esquecimento": "memória e esquecimento",
            "sono_insonia": "sono e insônia",
            "hidratacao": "hidratação",
            "alimentacao_idoso": "alimentação da pessoa idosa",
            "ansiedade_emocional": "ansiedade e estado emocional",
            "solidao": "solidão",
            "luto_tristeza": "luto e tristeza",
        }

        self._load_files()

    def _load_files(self) -> None:
        for path in (
            CONFIG["MODEL_PATH"],
            CONFIG["CLASSES_PATH"],
            CONFIG["INTENTS_PATH"],
        ):
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")

        self.model = keras.models.load_model(
            str(CONFIG["MODEL_PATH"]), compile=False
        )

        with CONFIG["INTENTS_PATH"].open("r", encoding="utf-8") as file:
            self.intents = json.load(file)

        with CONFIG["CLASSES_PATH"].open("rb") as file:
            metadata = pickle.load(file)

        if isinstance(metadata, dict):
            self.classes = list(metadata.get("classes", []))
            self.embedding_model_name = metadata.get(
                "embedding_model_name", CONFIG["DEFAULT_EMBEDDING_MODEL"]
            )

            recommended_values = {
                "ERROR_THRESHOLD": "recommended_error_threshold",
                "HIGH_CONFIDENCE_THRESHOLD":
                    "recommended_high_confidence_threshold",
                "MINIMUM_MARGIN": "recommended_minimum_margin",
            }
            for env_name, metadata_name in recommended_values.items():
                value = metadata.get(metadata_name)
                if value is not None and env_name not in os.environ:
                    CONFIG[env_name] = float(value)
        else:
            self.classes = list(metadata)

        if not self.classes:
            raise ValueError("Nenhuma classe foi encontrada em classes.pkl.")

        self.embedding_model = load_embedding_model(self.embedding_model_name)

        get_dimension = getattr(
            self.embedding_model, "get_embedding_dimension", None
        )
        if get_dimension is None:
            get_dimension = self.embedding_model.get_sentence_embedding_dimension
        self.embedding_dimension = int(get_dimension())

        expected_input = int(self.model.input_shape[-1])
        expected_output = int(self.model.output_shape[-1])

        if expected_input != self.embedding_dimension:
            raise ValueError(
                "Dimensão incompatível: o modelo Keras espera "
                f"{expected_input}, mas o SentenceTransformer gera "
                f"{self.embedding_dimension}. Treine o modelo novamente."
            )

        if expected_output != len(self.classes):
            raise ValueError(
                "Quantidade de classes incompatível: o modelo possui "
                f"{expected_output} saídas e classes.pkl possui "
                f"{len(self.classes)} classes."
            )

        intent_tags = {
            item.get("tag") for item in self.intents.get("intents", [])
            if isinstance(item, dict)
        }
        self.allowed_intents = {tag for tag in intent_tags if tag}
        missing_tags = set(self.classes) - intent_tags
        if missing_tags:
            raise ValueError(
                "Classes ausentes no intents.json: "
                + ", ".join(sorted(missing_tags))
            )

        logger.info("Chatbot carregado com %d classes.", len(self.classes))
        logger.info("Modelo de embeddings: %s", self.embedding_model_name)
        logger.info(
            "Threshold: %.2f | confiança alta: %.2f | margem: %.2f",
            CONFIG["ERROR_THRESHOLD"],
            CONFIG["HIGH_CONFIDENCE_THRESHOLD"],
            CONFIG["MINIMUM_MARGIN"],
        )

    @staticmethod
    def detectar_emergencia(mensagem: str) -> bool:
        texto = normalize_text(mensagem)
        sinais_graves = (
            "dor no peito", "falta de ar", "não consigo respirar",
            "nao consigo respirar", "desmaiei", "desmaiou", "convulsão",
            "convulsao", "rosto torto", "boca torta",
            "fraqueza em um lado", "não consigo falar", "nao consigo falar",
            "sangramento intenso", "quero me matar", "tirar minha vida",
        )
        return any(sinal in texto for sinal in sinais_graves)

    def _is_follow_up(self, mensagem: str) -> bool:
        texto = normalize_text(mensagem)
        words = texto.split()
        starters = (
            "e ", "isso", "ele", "ela", "também", "tambem",
            "como assim", "pode explicar", "o que faço", "e agora",
        )
        return len(words) <= 8 and any(texto.startswith(x) for x in starters)

    def _text_with_context(
        self, mensagem: str, contexto_anterior: Optional[str]
    ) -> str:
        if (
            contexto_anterior in self.context_hints
            and self._is_follow_up(mensagem)
        ):
            return f"{self.context_hints[contexto_anterior]}. {mensagem}"
        return mensagem

    def gerar_embedding(self, sentence: str) -> Optional[np.ndarray]:
        sentence = normalize_text(sentence)
        if not sentence:
            return None

        return self.embedding_model.encode(
            [sentence],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

    def predict_class(
        self,
        sentence: str,
        contexto_anterior: Optional[str] = None,
    ) -> List[dict]:
        prepared_text = self._text_with_context(sentence, contexto_anterior)
        embedding = self.gerar_embedding(prepared_text)
        if embedding is None:
            return []

        with self.predict_lock:
            probabilities = self.model.predict(embedding, verbose=0)[0]

        results = [
            {"intent": self.classes[index], "probability": float(probability)}
            for index, probability in enumerate(probabilities)
        ]
        results.sort(key=lambda item: item["probability"], reverse=True)

        best = results[0]
        if best["probability"] < CONFIG["ERROR_THRESHOLD"]:
            return []

        if len(results) > 1:
            margin = best["probability"] - results[1]["probability"]
            if (
                best["probability"] < CONFIG["HIGH_CONFIDENCE_THRESHOLD"]
                and margin < CONFIG["MINIMUM_MARGIN"]
            ):
                logger.info(
                    "Classificação ambígua: %s (%.3f) / %s (%.3f)",
                    best["intent"], best["probability"],
                    results[1]["intent"], results[1]["probability"],
                )
                return []

        return results[:3]

    def get_response(self, intents_list: List[dict]) -> Tuple[str, str]:
        if not intents_list:
            return (
                "Não entendi com segurança. Pode escrever novamente com "
                "mais detalhes?",
                "fora_do_escopo",
            )

        tag = intents_list[0]["intent"]
        if tag not in self.allowed_intents:
            logger.warning("Intenção não permitida: %s", tag)
            return (
                "Desculpe, esse assunto está fora das minhas funções.",
                "fora_do_escopo",
            )

        responses = [
            response
            for intent in self.intents.get("intents", [])
            if intent.get("tag") == tag
            for response in intent.get("responses", [])
            if isinstance(response, str) and response.strip()
        ]
        if responses:
            return random.choice(responses), tag

        return (
            "Não encontrei uma resposta cadastrada para esse assunto.",
            "fora_do_escopo",
        )

    def responder(
        self,
        mensagem: str,
        contexto_anterior: Optional[str] = None,
    ) -> Tuple[str, str]:
        if not isinstance(mensagem, str) or not mensagem.strip():
            return "Por favor, envie uma mensagem válida.", "fora_do_escopo"

        if len(mensagem) > CONFIG["MAX_MESSAGE_LENGTH"]:
            return "A mensagem é muito longa. Tente resumi-la.", "fora_do_escopo"

        if self.detectar_emergencia(mensagem):
            return (
                "Isso pode ser uma emergência. Procure atendimento "
                "imediatamente ou ligue para o SAMU no número 192. "
                "Não espere apenas pela resposta do chatbot.",
                "emergencia_sinais_graves",
            )

        intents = self.predict_class(mensagem, contexto_anterior)
        if intents:
            logger.info(
                "Intenção: %s | confiança: %.3f",
                intents[0]["intent"], intents[0]["probability"],
            )

        return self.get_response(intents)


chatbot_instance = ChatBot()


def responder_chatbot(
    mensagem: str,
    contexto_anterior: Optional[str] = None,
) -> Tuple[str, str]:
    return chatbot_instance.responder(
        mensagem=mensagem,
        contexto_anterior=contexto_anterior,
    )
