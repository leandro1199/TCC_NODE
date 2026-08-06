import os

os.environ["TF_USE_LEGACY_KERAS"] = "1"
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import json
import logging
import pickle
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from tf_keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tf_keras.layers import Dense, Dropout, Input
from tf_keras.models import Sequential, load_model
from tf_keras.optimizers import Adam
from tf_keras.regularizers import l2

from text_utils import load_embedding_model, normalize_text


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
MIN_EXAMPLES_PER_CLASS = int(os.getenv("MIN_EXAMPLES_PER_CLASS", "4"))
RANDOM_SEED = 42


class ChatBotTrainer:
    def __init__(
        self,
        intents_file=None,
        embedding_model_name="paraphrase-multilingual-mpnet-base-v2",
        model_path=None,
        classes_path=None,
    ):
        self.intents_file = (
            Path(intents_file) if intents_file
            else PROJECT_DIR / "json" / "intents.json"
        )
        self.embedding_model_name = embedding_model_name
        self.embedding_model = load_embedding_model(self.embedding_model_name)
        self.model = None
        self.classes: List[str] = []
        self.model_path = (
            Path(model_path) if model_path
            else BASE_DIR / "model_chatbot.keras"
        )
        self.classes_path = (
            Path(classes_path) if classes_path
            else BASE_DIR / "classes.pkl"
        )

    def prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        if not self.intents_file.exists():
            raise FileNotFoundError(
                f"Arquivo de intents não encontrado: {self.intents_file}"
            )

        with self.intents_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        intents = data.get("intents")
        if not isinstance(intents, list):
            raise ValueError(
                "O intents.json não possui a chave 'intents' em formato válido."
            )

        pattern_to_tag: Dict[str, str] = {}
        ignored_patterns = {"sim", "não", "nao", "ok", "certo", "beleza"}

        for intent in intents:
            if not isinstance(intent, dict):
                logger.warning("Intent inválida ignorada: %r", intent)
                continue

            tag = intent.get("tag")
            patterns = intent.get("patterns", [])
            if not tag or not isinstance(patterns, list):
                logger.warning("Intent inválida ignorada: %r", intent)
                continue

            for pattern in patterns:
                normalized = normalize_text(pattern)
                if not normalized or normalized in ignored_patterns:
                    continue

                previous_tag = pattern_to_tag.get(normalized)
                if previous_tag == tag:
                    continue

                if previous_tag and previous_tag != tag:
                    # Sinais de emergência devem prevalecer sobre intenções
                    # informativas. Nos demais conflitos, preservamos a
                    # primeira ocorrência para não treinar rótulos ambíguos.
                    if tag == "emergencia_sinais_graves":
                        pattern_to_tag[normalized] = tag
                    logger.warning(
                        "Frase ambígua '%s': %s / %s. Usando %s.",
                        normalized,
                        previous_tag,
                        tag,
                        pattern_to_tag[normalized],
                    )
                    continue

                pattern_to_tag[normalized] = tag

        texts = list(pattern_to_tag)
        labels = list(pattern_to_tag.values())

        if not texts:
            raise ValueError("Nenhum dado de treinamento válido foi encontrado.")

        class_counts = Counter(labels)
        weak_classes = {
            label: count for label, count in class_counts.items()
            if count < MIN_EXAMPLES_PER_CLASS
        }
        if weak_classes:
            details = ", ".join(
                f"{name}={count}" for name, count in sorted(weak_classes.items())
            )
            raise ValueError(
                f"Cada intenção precisa de pelo menos {MIN_EXAMPLES_PER_CLASS} "
                f"frases diferentes. Corrija: {details}."
            )

        self.classes = sorted(class_counts)
        class_to_index = {tag: index for index, tag in enumerate(self.classes)}

        logger.info("Gerando embeddings com: %s", self.embedding_model_name)
        X = self.embedding_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).astype(np.float32)
        y = np.array([class_to_index[tag] for tag in labels], dtype=np.int32)

        logger.info("Exemplos: %d | classes: %d", len(texts), len(self.classes))
        logger.info("Distribuição: %s", dict(class_counts))
        return X, y

    @staticmethod
    def build_model(input_size: int, output_size: int):
        model = Sequential([
            Input(shape=(input_size,)),
            Dense(128, activation="relu", kernel_regularizer=l2(1e-4)),
            Dropout(0.35),
            Dense(64, activation="relu", kernel_regularizer=l2(1e-4)),
            Dropout(0.25),
            Dense(output_size, activation="softmax"),
        ])
        model.compile(
            optimizer=Adam(learning_rate=1e-3),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.summary()
        return model

    @staticmethod
    def recommend_threshold(
        probabilities: np.ndarray,
        expected: np.ndarray,
        minimum_precision: float = 0.85,
    ) -> float:
        """Escolhe um limite que busca 85% de acerto entre respostas aceitas."""
        predicted = np.argmax(probabilities, axis=1)
        confidence = np.max(probabilities, axis=1)
        correct = predicted == expected
        best_threshold = 0.55
        best_coverage = -1.0

        for threshold in np.arange(0.35, 0.91, 0.01):
            accepted = confidence >= threshold
            if not np.any(accepted):
                continue

            precision = float(np.mean(correct[accepted]))
            coverage = float(np.mean(accepted))
            if precision >= minimum_precision and coverage > best_coverage:
                best_threshold = float(threshold)
                best_coverage = coverage

        return round(best_threshold, 2)

    def train(self, epochs=100, batch_size=8, test_size=0.25):
        np.random.seed(RANDOM_SEED)
        tf.random.set_seed(RANDOM_SEED)
        X, y = self.prepare_training_data()
        if len(np.unique(y)) < 2:
            raise ValueError("É necessário ter pelo menos duas classes.")

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.classes_path.parent.mkdir(parents=True, exist_ok=True)

        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=RANDOM_SEED,
            stratify=y,
        )
        logger.info(
            "Treino: %d amostras | validação: %d amostras",
            len(X_train), len(X_val),
        )

        self.model = self.build_model(X.shape[1], len(self.classes))
        unique_classes = np.unique(y_train)
        weights = compute_class_weight(
            class_weight="balanced", classes=unique_classes, y=y_train
        )
        class_weight = {
            int(label): float(weight)
            for label, weight in zip(unique_classes, weights)
        }

        callbacks = [
            ModelCheckpoint(
                filepath=str(self.model_path),
                monitor="val_loss",
                mode="min",
                save_best_only=True,
                verbose=1,
            ),
            EarlyStopping(
                monitor="val_loss",
                mode="min",
                patience=15,
                min_delta=0.001,
                restore_best_weights=True,
                verbose=1,
            ),
            ReduceLROnPlateau(
                monitor="val_loss",
                mode="min",
                factor=0.5,
                patience=5,
                min_delta=0.001,
                min_lr=1e-6,
                verbose=1,
            ),
        ]

        history = self.model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            class_weight=class_weight,
            verbose=1,
        )

        self.model = load_model(str(self.model_path), compile=False)
        validation_probabilities = self.model.predict(X_val, verbose=0)
        validation_predictions = np.argmax(validation_probabilities, axis=1)

        report = classification_report(
            y_val,
            validation_predictions,
            labels=list(range(len(self.classes))),
            target_names=self.classes,
            zero_division=0,
        )
        logger.info("Relatório de classificação:\n%s", report)
        logger.info(
            "Matriz de confusão:\n%s",
            confusion_matrix(
                y_val,
                validation_predictions,
                labels=list(range(len(self.classes))),
            ),
        )

        recommended_error = self.recommend_threshold(
            validation_probabilities, y_val
        )
        recommended_high = round(
            min(0.95, max(0.75, recommended_error + 0.20)), 2
        )

        metadata = {
            "classes": self.classes,
            "num_classes": len(self.classes),
            "embedding_model_name": self.embedding_model_name,
            "input_dim": int(X.shape[1]),
            "recommended_error_threshold": recommended_error,
            "recommended_high_confidence_threshold": recommended_high,
            "recommended_minimum_margin": 0.10,
            "normalization_version": "nfkc_keep_accents_v1",
        }
        with self.classes_path.open("wb") as file:
            pickle.dump(metadata, file)

        logger.info("Threshold recomendado: %.2f", recommended_error)
        logger.info("Modelo salvo em: %s", self.model_path.resolve())
        logger.info("Classes salvas em: %s", self.classes_path.resolve())
        return history

    def load_trained_model(self) -> None:
        if not self.model_path.exists() or not self.classes_path.exists():
            raise FileNotFoundError("Modelo ou classes.pkl não encontrado.")

        self.model = load_model(str(self.model_path), compile=False)
        with self.classes_path.open("rb") as file:
            metadata = pickle.load(file)

        self.classes = (
            list(metadata["classes"])
            if isinstance(metadata, dict) else list(metadata)
        )

    def predict_intent(self, sentence, top_n=3, threshold=0.55):
        if self.model is None:
            raise RuntimeError("Modelo ainda não foi treinado ou carregado.")

        sentence = normalize_text(sentence)
        if not sentence:
            return [("sem_entendimento", 0.0)]

        vector = self.embedding_model.encode(
            [sentence],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)
        probabilities = self.model.predict(vector, verbose=0)[0]
        indices = probabilities.argsort()[::-1][:top_n]
        results = [
            (self.classes[index], float(probabilities[index]))
            for index in indices
        ]
        filtered = [item for item in results if item[1] >= threshold]
        return filtered or [("sem_entendimento", float(results[0][1]))]


if __name__ == "__main__":
    np.random.seed(RANDOM_SEED)
    tf.random.set_seed(RANDOM_SEED)
    trainer = ChatBotTrainer()
    trainer.train(epochs=100, batch_size=8, test_size=0.25)
