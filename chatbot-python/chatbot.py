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

    "EMBEDDING_MODEL_NAME": os.getenv(
        "EMBEDDING_MODEL_NAME",
        "all-MiniLM-L6-v2"
    ),

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
            raise ValueError("Nome do banco inválido.")

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
                f"""
                CREATE DATABASE IF NOT EXISTS `{db_name}`
                CHARACTER SET utf8mb4
                COLLATE utf8mb4_unicode_ci
                """
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

    def _column_exists(
        self,
        cursor,
        table_name: str,
        column_name: str
    ) -> bool:

        cursor.execute(
            f"SHOW COLUMNS FROM `{table_name}` LIKE %s",
            (column_name,)
        )

        return cursor.fetchone() is not None

    def _create_tables(self):

        conn = None
        cursor = None

        try:

            conn = self._connect_with_db()
            cursor = conn.cursor()

            # ================= USUÁRIOS =================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (

                    id INT AUTO_INCREMENT PRIMARY KEY,

                    nome VARCHAR(100) NOT NULL,

                    email VARCHAR(150) NOT NULL UNIQUE,

                    senha VARCHAR(255) NOT NULL,

                    criado_em TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ================= INTERAÇÕES =================

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interacoes (

                    id INT AUTO_INCREMENT PRIMARY KEY,

                    usuario_id INT NULL,

                    pergunta_usuario TEXT NOT NULL,

                    resposta_bot TEXT NOT NULL,

                    intent_detectada VARCHAR(100)
                    DEFAULT 'desconhecida',

                    fallback_usado VARCHAR(50)
                    DEFAULT 'nenhum',

                    confianca DECIMAL(7,6)
                    DEFAULT 0.000000,

                    criado_em TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ================= MIGRAÇÕES =================

            if not self._column_exists(
                cursor,
                "interacoes",
                "usuario_id"
            ):

                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN usuario_id INT NULL
                """)

            if not self._column_exists(
                cursor,
                "usuarios",
                "criado_em"
            ):

                cursor.execute("""
                    ALTER TABLE usuarios
                    ADD COLUMN criado_em TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
                """)

            if not self._column_exists(
                cursor,
                "interacoes",
                "fallback_usado"
            ):

                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN fallback_usado VARCHAR(50)
                    DEFAULT 'nenhum'
                """)

            if not self._column_exists(
                cursor,
                "interacoes",
                "confianca"
            ):

                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN confianca DECIMAL(7,6)
                    DEFAULT 0.000000
                """)

            if not self._column_exists(
                cursor,
                "interacoes",
                "criado_em"
            ):

                cursor.execute("""
                    ALTER TABLE interacoes
                    ADD COLUMN criado_em TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP
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

    # 🔥 DESATIVADO
    # Quem salva agora é o Node.js
    def save_interaction(
        self,
        user_msg: str,
        bot_response: str,
        intent: str = "desconhecida",
        confidence: float = 0.0,
        fallback_used: str = "nenhum"
    ):

        pass


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
            raise FileNotFoundError(
                f"Modelo não encontrado em: {CONFIG['MODEL_PATH']}"
            )

        if not CONFIG["INTENTS_PATH"].exists():
            raise FileNotFoundError(
                f"Arquivo intents não encontrado: {CONFIG['INTENTS_PATH']}"
            )

        if not CONFIG["CLASSES_PATH"].exists():
            raise FileNotFoundError(
                f"Arquivo classes não encontrado: {CONFIG['CLASSES_PATH']}"
            )

        self.model = keras.models.load_model(
            str(CONFIG["MODEL_PATH"]),
            compile=False
        )

        with open(
            CONFIG["INTENTS_PATH"],
            "r",
            encoding="utf-8"
        ) as f:

            self.intents = json.load(f)

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

        self.embedding_model = SentenceTransformer(
            CONFIG["EMBEDDING_MODEL_NAME"]
        )

        logger.info("Chatbot carregado.")

    def _init_mysql(self):

        try:

            self.mysql = MySQLManager(
                CONFIG["MYSQL_CONFIG"]
            )

            logger.info("MySQL conectado.")

        except Exception as e:

            logger.warning(
                "MySQL indisponível: %s",
                e
            )

            self.mysql = None