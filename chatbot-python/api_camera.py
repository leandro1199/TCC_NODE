import cv2
import time
import mysql.connector
from flask import Flask, Response, jsonify

app = Flask(__name__)

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "1011",
    "database": "chatbot_db",
    "port": 3308
}


def buscar_camera(camera_id):
    conexao = mysql.connector.connect(**DB_CONFIG)
    cursor = conexao.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, nome, rtsp_url FROM cameras WHERE id = %s",
        (camera_id,)
    )

    camera = cursor.fetchone()

    cursor.close()
    conexao.close()

    return camera


def abrir_camera(rtsp_url):
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        print("Não foi possível abrir a câmera:", rtsp_url)

    return cap


def gerar_frames(camera_id):
    dados_camera = buscar_camera(camera_id)

    if not dados_camera:
        print("Câmera não encontrada no banco.")
        return

    rtsp_url = dados_camera["rtsp_url"]
    print("Abrindo câmera:", dados_camera["nome"])
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


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "mensagem": "API da câmera funcionando"
    })


@app.route("/video_feed/<int:camera_id>")
def video_feed(camera_id):
    return Response(
        gerar_frames(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status_camera/<int:camera_id>")
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
        "nome": dados_camera["nome"],
        "online": online
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=False)