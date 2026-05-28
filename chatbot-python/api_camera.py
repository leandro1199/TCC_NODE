import cv2
import time

from flask import Flask, Response, jsonify
from flask_cors import CORS

import firebase_admin
from firebase_admin import credentials, firestore


app = Flask(__name__)
CORS(app)


# ================= FIREBASE =================

cred = credentials.Certificate("firebase-key.json")

firebase_admin.initialize_app(cred)

db = firestore.client()


# ================= BUSCAR CÂMERA =================

def buscar_camera(camera_id):

    doc_ref = db.collection("cameras").document(str(camera_id))

    doc = doc_ref.get()

    if not doc.exists:
        return None

    camera = doc.to_dict()
    camera["id"] = doc.id

    return camera


# ================= ABRIR CÂMERA =================

def abrir_camera(rtsp_url):

    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Não foi possível abrir a câmera:", rtsp_url)

    return cap


# ================= GERAR FRAMES =================

def gerar_frames(camera_id):

    dados_camera = buscar_camera(camera_id)

    if not dados_camera:
        print("Câmera não encontrada no Firebase.")
        return

    rtsp_url = dados_camera["rtsp_url"]

    print("Abrindo câmera:", dados_camera.get("nome", "Sem nome"))
    print("RTSP:", rtsp_url)

    cap = abrir_camera(rtsp_url)

    while True:

        sucesso, frame = cap.read()

        if not sucesso or frame is None:

            print("Falha ao ler frame. Tentando reconectar...")

            cap.release()

            time.sleep(2)

            cap = abrir_camera(rtsp_url)

            continue

        frame = cv2.resize(frame, (800, 450))

        ok, buffer = cv2.imencode(".jpg", frame)

        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() +
            b"\r\n"
        )


# ================= ROTAS =================

@app.route("/")
def home():

    return jsonify({
        "status": "online",
        "mensagem": "API da câmera funcionando com Firebase"
    })


@app.route("/video_feed/<camera_id>")
def video_feed(camera_id):

    return Response(
        gerar_frames(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status_camera/<camera_id>")
def status_camera(camera_id):

    dados_camera = buscar_camera(camera_id)

    if not dados_camera:

        return jsonify({
            "online": False,
            "erro": "Câmera não encontrada"
        }), 404

    cap = abrir_camera(dados_camera["rtsp_url"])

    online = cap.isOpened()

    cap.release()

    return jsonify({
        "camera_id": dados_camera["id"],
        "nome": dados_camera.get("nome", "Sem nome"),
        "online": online
    })


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5002,
        debug=False
    )