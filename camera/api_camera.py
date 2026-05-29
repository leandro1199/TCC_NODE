import time
import subprocess
import cv2
import numpy as np
import mediapipe as mp

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


# ================= MEDIAPIPE =================

mp_pose = mp.solutions.pose
mp_draw = mp.solutions.drawing_utils


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


# ================= VERIFICAR QUEDA =================

def verificar_queda(frame, pose, camera_id, ultimo_alerta):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    resultado = pose.process(rgb)

    queda = False

    if resultado.pose_landmarks:
        pontos = resultado.pose_landmarks.landmark

        ombro = pontos[mp_pose.PoseLandmark.LEFT_SHOULDER]
        quadril = pontos[mp_pose.PoseLandmark.LEFT_HIP]

        diferenca_y = abs(ombro.y - quadril.y)
        diferenca_x = abs(ombro.x - quadril.x)

        if diferenca_x > diferenca_y:
            queda = True

        mp_draw.draw_landmarks(
            frame,
            resultado.pose_landmarks,
            mp_pose.POSE_CONNECTIONS
        )

    if queda:
        cv2.putText(
            frame,
            "QUEDA DETECTADA!",
            (40, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3
        )

        if time.time() - ultimo_alerta > 10:
            db.collection("cameras").document(str(camera_id)).update({
                "queda": True,
                "alerta": "Queda detectada",
                "ultima_queda": firestore.SERVER_TIMESTAMP
            })

            ultimo_alerta = time.time()

    return frame, ultimo_alerta


# ================= GERAR FRAMES =================

def gerar_frames(camera_id):
    dados_camera = buscar_camera(camera_id)

    if not dados_camera:
        print("Câmera não encontrada no Firebase.")
        return

    rtsp_url = dados_camera["rtsp_url"]

    pose = mp_pose.Pose()
    ultimo_alerta = 0

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
            stderr=None,
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

                    array = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)

                    if frame is not None:
                        frame, ultimo_alerta = verificar_queda(
                            frame,
                            pose,
                            camera_id,
                            ultimo_alerta
                        )

                        _, jpg_codificado = cv2.imencode(".jpg", frame)
                        jpg = jpg_codificado.tobytes()

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
        "mensagem": "API da câmera funcionando com Firebase, FFmpeg e detector de queda"
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