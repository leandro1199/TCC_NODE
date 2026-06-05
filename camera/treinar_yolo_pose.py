from ultralytics import YOLO

model = YOLO("yolov8n-cls.pt")

model.train(
    data="dataset_video",
    epochs=50,
    imgsz=224,
    batch=16,
    project="runs/classify",
    name="fall_classification",
    exist_ok=True
)