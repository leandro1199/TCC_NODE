import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import json
import logging
import pickle
import random
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple
import mysql.connector
import numpy as np
import tf_keras as keras
from mysql.connector import Error
from sentence_transformers import SentenceTransformer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG = {
    "ERROR_THRESHOLD": float(os.getenv("ERROR_THRESHOLD", 0.35)),
    "HIGH_CONFIDENCE_THRESHOLD": float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", 0.70)),
    "MODEL_PATH": BASE_DIR / "model_chatbot.keras",
    "CLASSES_PATH": BASE_DIR / "classes.pkl",
    "INTENTS_PATH": BASE_DIR / "json" / "intents.json",
    "EMBEDDING_MODEL_NAME": os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2"),
    "MYSQL_CONFIG": {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "1011"),
        "port": int(os.getenv("DB_PORT", 3308)),
        "database": os.getenv("DB_NAME", "chatbot_db"),
    }
}


class MySQLManager:
    def __init__(self, config: dict):
        self.config = config
        self._validate_database_name()
        self._create_database()
        self._create_tables()

    def _validate_database_name(self):
        db_name = self.config["database"]
        if not re.fullmatch(r"[A-Za-z0-9_]+", db_name):
            raise ValueError("Nome do banco de dados inválido.")

    def _connect_no_db(self):
        return mysql.connector.connect(
            host=self.config["host"],
            user=self.config["user"],
            password=self.config["password"],
            port=self.config["port"]
        )

    def _connect_with_db(self):
        return mysql.connector.connect(
            host=self.config["host"],
            user=self.config["user"],
            password=self.config["password"],
            port=self.config["port"],
            database=self.config["database"]
        )

    def _create_database(self):
        conn = None
        cursor = None

        try:
            conn = self._connect_no_db()
            cursor = conn.cursor()

            db_name = self.config["database"]

            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )

            conn.commit()
            logger.info("Banco de dados pronto.")

        except Error as e:
            logger.error("Erro ao criar banco: %s", e)
            raise

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _column_exists(self, cursor, table_name: str, column_name: str) -> bool:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}` LIKE %s", (column_name,))
        return cursor.fetchone() is not None

    def _create_tables(self):
        conn = None
        cursor = None

        try:
            conn = self._connect_with_db()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nome VARCHAR(100) NOT NULL,
                    email VARCHAR(150) NOT NULL UNIQUE,
                    senha VARCHAR(255) NOT NULL,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interacoes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    pergunta_usuario TEXT NOT NULL,
                    resposta_bot TEXT NOT NULL,
                    intent_detectada VARCHAR(100) DEFAULT 'desconhecida',
                    fallback_usado VARCHAR(50) DEFAULT 'nenhum',
                    confianca DECIMAL(7,6) DEFAULT 0.000000,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            if not self._column_exists(cursor, "usuarios", "criado_em"):
                cursor.execute("""
                    ALTER TABLE usuarios
                    ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """)

            if not self._column_exists(cursor, "interacoes", "fallback_usado"):
                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN fallback_usado VARCHAR(50) DEFAULT 'nenhum'
                """)

            if not self._column_exists(cursor, "interacoes", "confianca"):
                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN confianca DECIMAL(7,6) DEFAULT 0.000000
                """)

            if not self._column_exists(cursor, "interacoes", "criado_em"):
                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """)

            conn.commit()
            logger.info("Tabelas prontas.")

        except Error as e:
            logger.error("Erro ao criar tabelas: %s", e)
            raise

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_interaction(
        self,
        user_msg: str,
        bot_response: str,
        intent: str = "desconhecida",
        confidence: float = 0.0,
        fallback_used: str = "nenhum"
    ):
        conn = None
        cursor = None

        try:
            conn = self._connect_with_db()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO interacoes
                (pergunta_usuario, resposta_bot, intent_detectada, fallback_usado, confianca)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                user_msg,
                bot_response,
                intent,
                fallback_used,
                float(confidence)
            ))

            conn.commit()

        except Error as e:
            logger.error("Erro ao salvar interação no MySQL: %s", e)

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


class ChatBot:
    def __init__(self):
        self.model = None
        self.intents = None
        self.classes = None
        self.mysql = None
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
        self._init_mysql()

    def _load_files(self):
        if not CONFIG["MODEL_PATH"].exists():
            raise FileNotFoundError(f"Modelo não encontrado em: {CONFIG['MODEL_PATH']}")

        if not CONFIG["INTENTS_PATH"].exists():
            raise FileNotFoundError(f"Arquivo intents não encontrado em: {CONFIG['INTENTS_PATH']}")

        if not CONFIG["CLASSES_PATH"].exists():
            raise FileNotFoundError(f"Arquivo classes não encontrado em: {CONFIG['CLASSES_PATH']}")

        self.model = keras.models.load_model(str(CONFIG["MODEL_PATH"]), compile=False)

        with open(CONFIG["INTENTS_PATH"], "r", encoding="utf-8") as f:
            self.intents = json.load(f)

        with open(CONFIG["CLASSES_PATH"], "rb") as f:
            loaded = pickle.load(f)

        self.classes = loaded["classes"] if isinstance(loaded, dict) and "classes" in loaded else loaded

        self.embedding_model = SentenceTransformer(CONFIG["EMBEDDING_MODEL_NAME"])

        logger.info("Chatbot carregado com sucesso.")

    def _init_mysql(self):
        try:
            self.mysql = MySQLManager(CONFIG["MYSQL_CONFIG"])
            logger.info("MySQL conectado com sucesso.")
        except Exception as e:
            logger.warning("MySQL indisponível. O bot seguirá sem banco. Motivo: %s", e)
            self.mysql = None

    def _remove_accents(self, text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")

    def _normalize_text(self, text: str) -> str:
        text = self._remove_accents(str(text).lower().strip())
        text = re.sub(r"[^\w\s?/-]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _get_response_from_intent(self, tag: str) -> Optional[str]:
        if not self.intents or "intents" not in self.intents:
            return None

        for intent in self.intents["intents"]:
            if intent.get("tag") == tag:
                responses = intent.get("responses", [])
                if responses:
                    return random.choice(responses)

        return None

    def _is_health_scope(self, text: str) -> bool:
        text_norm = self._normalize_text(text)

        scope_keywords = [
            "idoso", "idosa", "remedio", "medicacao", "dose", "pressao",
            "hipertensao", "diabetes", "glicose", "insulina", "dor",
            "joelho", "coluna", "costas", "artrose", "osteoporose",
            "osso", "articulacao", "memoria", "esquecimento", "sono",
            "insonia", "agua", "hidratacao", "alimentacao", "queda",
            "equilibrio", "tontura", "mal estar", "cabeca", "doenca",
            "exercicio", "alongamento", "fisioterapia", "caminhar",
            "cansaco", "fraqueza", "visao", "idosos", "cuidador",
            "familiar", "saude", "bem estar"
        ]

        return any(keyword in text_norm for keyword in scope_keywords)

    def _is_emergency_message(self, text: str) -> bool:
        text_norm = self._normalize_text(text)

        emergency_patterns = [
            r"\bdor no peito\b",
            r"\bfalta de ar\b",
            r"\bnao consigo respirar\b",
            r"\bfraqueza de um lado\b",
            r"\bfala enrolada\b",
            r"\bdesmaiei\b",
            r"\bcai e bati a cabeca\b",
            r"\bestou muito confuso\b",
            r"\bconfusao mental\b"
        ]

        return any(re.search(pattern, text_norm) for pattern in emergency_patterns)

    def _predict_intent(self, text: str) -> List[dict]:
        if not text or not text.strip():
            return []

        try:
            vec = self.embedding_model.encode(
                [self._normalize_text(text)],
                convert_to_numpy=True,
                normalize_embeddings=True
            ).astype(np.float32)

            result = self.model.predict(vec, verbose=0)[0]

            results = [
                {
                    "intent": self.classes[i],
                    "probability": float(prob)
                }
                for i, prob in enumerate(result)
                if float(prob) >= CONFIG["ERROR_THRESHOLD"]
            ]

            results.sort(key=lambda x: x["probability"], reverse=True)
            return results

        except Exception as e:
            logger.error("Erro em _predict_intent: %s", e)
            return []

    def _save_interaction(
        self,
        user_msg: str,
        bot_response: str,
        intent: str = "desconhecida",
        confidence: float = 0.0,
        fallback_used: str = "nenhum"
    ):
        if self.mysql:
            self.mysql.save_interaction(
                user_msg=user_msg,
                bot_response=bot_response,
                intent=intent,
                confidence=confidence,
                fallback_used=fallback_used
            )

    def _out_of_scope_response(self) -> str:
        return (
            "Prefiro me limitar a assuntos de saúde e cuidados da pessoa idosa. "
            "Você pode me perguntar sobre remédios, pressão, diabetes, dores, "
            "memória, sono, mobilidade ou prevenção de quedas."
        )

    def respond(self, message: str) -> str:
        return self.respond_with_details(message)["resposta"]

    def respond_with_details(self, message: str) -> dict:
        if not message or not message.strip():
            return {
                "resposta": "Digite uma mensagem válida.",
                "intent": "vazio",
                "confianca": 0.0,
                "fallback_usado": "entrada_vazia"
            }

        message = message.strip()
        logger.info("Mensagem recebida: %s", message)

        if self._is_emergency_message(message):
            response = self._get_response_from_intent("emergencia_sinais_graves")

            if not response:
                response = "Isso pode ser urgente. Procure atendimento imediatamente ou peça ajuda a alguém próximo."

            self._save_interaction(
                user_msg=message,
                bot_response=response,
                intent="emergencia_sinais_graves",
                confidence=1.0,
                fallback_used="regra_emergencia"
            )

            return {
                "resposta": response,
                "intent": "emergencia_sinais_graves",
                "confianca": 1.0,
                "fallback_usado": "regra_emergencia"
            }

        predictions = self._predict_intent(message)

        if predictions:
            best_intent = predictions[0]["intent"]
            best_confidence = predictions[0]["probability"]

            if (
                best_intent in self.allowed_intents
                and best_confidence >= CONFIG["HIGH_CONFIDENCE_THRESHOLD"]
            ):
                response = self._get_response_from_intent(best_intent)

                if response:
                    self._save_interaction(
                        user_msg=message,
                        bot_response=response,
                        intent=best_intent,
                        confidence=best_confidence,
                        fallback_used="modelo_especializado"
                    )

                    return {
                        "resposta": response,
                        "intent": best_intent,
                        "confianca": round(best_confidence, 4),
                        "fallback_usado": "modelo_especializado"
                    }

        if self._is_health_scope(message):
            if predictions:
                best_intent = predictions[0]["intent"]
                best_confidence = predictions[0]["probability"]

                if (
                    best_intent in self.allowed_intents
                    and best_confidence >= CONFIG["ERROR_THRESHOLD"]
                ):
                    response = self._get_response_from_intent(best_intent)

                    if response:
                        self._save_interaction(
                            user_msg=message,
                            bot_response=response,
                            intent=best_intent,
                            confidence=best_confidence,
                            fallback_used="modelo_moderado"
                        )

                        return {
                            "resposta": response,
                            "intent": best_intent,
                            "confianca": round(best_confidence, 4),
                            "fallback_usado": "modelo_moderado"
                        }

            response = (
                "Entendi que sua pergunta é sobre saúde ou cuidados do idoso, "
                "mas ainda não consegui identificar exatamente o tema. "
                "Tente perguntar de forma mais direta, por exemplo: "
                "'o que é hipertensão?', 'estou com dor no joelho', "
                "'esqueci meu remédio' ou 'como evitar quedas?'."
            )

            self._save_interaction(
                user_msg=message,
                bot_response=response,
                intent="saude_generica",
                confidence=0.0,
                fallback_used="saude_sem_intent"
            )

            return {
                "resposta": response,
                "intent": "saude_generica",
                "confianca": 0.0,
                "fallback_usado": "saude_sem_intent"
            }

        response = self._out_of_scope_response()

        self._save_interaction(
            user_msg=message,
            bot_response=response,
            intent="fora_do_escopo",
            confidence=0.0,
            fallback_used="bloqueio_escopo"
        )

        return {
            "resposta": response,
            "intent": "fora_do_escopo",
            "confianca": 0.0,
            "fallback_usado": "bloqueio_escopo"
        }

    def predict_intent(self, text: str, top_n: int = 1) -> List[Tuple[str, float]]:
        try:
            if not text or not text.strip():
                return []

            vec = self.embedding_model.encode(
                [self._normalize_text(text)],
                convert_to_numpy=True,
                normalize_embeddings=True
            ).astype(np.float32)

            result = self.model.predict(vec, verbose=0)[0]

            intents_probs = [
                (self.classes[i], float(prob))
                for i, prob in enumerate(result)
                if float(prob) > 0.01
            ]

            intents_probs.sort(key=lambda x: x[1], reverse=True)
            return intents_probs[:top_n]

        except Exception as e:
            logger.error("Erro em predict_intent: %s", e)
            return []


chatbot = ChatBot()


def responder(msg: str) -> str:
    return chatbot.respond(msg)



def responder_chatbot(mensagem, contexto_anterior=None):
    mensagem_normalizada = str(mensagem).lower().strip()

    # CONTEXTO: dor nas costas
    if contexto_anterior == "dor_coluna_costas":
        palavras_contexto = [
            "limite",
            "limites",
            "evitar",
            "posso",
            "esforço",
            "esforco",
            "quando parar",
            "o que nao posso",
            "o que não posso"
        ]

        if any(palavra in mensagem_normalizada for palavra in palavras_contexto):
            return (
                "Como você estava falando de dor nas costas, evite carregar peso, movimentos bruscos, torções e esforço excessivo. "
                "Se a dor aumentar, aparecer dormência, fraqueza ou dor muito forte, pare e procure orientação médica.",
                "dor_coluna_costas"
            )

    # CONTEXTO: dor nas articulações
    if contexto_anterior == "dor_articulacao":
        palavras_contexto = [
            "limite",
            "limites",
            "evitar",
            "posso",
            "esforço",
            "esforco",
            "quando parar"
        ]

        if any(palavra in mensagem_normalizada for palavra in palavras_contexto):
            return (
                "Como você estava falando de dor nas articulações, evite impacto, esforço excessivo e movimentos bruscos. "
                "Se houver inchaço, calor local ou dor forte, procure avaliação médica.",
                "dor_articulacao"
            )

    # Usa seu modelo real
    resultado = chatbot.respond_with_details(mensagem)

    resposta = resultado.get("resposta", "Não entendi completamente. Você pode explicar melhor?")
    intent = resultado.get("intent", "desconhecida")

    # Se caiu fora do escopo, mas havia contexto anterior, tenta responder melhor
    if intent in ["fora_do_escopo", "saude_generica"] and contexto_anterior:
        if contexto_anterior == "dor_coluna_costas":
            return (
                "Você está falando ainda da dor nas costas? Se sim, evite esforço, peso e movimentos bruscos. "
                "Se quiser, posso te orientar sobre movimentos leves e sinais de alerta.",
                "dor_coluna_costas"
            )

    return resposta, intent


if __name__ == "__main__":
    mensagem = " ".join(sys.argv[1:]).strip()

    if not mensagem:
        print(json.dumps({
            "resposta": "Digite uma mensagem válida.",
            "intent": "vazio",
            "confianca": 0.0,
            "fallback_usado": "entrada_vazia"
        }, ensure_ascii=False))
        sys.exit(0)

    resultado = chatbot.respond_with_details(mensagem)

    print(json.dumps(resultado, ensure_ascii=False))