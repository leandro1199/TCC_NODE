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

#imagem = cv2.imread("imagens/queda1.jpg")
imagem = cv2.imread("imagens/queda4.jpg")

if imagem is None:
    print("Imagem não encontrada")
    exit()

# ================= LIMITAR RESOLUÇÃO =================

altura, largura = imagem.shape[:2]

MAX_LARGURA = 1280
MAX_ALTURA = 720

escala = min(
    MAX_LARGURA / largura,
    MAX_ALTURA / altura,
    1.0
)

if escala < 1:
    nova_largura = int(largura * escala)
    nova_altura = int(altura * escala)

    imagem = cv2.resize(
        imagem,
        (nova_largura, nova_altura),
        interpolation=cv2.INTER_AREA
    )

# ================= DETECÇÃO =================

queda, confianca, caixas = detector.detectar(imagem)

print("Queda:", queda)
print("Confianca:", confianca)
print("Caixas:", caixas)

# ================= DESENHAR RESULTADOS =================

for x1, y1, x2, y2, conf in caixas:

    cv2.rectangle(
        imagem,
        (x1, y1),
        (x2, y2),
        (0, 0, 255),
        3
    )

    cv2.putText(
        imagem,
        f"Fall {conf:.2f}",
        (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2
    )

# ================= EXIBIR =================

cv2.imshow("Resultado YOLO", imagem)

cv2.waitKey(0)
cv2.destroyAllWindows()