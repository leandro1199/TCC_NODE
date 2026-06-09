import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

import json
import logging
import pickle
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from sentence_transformers import SentenceTransformer
from tf_keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tf_keras.layers import Dense, Dropout, Input
from tf_keras.models import Sequential, load_model
from tf_keras.optimizers import Adam

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MIN_EXAMPLES_PER_CLASS = 5


class ChatBotTrainer:
    def __init__(
        self,
        intents_file=None,
        embedding_model_name="paraphrase-multilingual-mpnet-base-v2",
        model_path=None,
        classes_path=None
    ):
        self.intents_file = Path(intents_file) if intents_file else BASE_DIR / "json" / "intents.json"
        self.embedding_model_name = embedding_model_name
        self.embedding_model = SentenceTransformer(self.embedding_model_name)

        self.model = None
        self.classes = []

        self.model_path = Path(model_path) if model_path else BASE_DIR / "model_chatbot.keras"
        self.classes_path = Path(classes_path) if classes_path else BASE_DIR / "classes.pkl"

    def normalize_text(self, text: str) -> str:
        text = str(text).strip().lower()
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
        text = re.sub(r"[^\w\s?/-]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def prepare_training_data(self):
        if not self.intents_file.exists():
            raise FileNotFoundError(f"Arquivo de intents não encontrado: {self.intents_file}")

        with open(self.intents_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        intents = data.get("intents")
        if not isinstance(intents, list):
            raise ValueError("O arquivo intents.json não possui a chave 'intents' em formato válido.")

        texts = []
        labels = []
        seen = set()

        ignored_patterns = {
            "sim", "nao", "não", "ok", "certo", "beleza"
        }

        for intent in intents:
            tag = intent.get("tag")
            patterns = intent.get("patterns", [])

            if not tag or not isinstance(patterns, list):
                logger.warning("Intent inválida ignorada: %s", intent)
                continue

            for pattern in patterns:
                normalized = self.normalize_text(pattern)

                if not normalized or normalized in ignored_patterns:
                    continue

                pair = (normalized, tag)
                if pair in seen:
                    continue
                seen.add(pair)

                texts.append(normalized)
                labels.append(tag)

        if not texts:
            raise ValueError("Nenhum dado de treinamento válido foi encontrado no intents.json.")

        class_counts = Counter(labels)

        valid_classes = {
            label for label, count in class_counts.items()
            if count >= MIN_EXAMPLES_PER_CLASS
        }
        removed_classes = {
            label: count for label, count in class_counts.items()
            if count < MIN_EXAMPLES_PER_CLASS
        }

        if removed_classes:
            logger.warning("Classes removidas por terem menos de %d exemplos: %s", MIN_EXAMPLES_PER_CLASS, removed_classes)

        filtered_texts = []
        filtered_labels = []

        for text, label in zip(texts, labels):
            if label in valid_classes:
                filtered_texts.append(text)
                filtered_labels.append(label)

        texts = filtered_texts
        labels = filtered_labels

        if not texts:
            raise ValueError("Após filtrar classes fracas, não restaram dados suficientes.")

        self.classes = sorted(set(labels))
        class_to_index = {tag: i for i, tag in enumerate(self.classes)}

        logger.info("Gerando embeddings com modelo: %s", self.embedding_model_name)
        X = self.embedding_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True
        ).astype(np.float32)

        y = np.array([class_to_index[tag] for tag in labels], dtype=np.int32)

        logger.info("Total de exemplos válidos: %d", len(texts))
        logger.info("Total de classes válidas: %d", len(self.classes))
        logger.info("Distribuição das classes: %s", dict(Counter(labels)))

        return X, y

    def build_model(self, input_size: int, output_size: int):
        model = Sequential([
            Input(shape=(input_size,)),
            Dense(256, activation="relu"),
            Dropout(0.4),
            Dense(128, activation="relu"),
            Dropout(0.3),
            Dense(output_size, activation="softmax")
        ])

        model.compile(
            optimizer=Adam(learning_rate=1e-3),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"]
        )

        model.summary()
        return model

    def train(self, epochs=125, batch_size=16, test_size=0.4):
        X, y = self.prepare_training_data()

        if len(np.unique(y)) < 2:
            raise ValueError("É necessário ter pelo menos 2 classes válidas para treinar o modelo.")

        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=test_size,
            random_state=42,
            stratify=y
        )

        logger.info("Treino: %d amostras | Validação: %d amostras", len(X_train), len(X_val))

        self.model = self.build_model(X.shape[1], len(self.classes))

        classes_unique = np.unique(y_train)
        weights = compute_class_weight(
            class_weight="balanced",
            classes=classes_unique,
            y=y_train
        )
        class_weight = {int(c): float(w) for c, w in zip(classes_unique, weights)}

        checkpoint = ModelCheckpoint(
            filepath=str(self.model_path),
            monitor="val_loss",
            mode="min",
            save_best_only=True,
            verbose=1
        )

        early_stop = EarlyStopping(
            monitor="val_loss",
            mode="min",
            patience=20,
            restore_best_weights=True,
            verbose=1
        )

        reduce_lr = ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=20,
            min_lr=1e-6,
            verbose=1
        )

        history = self.model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            verbose=1,
            callbacks=[checkpoint, early_stop, reduce_lr],
            class_weight=class_weight
        )

        if self.model_path.exists():
            self.model = load_model(str(self.model_path), compile=False)
            self.model.compile(
                optimizer=Adam(learning_rate=1e-3),
                loss="sparse_categorical_crossentropy",
                metrics=["accuracy"]
            )

        y_pred_probs = self.model.predict(X_val, verbose=0)
        y_pred = np.argmax(y_pred_probs, axis=1)

        report = classification_report(
            y_val,
            y_pred,
            labels=list(range(len(self.classes))),
            target_names=self.classes,
            zero_division=0
        )
        logger.info("Relatório de classificação:\n%s", report)

        metadata = {
            "classes": self.classes,
            "num_classes": len(self.classes),
            "embedding_model_name": self.embedding_model_name,
            "input_dim": int(X.shape[1]),
            "recommended_error_threshold": 0.45,
            "recommended_high_confidence_threshold": 0.75
        }

        with open(self.classes_path, "wb") as f:
            pickle.dump(metadata, f)

        logger.info("Modelo salvo em: %s", self.model_path)
        logger.info("Classes salvas em: %s", self.classes_path)
        logger.info("Treinamento concluído com sucesso.")

        return history

    def load_trained_model(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {self.model_path}")

        if not self.classes_path.exists():
            raise FileNotFoundError(f"Arquivo classes não encontrado: {self.classes_path}")

        self.model = load_model(str(self.model_path), compile=False)
        self.model.compile(
            optimizer=Adam(learning_rate=1e-3),
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"]
        )

        with open(self.classes_path, "rb") as f:
            metadata = pickle.load(f)

        if isinstance(metadata, dict) and "classes" in metadata:
            self.classes = metadata["classes"]
        else:
            self.classes = metadata

        logger.info("Modelo e classes carregados com sucesso.")

    def predict_intent(self, sentence, top_n=3, threshold=0.75):
        if self.model is None:
            raise RuntimeError("Modelo ainda não foi treinado ou carregado.")

        sentence = self.normalize_text(sentence)
        if not sentence:
            return [("sem_entendimento", 0.0)]

        vec = self.embedding_model.encode(
            [sentence],
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype(np.float32)

        probs = self.model.predict(vec, verbose=0)[0]
        indices = probs.argsort()[::-1][:top_n]

        results = [(self.classes[i], float(probs[i])) for i in indices]
        filtered = [item for item in results if item[1] >= threshold]

        if not filtered:
            return [("sem_entendimento", float(results[0][1]))]

        return filtered


if __name__ == "__main__":
    np.random.seed(42)
    tf.random.set_seed(42)

    trainer = ChatBotTrainer()
    trainer.train(epochs=100, batch_size=16)