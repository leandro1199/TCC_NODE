import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import cv2
import numpy as np

from flask import Flask, Response, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

import firebase_admin
from firebase_admin import credentials, firestore

from detector_yolo_queda import DetectorYOLOQueda
from alerta_queda import EventoQueda, ServicoAlertaQueda


app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

# Reaproveita as configurações do backend no teste local. Variáveis definidas
# no sistema operacional continuam tendo prioridade.
load_dotenv(PROJECT_DIR / "backend-node" / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

CAMERA_MODE = os.getenv("CAMERA_MODE", "offline").strip().lower()
OFFLINE_MODE = CAMERA_MODE == "offline"
OFFLINE_CAMERA_SOURCE = os.getenv("CAMERA_OFFLINE_SOURCE", "0").strip()
RTSP_BACKEND = os.getenv("CAMERA_RTSP_BACKEND", "auto").strip().lower()
ALERT_COOLDOWN_SECONDS = max(
    10,
    int(os.getenv("ALERT_COOLDOWN_SECONDS", "60")),
)


# ================= FIREBASE =================

db = None
if not OFFLINE_MODE:
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
servico_alerta = ServicoAlertaQueda()
executor_alertas = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alerta-queda")


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


def localizar_vlc():
    configured_path = os.getenv("VLC_PATH")
    if configured_path:
        return configured_path

    path_command = shutil.which("vlc")
    if path_command:
        return path_command

    candidates = (
        Path(os.getenv("ProgramFiles", "C:/Program Files"))
        / "VideoLAN" / "VLC" / "vlc.exe",
        Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "VideoLAN" / "VLC" / "vlc.exe",
    )
    return str(next((path for path in candidates if path.exists()), "")) or None


VLC_PATH = localizar_vlc()


def obter_ffmpeg():
    if not FFMPEG_PATH:
        raise FileNotFoundError(
            "FFmpeg não encontrado. Instale-o no PATH ou defina FFMPEG_PATH."
        )
    return FFMPEG_PATH


def obter_vlc():
    if not VLC_PATH:
        raise FileNotFoundError(
            "VLC não encontrado. Instale-o ou defina a variável VLC_PATH."
        )
    return VLC_PATH


# ================= BUSCAR CÂMERA =================

def buscar_camera(camera_id):
    if db is None:
        return None

    doc_ref = db.collection("cameras").document(str(camera_id))
    doc = doc_ref.get()

    if not doc.exists:
        return None

    camera = doc.to_dict()
    camera["id"] = doc.id

    return camera


# ================= RELATÓRIO E NOTIFICAÇÕES =================

def nome_da_camera(camera_id):
    if db is not None:
        try:
            camera = buscar_camera(camera_id)
            if camera:
                return camera.get("nome") or f"Câmera {camera_id}"
        except Exception as erro:
            print(f"Não foi possível obter o nome da câmera: {erro}", flush=True)
    return os.getenv("CAMERA_OFFLINE_NAME", "Câmera local").strip() or "Câmera local"


def registrar_e_notificar_queda(evento):
    documento = None

    if db is not None:
        try:
            dados = evento.para_firestore()
            dados["criadoEm"] = firestore.SERVER_TIMESTAMP
            _, documento = db.collection("relatorios_queda").add(dados)
        except Exception as erro:
            print(f"Falha ao salvar o relatório da queda: {erro}", flush=True)

    resultados = servico_alerta.enviar(evento)

    if documento is not None:
        try:
            documento.update({
                "notificacoes": resultados,
                "notificadoEm": firestore.SERVER_TIMESTAMP,
            })
        except Exception as erro:
            print(f"Falha ao atualizar o status das notificações: {erro}", flush=True)

    resumo = ", ".join(
        f"{canal}={resultado.get('status', 'desconhecido')}"
        for canal, resultado in resultados.items()
    )
    print(f"Alerta de queda processado: {resumo}", flush=True)


def agendar_alerta_queda(frame, camera_id, confianca):
    try:
        evento = EventoQueda.criar(
            frame.copy(),
            camera_id=str(camera_id),
            camera_nome=nome_da_camera(camera_id),
            confianca=confianca,
        )
        executor_alertas.submit(registrar_e_notificar_queda, evento)
    except Exception as erro:
        print(f"Falha ao preparar o alerta de queda: {erro}", flush=True)


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

        if time.time() - ultimo_alerta > ALERT_COOLDOWN_SECONDS:
            if db is not None:
                try:
                    db.collection("cameras").document(str(camera_id)).update({
                        "queda": True,
                        "alerta": "Queda detectada pela IA",
                        "confianca_queda": confianca,
                        "ultima_queda": firestore.SERVER_TIMESTAMP
                    })
                except Exception as erro:
                    print(f"Falha ao atualizar o estado da câmera: {erro}", flush=True)

            agendar_alerta_queda(frame, camera_id, confianca)
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


# ================= CÂMERA OFFLINE =================

def obter_fonte_offline():
    """Converte "0" em webcam local e preserva URLs/caminhos como texto."""
    return (
        int(OFFLINE_CAMERA_SOURCE)
        if OFFLINE_CAMERA_SOURCE.lstrip("-").isdigit()
        else OFFLINE_CAMERA_SOURCE
    )


def fonte_rtsp(fonte):
    return isinstance(fonte, str) and fonte.lower().startswith(
        ("rtsp://", "rtsps://")
    )


def adicionar_credenciais_rtsp(fonte):
    partes = urlsplit(fonte)
    if partes.username:
        return fonte

    usuario = os.getenv("CAMERA_RTSP_USER", "").strip()
    senha = os.getenv("CAMERA_RTSP_PASSWORD", "")
    if not usuario:
        return fonte

    hostname = partes.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    porta = f":{partes.port}" if partes.port else ""
    autenticacao = quote(usuario, safe="")
    if senha:
        autenticacao += f":{quote(senha, safe='')}"
    netloc = f"{autenticacao}@{hostname}{porta}"
    return urlunsplit(
        (partes.scheme, netloc, partes.path, partes.query, partes.fragment)
    )


def descrever_fonte_offline():
    if OFFLINE_CAMERA_SOURCE.lstrip("-").isdigit():
        return f"webcam {OFFLINE_CAMERA_SOURCE}"
    if "://" in OFFLINE_CAMERA_SOURCE:
        protocolo = OFFLINE_CAMERA_SOURCE.split("://", 1)[0]
        return f"câmera {protocolo.upper()} configurada"
    return "arquivo ou dispositivo local configurado"


def abrir_captura_offline(fonte):
    if isinstance(fonte, int) and os.name == "nt":
        captura = cv2.VideoCapture(fonte, cv2.CAP_DSHOW)
        if captura.isOpened():
            return captura
        captura.release()
    return cv2.VideoCapture(fonte)


def usar_vlc_para_fonte(fonte):
    if not fonte_rtsp(fonte) or RTSP_BACKEND == "opencv":
        return False
    if RTSP_BACKEND == "vlc" and not VLC_PATH:
        obter_vlc()
    return bool(VLC_PATH)


def comando_vlc(fonte, tempo_execucao=None):
    comando = [
        obter_vlc(),
        "--no-one-instance",
        "-I", "dummy",
        "--dummy-quiet",
        "--no-audio",
        "--no-video-title-show",
        "--rtsp-tcp",
    ]
    if tempo_execucao is not None:
        comando.extend([
            f"--run-time={tempo_execucao}",
            "--play-and-exit",
        ])
    comando.extend([
        adicionar_credenciais_rtsp(fonte),
        "--sout=#transcode{vcodec=MJPG,vb=1200}:"
        "std{access=file,mux=raw,dst=-}",
    ])
    return comando


def testar_fonte_vlc(fonte):
    try:
        resultado = subprocess.run(
            comando_vlc(fonte, tempo_execucao=4),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return b"\xff\xd8" in resultado.stdout and b"\xff\xd9" in resultado.stdout


def resposta_mjpeg(frame):
    codificado, jpg = cv2.imencode(".jpg", frame)
    if not codificado:
        return None
    return (
        b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n" +
        jpg.tobytes() +
        b"\r\n"
    )


def frame_indisponivel(mensagem):
    frame = np.zeros((450, 800, 3), dtype=np.uint8)
    cv2.putText(
        frame,
        mensagem,
        (35, 225),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )
    return frame


def gerar_frames_vlc(fonte, stream_id):
    ultimo_alerta = 0

    while True:
        processo = None
        try:
            processo = subprocess.Popen(
                comando_vlc(fonte),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10**6,
            )
            if processo.stdout is None:
                raise RuntimeError("O VLC não disponibilizou o fluxo de vídeo.")

            buffer = b""
            while True:
                bloco = processo.stdout.read(4096)
                if not bloco:
                    break
                buffer += bloco

                if len(buffer) > 2 * 1024 * 1024:
                    inicio_jpeg = buffer.rfind(b"\xff\xd8")
                    buffer = (
                        buffer[inicio_jpeg:]
                        if inicio_jpeg >= 0
                        else buffer[-2:]
                    )

                while True:
                    inicio = buffer.find(b"\xff\xd8")
                    fim = buffer.find(b"\xff\xd9", inicio + 2)
                    if inicio == -1 or fim == -1 or fim <= inicio:
                        break

                    jpg = buffer[inicio:fim + 2]
                    buffer = buffer[fim + 2:]
                    array = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
                    if frame is None:
                        continue

                    frame, ultimo_alerta = verificar_queda(
                        frame,
                        stream_id,
                        ultimo_alerta,
                    )
                    resposta = resposta_mjpeg(frame)
                    if resposta:
                        yield resposta
        except GeneratorExit:
            return
        except Exception as erro:
            print(f"Erro no fluxo VLC: {erro}", flush=True)
        finally:
            if processo is not None and processo.poll() is None:
                processo.terminate()
                try:
                    processo.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    processo.kill()
            detector_queda.reset_stream(stream_id)

        print("Reconectando câmera pelo VLC em 2 segundos...", flush=True)
        time.sleep(2)


def gerar_frames_offline():
    fonte = obter_fonte_offline()
    stream_id = f"offline:{OFFLINE_CAMERA_SOURCE}"
    ultimo_alerta = 0

    print(f"Abrindo {descrever_fonte_offline()}", flush=True)

    if usar_vlc_para_fonte(fonte):
        yield from gerar_frames_vlc(fonte, stream_id)
        return

    while True:
        captura = abrir_captura_offline(fonte)

        if not captura.isOpened():
            resposta = resposta_mjpeg(
                frame_indisponivel("Camera offline - tentando reconectar...")
            )
            if resposta:
                yield resposta
            captura.release()
            time.sleep(2)
            continue

        try:
            while True:
                recebido, frame = captura.read()
                if not recebido or frame is None:
                    break

                altura, largura = frame.shape[:2]
                escala = min(800 / largura, 450 / altura, 1.0)
                if escala < 1.0:
                    frame = cv2.resize(
                        frame,
                        (int(largura * escala), int(altura * escala)),
                        interpolation=cv2.INTER_AREA,
                    )

                frame, ultimo_alerta = verificar_queda(
                    frame,
                    stream_id,
                    ultimo_alerta,
                )
                resposta = resposta_mjpeg(frame)
                if resposta:
                    yield resposta
        except GeneratorExit:
            return
        except Exception as erro:
            print(f"Erro na câmera offline: {erro}", flush=True)
        finally:
            captura.release()
            detector_queda.reset_stream(stream_id)

        print("Reconectando câmera offline em 2 segundos...", flush=True)
        time.sleep(2)


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
        "modo": CAMERA_MODE,
        "componentes": {
            "firebase": "desativado" if OFFLINE_MODE else "online",
            "yolo": "online",
            "ffmpeg": "configurado" if FFMPEG_PATH else "não encontrado",
            "vlc": "configurado" if VLC_PATH else "não encontrado",
            "camera_offline": descrever_fonte_offline(),
            "alertas": (
                "simulacao"
                if servico_alerta.habilitado and servico_alerta.simulacao
                else "online"
                if servico_alerta.habilitado
                else "desativado"
            ),
        },
    })


