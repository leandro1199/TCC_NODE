from ultralytics import YOLO

model = YOLO("yolov8n-pose.pt")

model.train(
    data="datasets/falling/data.yaml",
    epochs=50,
    imgsz=640,
    batch=8
)