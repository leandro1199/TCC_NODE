import argparse
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = "rtsp://192.168.1.5:554/onvif2"
WINDOW_NAME = "AI Health - Gravacao de teste"


def localizar_vlc():
    configurado = os.getenv("VLC_PATH", "").strip()
    if configurado:
        return configurado

    encontrado = shutil.which("vlc")
    if encontrado:
        return encontrado

    candidatos = (
        Path(os.getenv("ProgramFiles", "C:/Program Files"))
        / "VideoLAN" / "VLC" / "vlc.exe",
        Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "VideoLAN" / "VLC" / "vlc.exe",
    )
    return str(next((item for item in candidatos if item.exists()), ""))


def adicionar_credenciais(fonte):
    partes = urlsplit(fonte)
    if partes.username:
        return fonte

    usuario = os.getenv("CAMERA_RTSP_USER", "admin").strip()
    senha = os.getenv("CAMERA_RTSP_PASSWORD", "")
    if not senha:
        raise RuntimeError("Defina CAMERA_RTSP_PASSWORD antes de gravar.")

    hostname = partes.hostname or ""
    porta = f":{partes.port}" if partes.port else ""
    autenticacao = f"{quote(usuario, safe='')}:{quote(senha, safe='')}"
    return urlunsplit(
        (
            partes.scheme,
            f"{autenticacao}@{hostname}{porta}",
            partes.path,
            partes.query,
            partes.fragment,
        )
    )


def proximo_caminho(numero):
    pasta = BASE_DIR / "gravacoes"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"video_{numero}.mp4"
    if destino.exists():
        sufixo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = pasta / f"video_{numero}_{sufixo}.mp4"
    return destino


def porta_local_livre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.bind(("127.0.0.1", 0))
        return servidor.getsockname()[1]


def comando_vlc(fonte, porta):
    vlc = localizar_vlc()
    if not vlc:
        raise FileNotFoundError("VLC não encontrado no computador.")
    return [
        vlc,
        "--no-one-instance",
        "-I", "dummy",
        "--dummy-quiet",
        "--no-audio",
        "--no-video-title-show",
        "--rtsp-tcp",
        adicionar_credenciais(fonte),
        "--sout=#transcode{vcodec=MJPG,vb=1200}:"
        f"std{{access=http,mux=mpjpeg,dst=127.0.0.1:{porta}/camera.mjpg}}",
    ]


def conectar_preview(porta, limite=15):
    endereco = f"http://127.0.0.1:{porta}/camera.mjpg"
    prazo = time.monotonic() + limite

    while time.monotonic() < prazo:
        captura = cv2.VideoCapture(endereco)
        if captura.isOpened():
            captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            recebido, frame = captura.read()
            if recebido and frame is not None:
                return captura, frame
        captura.release()
        cv2.waitKey(100)

    raise RuntimeError("O VLC não disponibilizou a prévia da câmera.")


def texto_centralizado(frame, texto, escala, cor, espessura):
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    (largura, altura), _ = cv2.getTextSize(
        texto,
        fonte,
        escala,
        espessura,
    )
    x = max(20, (frame.shape[1] - largura) // 2)
    y = max(altura + 20, (frame.shape[0] + altura) // 2)
    cv2.putText(
        frame,
        texto,
        (x, y),
        fonte,
        escala,
        (0, 0, 0),
        espessura + 5,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        texto,
        (x, y),
        fonte,
        escala,
        cor,
        espessura,
        cv2.LINE_AA,
    )


def gravar(numero, duracao, contagem, fonte, fps):
    destino = proximo_caminho(numero)
    processo = None
    captura = None
    escritor = None
    porta = porta_local_livre()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 640, 720)

    quadro_conexao = np.zeros((720, 640, 3), dtype=np.uint8)
    texto_centralizado(
        quadro_conexao,
        "Conectando a camera...",
        0.8,
        (255, 255, 255),
        2,
    )
    cv2.imshow(WINDOW_NAME, quadro_conexao)
    cv2.waitKey(1)

    try:
        processo = subprocess.Popen(
            comando_vlc(fonte, porta),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        captura, frame = conectar_preview(porta)

        inicio_contagem = time.monotonic()
        while True:
            decorrido = time.monotonic() - inicio_contagem
            restante = contagem - int(decorrido)
            if restante <= 0:
                break

            exibicao = frame.copy()
            texto_centralizado(
                exibicao,
                str(restante),
                5.0,
                (0, 255, 255),
                10,
            )
            cv2.imshow(WINDOW_NAME, exibicao)
            if cv2.waitKey(1) & 0xFF == 27:
                raise KeyboardInterrupt

            recebido, proximo = captura.read()
            if not recebido or proximo is None:
                raise RuntimeError("O fluxo da câmera foi interrompido.")
            frame = proximo

        altura, largura = frame.shape[:2]
        codec = cv2.VideoWriter_fourcc(*"mp4v")
        escritor = cv2.VideoWriter(
            str(destino),
            codec,
            fps,
            (largura, altura),
        )
        if not escritor.isOpened():
            raise RuntimeError("Não foi possível criar o arquivo MP4.")

        inicio_gravacao = time.monotonic()
        frames_gravados = 0
        while time.monotonic() - inicio_gravacao < duracao:
            recebido, frame = captura.read()
            if not recebido or frame is None:
                raise RuntimeError("O fluxo da câmera foi interrompido.")

            escritor.write(frame)
            frames_gravados += 1

            exibicao = frame.copy()
            decorrido = time.monotonic() - inicio_gravacao
            cv2.circle(exibicao, (30, 35), 10, (0, 0, 255), -1)
            cv2.putText(
                exibicao,
                f"GRAVANDO {decorrido:04.1f}s",
                (50, 43),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(WINDOW_NAME, exibicao)
            if cv2.waitKey(1) & 0xFF == 27:
                raise KeyboardInterrupt

        escritor.release()
        escritor = None

        quadro_final = frame.copy()
        texto_centralizado(
            quadro_final,
            "VIDEO SALVO",
            1.2,
            (0, 255, 0),
            3,
        )
        cv2.imshow(WINDOW_NAME, quadro_final)
        cv2.waitKey(1200)

        print(f"ARQUIVO={destino}")
        print(f"FRAMES={frames_gravados}")
        print(f"FPS={fps}")
        return destino
    finally:
        if escritor is not None:
            escritor.release()
        if captura is not None:
            captura.release()
        if processo is not None and processo.poll() is None:
            processo.terminate()
            try:
                processo.wait(timeout=3)
            except subprocess.TimeoutExpired:
                processo.kill()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Grava vídeo RTSP com prévia e contagem regressiva."
    )
    parser.add_argument("--numero", type=int, required=True)
    parser.add_argument("--duracao", type=float, default=10.0)
    parser.add_argument("--contagem", type=int, default=3)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument(
        "--fonte",
        default=os.getenv("CAMERA_OFFLINE_SOURCE", DEFAULT_SOURCE),
    )
    args = parser.parse_args()
    gravar(
        numero=args.numero,
        duracao=args.duracao,
        contagem=args.contagem,
        fonte=args.fonte,
        fps=args.fps,
    )


if __name__ == "__main__":
    main()
