import cv2
import sys
import os

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)

from detector_yolo_queda import DetectorYOLOQueda

detector = DetectorYOLOQueda()

imagem = cv2.imread("imagens/queda1.jpg")

queda, confianca = detector.detectar(imagem)

print("Queda:", queda)
print("Confianca:", confianca)