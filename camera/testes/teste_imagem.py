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

# Redimensiona a imagem para exibição
altura, largura = imagem_resultado.shape[:2]

nova_largura = 900
nova_altura = int((nova_largura / largura) * altura)

imagem_resultado = cv2.resize(
    imagem_resultado,
    (nova_largura, nova_altura)
)

# Janela redimensionável
cv2.namedWindow("Resultado", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Resultado", 900, 600)

cv2.imshow("Resultado", imagem_resultado)

cv2.waitKey(0)
cv2.destroyAllWindows()