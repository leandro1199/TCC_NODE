import os
from pathlib import Path

from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATASET_CONFIG = BASE_DIR / "datasets" / "falling" / "data.yaml"
BASE_MODEL = BASE_DIR / "yolov8n-pose.pt"


def treinar():
    if not DATASET_CONFIG.exists():
        raise FileNotFoundError(f"Configuração do dataset não encontrada: {DATASET_CONFIG}")
    if not BASE_MODEL.exists():
        raise FileNotFoundError(f"Modelo base não encontrado: {BASE_MODEL}")

    model = YOLO(str(BASE_MODEL))
    return model.train(
        task="pose",
        data=str(DATASET_CONFIG),
        epochs=int(os.getenv("YOLO_EPOCHS", "100")),
        patience=int(os.getenv("YOLO_PATIENCE", "25")),
        imgsz=int(os.getenv("YOLO_IMAGE_SIZE", "640")),
        batch=int(os.getenv("YOLO_BATCH_SIZE", "8")),
        project=str(PROJECT_DIR / "runs" / "pose"),
        name=os.getenv("YOLO_RUN_NAME", "fall_pose_v2"),
        exist_ok=True,
        pretrained=True,
        optimizer="auto",
        degrees=12.0,
        translate=0.15,
        scale=0.50,
        fliplr=0.50,
        mosaic=0.75,
        close_mosaic=10,
        seed=42,
        deterministic=True,
    )


if __name__ == "__main__":
    treinar()
