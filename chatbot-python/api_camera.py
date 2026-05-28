import time
import subprocess

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


# ================= FFMPEG =================

FFMPEG_PATH = r"C:\Users\berna\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe"


# ================= BUSCAR CÂMERA =================

def buscar_camera(camera_id):

    doc_ref = db.collection("cameras").document(str(camera_id))

    doc = doc_ref.get()

    if not doc.exists:
        return None

    camera = doc.to_dict()
    camera["id"] = doc.id

    return camera


# ================= GERAR FRAMES =================

def gerar_frames(camera_id):

    dados_camera = buscar_camera(camera_id)

    if not dados_camera:
        print("Câmera não encontrada no Firebase.")
        return

    rtsp_url = dados_camera["rtsp_url"]

    print("Abrindo câmera:", dados_camera.get("nome", "Sem nome"))
    print("RTSP:", rtsp_url)

    while True:

        comando = [
            FFMPEG_PATH,
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-vf", "scale=800:450",
            "-f", "mjpeg",
            "-q:v", "5",
            "-"
        ]

        processo = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**8
        )

        buffer = b""

        try:

            while True:

                bloco = processo.stdout.read(4096)

                if not bloco:
                    break

                buffer += bloco

                inicio = buffer.find(b"\xff\xd8")
                fim = buffer.find(b"\xff\xd9")

                if inicio != -1 and fim != -1 and fim > inicio:

                    jpg = buffer[inicio:fim + 2]
                    buffer = buffer[fim + 2:]

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" +
                        jpg +
                        b"\r\n"
                    )

        except Exception as erro:

            print("Erro no streaming:", erro)

        finally:

            processo.kill()

        print("Reconectando câmera em 2 segundos...")
        time.sleep(2)


# ================= ROTAS =================

@app.route("/")
def home():

    return jsonify({
        "status": "online",
        "mensagem": "API da câmera funcionando com Firebase e FFmpeg"
    })


@app.route("/cameras")
def listar_cameras():

    docs = db.collection("cameras").stream()

    cameras = []

    for doc in docs:
        camera = doc.to_dict()
        camera["id"] = doc.id
        cameras.append(camera)

    return jsonify(cameras)


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

    rtsp_url = dados_camera["rtsp_url"]

    comando = [
        FFMPEG_PATH,
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-t", "3",
        "-f", "null",
        "-"
    ]

    processo = subprocess.run(
        comando,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    online = processo.returncode == 0

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