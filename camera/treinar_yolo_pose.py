import os
from pathlib import Path

import torch
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATASET_CONFIG = BASE_DIR / "datasets" / "falling" / "data.yaml"
BASE_MODEL = BASE_DIR / "yolov8n-pose.pt"


def selecionar_dispositivo():
    configurado = os.getenv("YOLO_DEVICE", "").strip()
    if configurado:
        return configurado
    return "0" if torch.cuda.is_available() else "cpu"


def localizar_checkpoint_retomada():
    configurado = os.getenv("YOLO_RESUME_CHECKPOINT", "").strip()
    if not configurado:
        return None

    checkpoint = Path(configurado).expanduser()
    if not checkpoint.is_absolute():
        checkpoint = PROJECT_DIR / checkpoint
    checkpoint = checkpoint.resolve()

    if not checkpoint.exists():
        raise FileNotFoundError(
            f"Checkpoint para retomada não encontrado: {checkpoint}"
        )
    return checkpoint


def adaptar_checkpoint_cpu_para_cuda(checkpoint, dispositivo):
    if str(dispositivo).lower() == "cpu" or not torch.cuda.is_available():
        return checkpoint

    estado = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if estado.get("scaler") != {}:
        return checkpoint

    # Checkpoints salvos em CPU possuem GradScaler vazio. Ao retomar com AMP
    # na GPU, o Ultralytics espera um scaler inicializável. Mantemos o arquivo
    # original intacto e removemos apenas esse estado vazio na cópia de GPU.
    estado["scaler"] = None
    checkpoint_gpu = checkpoint.with_name(
        f"{checkpoint.stem}-gpu{checkpoint.suffix}"
    )
    torch.save(estado, checkpoint_gpu)
    print(f"Checkpoint adaptado para retomada CUDA: {checkpoint_gpu}")
    return checkpoint_gpu


def treinar():
    if not DATASET_CONFIG.exists():
        raise FileNotFoundError(f"Configuração do dataset não encontrada: {DATASET_CONFIG}")

    dispositivo = selecionar_dispositivo()
    checkpoint = localizar_checkpoint_retomada()

    if checkpoint:
        checkpoint = adaptar_checkpoint_cpu_para_cuda(
            checkpoint, dispositivo
        )
        print(f"Retomando treinamento de: {checkpoint}")
        print(f"Dispositivo selecionado: {dispositivo}")
        model = YOLO(str(checkpoint))
        return model.train(resume=True, device=dispositivo)

    if not BASE_MODEL.exists():
        raise FileNotFoundError(f"Modelo base não encontrado: {BASE_MODEL}")

    print(f"Iniciando novo treinamento no dispositivo: {dispositivo}")
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
        device=dispositivo,
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
