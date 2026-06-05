print("ARQUIVO TESTE_VIDEO ATUALIZADO RODANDO", flush=True)

import cv2
import os
import sys

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
)

from detector_yolo_queda import DetectorYOLOQueda

# =====================================
# CONFIGURAÇÃO
# =====================================

#VIDEO_PATH = r"C:\TCC_NODE\camera\testes\videos\Fall\Raw_Video\20240912_101331.mp4"
VIDEO_PATH = r"C:\TCC_NODE\camera\testes\videos\No_Fall\Raw_Video\B_D_0002.mp4"
MAX_LARGURA = 1280
MAX_ALTURA = 720

# =====================================
# CARREGAR MODELO
# =====================================

print("\nCarregando modelo...", flush=True)

detector = DetectorYOLOQueda()

print("Modelo carregado com sucesso!", flush=True)

# =====================================
# ABRIR VÍDEO
# =====================================

print("\n====================================", flush=True)
print("ABRINDO VÍDEO", flush=True)
print("====================================", flush=True)
print("Arquivo:", VIDEO_PATH, flush=True)

cap = cv2.VideoCapture(VIDEO_PATH)

if not cap.isOpened():
    print("\nERRO: Não foi possível abrir o vídeo.", flush=True)
    print("Verifique o caminho:", flush=True)
    print(VIDEO_PATH, flush=True)
    exit()

fps = cap.get(cv2.CAP_PROP_FPS)
delay = int(1000 / fps) if fps > 0 else 33

largura_original = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
altura_original = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print("\nVídeo aberto com sucesso!", flush=True)
print(f"Resolução: {largura_original}x{altura_original}", flush=True)
print(f"FPS: {fps:.2f}", flush=True)
print(f"Delay: {delay} ms", flush=True)
print(f"Total de Frames: {total_frames}", flush=True)

# =====================================
# JANELA
# =====================================

cv2.namedWindow("Teste YOLO - Video", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Teste YOLO - Video", 1280, 720)

# =====================================
# PROCESSAMENTO
# =====================================

frame_num = 0

frames_queda = 0
LIMITE_FRAMES_QUEDA = 3

while True:

    ret, frame = cap.read()

    if not ret:
        print("\nFim do vídeo.", flush=True)
        break

    frame_num += 1

    altura, largura = frame.shape[:2]

    escala = min(
        MAX_LARGURA / largura,
        MAX_ALTURA / altura,
        1.0
    )

    if escala < 1:

        nova_largura = int(largura * escala)
        nova_altura = int(altura * escala)

        frame = cv2.resize(
            frame,
            (nova_largura, nova_altura),
            interpolation=cv2.INTER_AREA
        )

    # =========================
    # DETECÇÃO
    # =========================

    queda, confianca, caixas = detector.detectar(frame)

    if queda:
        frames_queda += 1
    else:
        frames_queda = 0

    queda_confirmada = frames_queda >= LIMITE_FRAMES_QUEDA

    print(
        f"Frame {frame_num}/{total_frames} | "
        f"Queda: {queda} | "
        f"Confirmada: {queda_confirmada} | "
        f"Confiança: {confianca:.2f}",
        flush=True
    )

    # =========================
    # DESENHAR CAIXAS
    # =========================

    for x1, y1, x2, y2, conf in caixas:

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 0, 255),
            2
        )

        cv2.putText(
            frame,
            f"Fall {conf:.2f}",
            (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )

    # =========================
    # ALERTA DE QUEDA
    # =========================

    if queda_confirmada:

        cv2.putText(
            frame,
            "QUEDA CONFIRMADA",
            (50, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 0, 255),
            3
        )

    # =========================
    # INFORMAÇÕES
    # =========================

    cv2.putText(
        frame,
        f"Frame: {frame_num}/{total_frames}",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        f"Frames queda: {frames_queda}",
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.putText(
        frame,
        f"Conf: {confianca:.2f}",
        (20, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    cv2.imshow("Teste YOLO - Video", frame)

    tecla = cv2.waitKey(delay)

    if tecla == 27:
        print("\nVídeo interrompido pelo usuário.", flush=True)
        break