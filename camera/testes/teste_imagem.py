import cv2
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from detectar_queda import DetectorQueda


detector = DetectorQueda()

caminho_imagem = "imagens/queda1.jpg"

imagem = cv2.imread(caminho_imagem)

if imagem is None:
    print("Imagem nao encontrada:", caminho_imagem)
    exit()

queda, mensagem, imagem_resultado = detector.analisar_imagem(imagem)

print("Queda:", queda)
print("Mensagem:", mensagem)

cv2.imshow("Resultado", imagem_resultado)
cv2.waitKey(0)
cv2.destroyAllWindows()