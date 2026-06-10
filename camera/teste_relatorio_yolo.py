import cv2
import base64
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

from detector_yolo_queda import DetectorYOLOQueda


cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

detector = DetectorYOLOQueda()


def salvar_relatorio_queda(frame, camera_id, camera_nome, confianca):
    _, buffer = cv2.imencode(".jpg", frame)
    imagem_base64 = base64.b64encode(buffer).decode("utf-8")

    agora = datetime.now()

    db.collection("relatorios_queda").add({
        "cameraId": str(camera_id),
        "cameraNome": camera_nome,
        "confianca": round(float(confianca) * 100, 2),
        "data": agora.strftime("%d/%m/%Y"),
        "hora": agora.strftime("%H:%M:%S"),
        "dataHora": agora.strftime("%d/%m/%Y %H:%M:%S"),
        "imagem": imagem_base64,
        "criadoEm": firestore.SERVER_TIMESTAMP
    })


imagem_teste = r"C:\TCC_NODE\camera\testes\imagens\queda1.jpg"

frame = cv2.imread(imagem_teste)

if frame is None:
    print("Imagem não encontrada.")
    exit()

queda, confianca, caixas = detector.detectar(frame)

print("Queda detectada:", queda)
print("Confiança:", confianca)

if queda:
    salvar_relatorio_queda(
        frame,
        camera_id="teste",
        camera_nome="Câmera de Teste",
        confianca=confianca
    )

    print("Relatório criado no Firebase.")
else:
    print("Nenhuma queda detectada. Relatório não criado.")