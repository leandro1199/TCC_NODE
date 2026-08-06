import os
import shutil
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np

from flask import Flask, Response, jsonify
from flask_cors import CORS

import firebase_admin
from firebase_admin import credentials, firestore

from detector_yolo_queda import DetectorYOLOQueda


app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


# ================= FIREBASE =================

firebase_key_path = Path(
    os.getenv("FIREBASE_KEY_PATH", PROJECT_DIR / "json" / "firebase.json")
)
if not firebase_key_path.exists():
    raise FileNotFoundError(
        "Credencial do Firebase não encontrada. Defina FIREBASE_KEY_PATH ou "
        f"adicione o arquivo em {firebase_key_path}."
    )

if not firebase_admin._apps:
    cred = credentials.Certificate(str(firebase_key_path))
    firebase_admin.initialize_app(cred)
db = firestore.client()


# ================= YOLO =================

detector_queda = DetectorYOLOQueda()


# ================= FFMPEG =================

def localizar_ffmpeg():
    configured_path = os.getenv("FFMPEG_PATH")
    if configured_path:
        return configured_path

    path_command = shutil.which("ffmpeg")
    if path_command:
        return path_command

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        candidates = sorted(
            packages_dir.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"),
            reverse=True,
        )
        if candidates:
            return str(candidates[0])

    return None


FFMPEG_PATH = localizar_ffmpeg()


def obter_ffmpeg():
    if not FFMPEG_PATH:
        raise FileNotFoundError(
            "FFmpeg não encontrado. Instale-o no PATH ou defina FFMPEG_PATH."
        )
    return FFMPEG_PATH


# ================= BUSCAR CÂMERA =================

def buscar_camera(camera_id):
    doc_ref = db.collection("cameras").document(str(camera_id))
    doc = doc_ref.get()

    if not doc.exists:
        return None

    camera = doc.to_dict()
    camera["id"] = doc.id

    return camera


# ================= VERIFICAR QUEDA COM YOLO =================

def verificar_queda(frame, camera_id, ultimo_alerta):
    queda, confianca, caixas = detector_queda.detectar(
        frame, stream_id=str(camera_id)
    )

    for x1, y1, x2, y2, conf in caixas:
        cor = (0, 0, 255) if queda else (0, 165, 255)
        rotulo = "Queda" if queda else "Postura horizontal"
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            cor,
            3
        )

        cv2.putText(
            frame,
            f"{rotulo} {conf:.2f}",
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            cor,
            2
        )

    if queda:
        cv2.putText(
            frame,
            f"QUEDA DETECTADA! {confianca:.2f}",
            (40, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 0, 255),
            3
        )

        if time.time() - ultimo_alerta > 60:
            db.collection("cameras").document(str(camera_id)).update({
                "queda": True,
                "alerta": "Queda detectada pela IA",
                "confianca_queda": confianca,
                "ultima_queda": firestore.SERVER_TIMESTAMP
            })

            ultimo_alerta = time.time()

    else:
        cv2.putText(
            frame,
            "Sem queda",
            (40, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

    return frame, ultimo_alerta


# ================= GERAR FRAMES =================

def gerar_frames(camera_id):
    dados_camera = buscar_camera(camera_id)

    if not dados_camera:
        print("Câmera não encontrada no Firebase.")
        return

    rtsp_url = dados_camera.get("rtsp_url")
    if not rtsp_url:
        print("A câmera não possui uma URL RTSP configurada.")
        return

    ultimo_alerta = 0

    print("Abrindo câmera:", dados_camera.get("nome", "Sem nome"))
    print("RTSP:", rtsp_url)

    try:
        ffmpeg_path = obter_ffmpeg()
    except FileNotFoundError as erro:
        print(erro)
        return

    while True:
        comando = [
            ffmpeg_path,
            "-nostdin",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-vf", "scale=800:450",
            "-f", "mjpeg",
            "-q:v", "5",
            "-"
        ]

        processo = None
        buffer = b""

        try:
            processo = subprocess.Popen(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10**6,
            )
            if processo.stdout is None:
                raise RuntimeError("O FFmpeg não disponibilizou o fluxo de vídeo.")

            while True:
                bloco = processo.stdout.read(4096)

                if not bloco:
                    break

                buffer += bloco

                if len(buffer) > 2 * 1024 * 1024:
                    inicio_jpeg = buffer.rfind(b"\xff\xd8")
                    buffer = buffer[inicio_jpeg:] if inicio_jpeg >= 0 else buffer[-2:]

                inicio = buffer.find(b"\xff\xd8")
                fim = buffer.find(b"\xff\xd9", inicio + 2)

                if inicio != -1 and fim != -1 and fim > inicio:
                    jpg = buffer[inicio:fim + 2]
                    buffer = buffer[fim + 2:]

                    array = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)

                    if frame is not None:
                        frame, ultimo_alerta = verificar_queda(
                            frame,
                            camera_id,
                            ultimo_alerta
                        )

                        codificado, jpg_codificado = cv2.imencode(".jpg", frame)
                        if not codificado:
                            continue
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
            if processo is not None and processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    processo.kill()
            detector_queda.reset_stream(camera_id)

        print("Reconectando câmera em 2 segundos...")
        time.sleep(2)


# ================= ROTAS =================

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "mensagem": "API da câmera funcionando",
        "componentes": {
            "firebase": "online",
            "yolo": "online",
            "ffmpeg": "configurado" if FFMPEG_PATH else "não encontrado",
        },
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

    rtsp_url = dados_camera.get("rtsp_url")
    if not rtsp_url:
        return jsonify({
            "camera_id": dados_camera["id"],
            "online": False,
            "erro": "URL RTSP não configurada",
        }), 400

    try:
        ffmpeg_path = obter_ffmpeg()
    except FileNotFoundError as erro:
        return jsonify({"online": False, "erro": str(erro)}), 503

    comando = [
        ffmpeg_path,
        "-nostdin",
        "-loglevel", "error",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-t", "3",
        "-f", "null",
        "-"
    ]

    try:
        processo = subprocess.run(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        online = processo.returncode == 0
    except subprocess.TimeoutExpired:
        online = False

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