@app.route("/cameras")
def listar_cameras():
    if db is None:
        return jsonify({
            "erro": "Firebase desativado no modo offline",
            "camera_offline": descrever_fonte_offline(),
        }), 503

    docs = db.collection("cameras").stream()

    cameras = []

    for doc in docs:
        camera = doc.to_dict()
        camera["id"] = doc.id
        cameras.append(camera)

    return jsonify(cameras)


@app.route("/status_alertas")
def status_alertas():
    """Informa a prontidão dos canais sem expor destinatários ou segredos."""
    return jsonify(servico_alerta.status_configuracao())


@app.route("/video_feed/offline")
def video_feed_offline():
    return Response(
        gerar_frames_offline(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/status_camera/offline")
def status_camera_offline():
    fonte = obter_fonte_offline()
    if usar_vlc_para_fonte(fonte):
        online = testar_fonte_vlc(fonte)
        backend = "vlc"
    else:
        captura = abrir_captura_offline(fonte)
        try:
            online, frame = (
                captura.read() if captura.isOpened() else (False, None)
            )
            online = bool(online and frame is not None)
        finally:
            captura.release()
        backend = "opencv"

    return jsonify({
        "fonte": descrever_fonte_offline(),
        "online": bool(online),
        "modo": "offline",
        "backend": backend,
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
