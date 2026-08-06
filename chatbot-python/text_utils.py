import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalização única, compartilhada pelo treino e pela execução."""
    normalized = unicodedata.normalize("NFKC", str(text)).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def load_embedding_model(model_name: str):
    """Usa primeiro o cache local e baixa o modelo apenas quando necessário."""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from sentence_transformers import SentenceTransformer

    repository_id = (
        model_name if "/" in model_name else f"sentence-transformers/{model_name}"
    )
    try:
        cached_path = snapshot_download(repository_id, local_files_only=True)
        return SentenceTransformer(str(cached_path), local_files_only=True)
    except (LocalEntryNotFoundError, OSError, ValueError):
        return SentenceTransformer(model_name)
