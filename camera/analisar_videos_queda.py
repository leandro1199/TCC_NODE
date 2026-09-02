import argparse
import csv
import json
from pathlib import Path

import cv2

from detector_yolo_queda import DetectorYOLOQueda


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = BASE_DIR / "gravacoes"
DEFAULT_OUTPUT_DIR = BASE_DIR / "resultado"
DEFAULT_LABELS_PATH = BASE_DIR / "rotulos_videos.json"


def carregar_rotulos(path):
    if path is None or not path.exists():
        return {}

    dados = json.loads(path.read_text(encoding="utf-8"))
    videos = dados.get("videos", dados) if isinstance(dados, dict) else {}
    if not isinstance(videos, dict):
        raise ValueError("O arquivo de rótulos precisa conter um objeto 'videos'.")
    return videos


def _divisao_segura(numerador, denominador):
    return round(numerador / denominador, 4) if denominador else None


def avaliar_resultados(resultados, rotulos):
    avaliados = []
    for resultado in resultados:
        rotulo = rotulos.get(resultado["video"], {})
        esperado = rotulo.get("queda") if isinstance(rotulo, dict) else None
        if not isinstance(esperado, bool):
            resultado["rotulo_esperado"] = None
            resultado["classificacao"] = "nao_rotulado"
            continue

        previsto = bool(resultado["queda_identificada"])
        if esperado and previsto:
            classificacao = "verdadeiro_positivo"
        elif esperado:
            classificacao = "falso_negativo"
        elif previsto:
            classificacao = "falso_positivo"
        else:
            classificacao = "verdadeiro_negativo"

        inicio_esperado = rotulo.get("inicio_queda_segundos")
        atraso = None
        if (
            esperado
            and previsto
            and isinstance(inicio_esperado, (int, float))
        ):
            atraso = round(
                resultado["primeiro_tempo_queda_segundos"] - inicio_esperado,
                4,
            )

        resultado.update({
            "rotulo_esperado": esperado,
            "inicio_queda_esperado_segundos": inicio_esperado,
            "classificacao": classificacao,
            "atraso_deteccao_segundos": atraso,
        })
        avaliados.append(resultado)

    contagens = {
        nome: sum(item["classificacao"] == nome for item in avaliados)
        for nome in (
            "verdadeiro_positivo",
            "verdadeiro_negativo",
            "falso_positivo",
            "falso_negativo",
        )
    }
    vp = contagens["verdadeiro_positivo"]
    vn = contagens["verdadeiro_negativo"]
    fp = contagens["falso_positivo"]
    fn = contagens["falso_negativo"]
    atrasos = [
        item["atraso_deteccao_segundos"]
        for item in avaliados
        if item.get("atraso_deteccao_segundos") is not None
    ]
    return {
        "videos_rotulados": len(avaliados),
        "videos_sem_rotulo": len(resultados) - len(avaliados),
        **contagens,
        "acuracia": _divisao_segura(vp + vn, vp + vn + fp + fn),
        "precisao": _divisao_segura(vp, vp + fp),
        "sensibilidade_recall": _divisao_segura(vp, vp + fn),
        "especificidade": _divisao_segura(vn, vn + fp),
        "atraso_medio_segundos": (
            round(sum(atrasos) / len(atrasos), 4) if atrasos else None
        ),
    }


def intervalos_contiguos(frames):
    if not frames:
        return []

    intervalos = []
    inicio = anterior = frames[0]
    for frame in frames[1:]:
        if frame == anterior + 1:
            anterior = frame
            continue
        intervalos.append([inicio, anterior])
        inicio = anterior = frame
    intervalos.append([inicio, anterior])
    return intervalos


def desenhar_resultado(
    frame,
    numero_frame,
    total_frames,
    tempo_segundos,
    queda_confirmada,
    confianca,
    caixas,
):
    cor_status = (0, 0, 255) if queda_confirmada else (0, 180, 0)
    texto_status = (
        f"QUEDA CONFIRMADA | confianca {confianca * 100:.1f}%"
        if queda_confirmada
        else "SEM QUEDA CONFIRMADA"
    )

    for x1, y1, x2, y2, confianca_caixa in caixas:
        cor = (0, 0, 255) if queda_confirmada else (0, 165, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), cor, 3)
        cv2.putText(
            frame,
            f"Postura suspeita {confianca_caixa * 100:.1f}%",
            (x1, max(25, y1 - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            cor,
            2,
            cv2.LINE_AA,
        )

    cv2.rectangle(frame, (0, 0), (frame.shape[1], 82), (20, 20, 20), -1)
    cv2.putText(
        frame,
        texto_status,
        (18, 33),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        cor_status,
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"Frame {numero_frame}/{total_frames} | Tempo {tempo_segundos:.2f}s",
        (18, 66),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    if queda_confirmada:
        cv2.rectangle(
            frame,
            (3, 3),
            (frame.shape[1] - 4, frame.shape[0] - 4),
            (0, 0, 255),
            6,
        )
    return frame


def analisar_video(
    detector,
    video_path,
    output_dir,
    csv_writer,
    view_csv_writer,
):
    captura = cv2.VideoCapture(str(video_path))
    if not captura.isOpened():
        raise RuntimeError(f"Não foi possível abrir {video_path}.")

    fps = float(captura.get(cv2.CAP_PROP_FPS)) or 15.0
    total_frames = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    largura = int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura = int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))
    stream_id = f"analise:{video_path.stem}"
    output_video = output_dir / f"{video_path.stem}_analisado.mp4"

    escritor = cv2.VideoWriter(
        str(output_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (largura, altura),
    )
    if not escritor.isOpened():
        captura.release()
        raise RuntimeError(f"Não foi possível criar {output_video}.")

    frames_confirmados = []
    primeira_imagem = None
    primeiro_frame_candidato = None
    confianca_primeiro_candidato = 0.0
    confianca_primeira_queda = 0.0
    maior_confianca_instantanea = 0.0
    frame_maior_confianca_instantanea = None
    maior_confianca_confirmada = 0.0
    frame_maior_confianca_confirmada = None
    candidatos_total = 0
    layouts_detectados = set()
    transicoes = []
    numero_frame = 0

    try:
        while True:
            recebido, frame = captura.read()
            if not recebido or frame is None:
                break
            numero_frame += 1
            tempo_segundos = (numero_frame - 1) / fps

            queda, confianca, caixas = detector.detectar(
                frame,
                stream_id=stream_id,
            )
            diagnosticos = detector.obter_diagnostico(stream_id)
            maior_instantanea = max(
                (caixa[4] for caixa in caixas),
                default=0.0,
            )
            candidatos_total += len(caixas)

            if caixas and primeiro_frame_candidato is None:
                primeiro_frame_candidato = numero_frame
                confianca_primeiro_candidato = maior_instantanea

            if maior_instantanea > maior_confianca_instantanea:
                maior_confianca_instantanea = maior_instantanea
                frame_maior_confianca_instantanea = numero_frame

            if queda:
                frames_confirmados.append(numero_frame)
                if primeira_imagem is None:
                    confianca_primeira_queda = confianca
                    primeira_imagem = output_dir / (
                        f"{video_path.stem}_primeira_queda_frame_"
                        f"{numero_frame}.jpg"
                    )
                    cv2.imwrite(str(primeira_imagem), frame)
                if confianca > maior_confianca_confirmada:
                    maior_confianca_confirmada = confianca
                    frame_maior_confianca_confirmada = numero_frame

            csv_writer.writerow({
                "video": video_path.name,
                "frame": numero_frame,
                "tempo_segundos": f"{tempo_segundos:.4f}",
                "queda_confirmada": int(queda),
                "confianca_confirmada": f"{confianca:.6f}",
                "candidatos_postura": len(caixas),
                "maior_confianca_instantanea": f"{maior_instantanea:.6f}",
            })

            for diagnostico in diagnosticos:
                layouts_detectados.add(diagnostico["layout"])
                if diagnostico["transition"]:
                    transicoes.append({
                        "frame": numero_frame,
                        "tempo_segundos": round(tempo_segundos, 4),
                        "view": diagnostico["view"],
                    })
                view_csv_writer.writerow({
                    "video": video_path.name,
                    "frame": numero_frame,
                    "tempo_segundos": f"{tempo_segundos:.4f}",
                    "view": diagnostico["view"],
                    "layout": diagnostico["layout"],
                    "deteccoes_pessoa": diagnostico["detections"],
                    "queda_instantanea": int(
                        diagnostico["instantaneous_fall"]
                    ),
                    "confianca_instantanea": (
                        f"{diagnostico['instantaneous_confidence']:.6f}"
                    ),
                    "queda_confirmada": int(diagnostico["confirmed_fall"]),
                    "confianca_confirmada": (
                        f"{diagnostico['confirmed_confidence']:.6f}"
                    ),
                    "confianca_modelo": (
                        f"{diagnostico['model_confidence']:.6f}"
                    ),
                    "postura_score": (
                        "" if diagnostico["posture_score"] is None
                        else f"{diagnostico['posture_score']:.6f}"
                    ),
                    "angulo_tronco": (
                        "" if diagnostico["torso_angle"] is None
                        else f"{diagnostico['torso_angle']:.4f}"
                    ),
                    "centro_y": (
                        "" if diagnostico["center_y"] is None
                        else f"{diagnostico['center_y']:.6f}"
                    ),
                    "track_iou": f"{diagnostico['track_iou']:.6f}",
                    "track_distance": (
                        f"{diagnostico['track_distance']:.6f}"
                    ),
                    "transicao": int(diagnostico["transition"]),
                    "variacao_angulo": f"{diagnostico['angle_change']:.4f}",
                    "deslocamento_vertical": (
                        f"{diagnostico['downward_change']:.6f}"
                    ),
                    "hits": diagnostico["hits"],
                    "misses": diagnostico["misses"],
                    "event_frames": diagnostico["event_frames"],
                })

            anotado = desenhar_resultado(
                frame.copy(),
                numero_frame,
                total_frames,
                tempo_segundos,
                queda,
                confianca,
                caixas,
            )
            escritor.write(anotado)

            if numero_frame % 25 == 0 or numero_frame == total_frames:
                print(
                    f"{video_path.name}: {numero_frame}/{total_frames} frames",
                    flush=True,
                )
    finally:
        captura.release()
        escritor.release()
        detector.reset_stream(stream_id)

    intervalos = intervalos_contiguos(frames_confirmados)
    return {
        "video": video_path.name,
        "video_analisado": output_video.name,
        "fps": round(fps, 4),
        "total_frames": numero_frame,
        "duracao_segundos": round(numero_frame / fps, 4),
        "layouts_detectados": sorted(layouts_detectados),
        "transicoes_detectadas": transicoes,
        "queda_identificada": bool(frames_confirmados),
        "primeiro_frame_queda": (
            frames_confirmados[0] if frames_confirmados else None
        ),
        "primeiro_tempo_queda_segundos": (
            round((frames_confirmados[0] - 1) / fps, 4)
            if frames_confirmados else None
        ),
        "ultimo_frame_queda": (
            frames_confirmados[-1] if frames_confirmados else None
        ),
        "frames_com_queda": frames_confirmados,
        "intervalos_frames_queda": intervalos,
        "quantidade_frames_com_queda": len(frames_confirmados),
        "confianca_primeira_queda": round(confianca_primeira_queda, 6),
        "confianca_primeira_queda_percentual": round(
            confianca_primeira_queda * 100,
            2,
        ),
        "maior_confianca_confirmada": round(
            maior_confianca_confirmada,
            6,
        ),
        "maior_confianca_confirmada_percentual": round(
            maior_confianca_confirmada * 100,
            2,
        ),
        "frame_maior_confianca_confirmada": (
            frame_maior_confianca_confirmada
        ),
        "primeiro_frame_candidato": primeiro_frame_candidato,
        "confianca_primeiro_candidato_percentual": round(
            confianca_primeiro_candidato * 100,
            2,
        ),
        "maior_confianca_instantanea": round(
            maior_confianca_instantanea,
            6,
        ),
        "maior_confianca_instantanea_percentual": round(
            maior_confianca_instantanea * 100,
            2,
        ),
        "frame_maior_confianca_instantanea": (
            frame_maior_confianca_instantanea
        ),
        "candidatos_postura_total": candidatos_total,
        "imagem_primeira_queda": primeira_imagem.name if primeira_imagem else None,
    }


def escrever_resumo_texto(resultados, detector, output_dir, avaliacao):
    linhas = [
        "RESULTADOS DA DETECÇÃO DE QUEDAS",
        f"Modelo: {detector.model_path}",
        "",
    ]
    for resultado in resultados:
        linhas.append(resultado["video"])
        linhas.append(
            "  Layout detectado: "
            + ", ".join(resultado["layouts_detectados"] or ["desconhecido"])
        )
        if resultado["transicoes_detectadas"]:
            transicoes = ", ".join(
                f"{item['view']}@{item['tempo_segundos']:.2f}s"
                for item in resultado["transicoes_detectadas"]
            )
            linhas.append(f"  Transições temporais: {transicoes}")
        if resultado["queda_identificada"]:
            linhas.extend([
                "  Queda identificada: SIM",
                f"  Primeiro frame: {resultado['primeiro_frame_queda']}",
                (
                    "  Primeiro instante: "
                    f"{resultado['primeiro_tempo_queda_segundos']:.2f}s"
                ),
                (
                    "  Confiança na primeira confirmação: "
                    f"{resultado['confianca_primeira_queda_percentual']:.2f}%"
                ),
                (
                    "  Maior confiança confirmada: "
                    f"{resultado['maior_confianca_confirmada_percentual']:.2f}% "
                    f"(frame {resultado['frame_maior_confianca_confirmada']})"
                ),
                (
                    "  Maior evidência instantânea: "
                    f"{resultado['maior_confianca_instantanea_percentual']:.2f}% "
                    f"(frame {resultado['frame_maior_confianca_instantanea']})"
                ),
                (
                    "  Intervalos de frames: "
                    f"{resultado['intervalos_frames_queda']}"
                ),
            ])
        else:
            linhas.extend([
                "  Queda identificada: NÃO",
                (
                    "  Maior confiança de postura suspeita: "
                    f"{resultado['maior_confianca_instantanea_percentual']:.2f}% "
                    f"(frame {resultado['frame_maior_confianca_instantanea']})"
                ),
            ])
        if resultado.get("rotulo_esperado") is not None:
            esperado = "QUEDA" if resultado["rotulo_esperado"] else "SEM QUEDA"
            linhas.append(f"  Rótulo esperado: {esperado}")
            linhas.append(f"  Classificação: {resultado['classificacao']}")
            if resultado.get("atraso_deteccao_segundos") is not None:
                linhas.append(
                    "  Atraso da detecção: "
                    f"{resultado['atraso_deteccao_segundos']:.2f}s"
                )
        linhas.append("")

    linhas.extend([
        "AVALIAÇÃO COM RÓTULOS",
        f"  Vídeos rotulados: {avaliacao['videos_rotulados']}",
        f"  Vídeos sem rótulo: {avaliacao['videos_sem_rotulo']}",
    ])
    if avaliacao["videos_rotulados"]:
        linhas.extend([
            f"  Verdadeiros positivos: {avaliacao['verdadeiro_positivo']}",
            f"  Verdadeiros negativos: {avaliacao['verdadeiro_negativo']}",
            f"  Falsos positivos: {avaliacao['falso_positivo']}",
            f"  Falsos negativos: {avaliacao['falso_negativo']}",
            f"  Precisão: {avaliacao['precisao']}",
            f"  Sensibilidade/recall: {avaliacao['sensibilidade_recall']}",
            f"  Especificidade: {avaliacao['especificidade']}",
            f"  Acurácia: {avaliacao['acuracia']}",
            f"  Atraso médio (s): {avaliacao['atraso_medio_segundos']}",
        ])

    (output_dir / "resumo_resultados.txt").write_text(
        "\n".join(linhas),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Analisa vídeos, anota quedas e gera métricas por frame."
    )
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument(
        "--saida",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--rotulos",
        type=Path,
        default=DEFAULT_LABELS_PATH,
        help=(
            "JSON com o resultado esperado de cada vídeo. Entradas com queda=null "
            "são ignoradas nas métricas de acerto."
        ),
    )
    args = parser.parse_args()

    videos = [video.resolve() for video in args.videos]
    for video in videos:
        if not video.exists():
            raise FileNotFoundError(f"Vídeo não encontrado: {video}")

    output_dir = args.saida.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    detector = DetectorYOLOQueda()
    print(f"Modelo: {detector.model_path}", flush=True)
    rotulos = carregar_rotulos(args.rotulos.resolve() if args.rotulos else None)

    csv_path = output_dir / "metricas_por_frame.csv"
    view_csv_path = output_dir / "metricas_por_view.csv"
    resultados = []
    with (
        csv_path.open("w", newline="", encoding="utf-8") as arquivo_csv,
        view_csv_path.open("w", newline="", encoding="utf-8") as arquivo_view_csv,
    ):
        campos = [
            "video",
            "frame",
            "tempo_segundos",
            "queda_confirmada",
            "confianca_confirmada",
            "candidatos_postura",
            "maior_confianca_instantanea",
        ]
        escritor_csv = csv.DictWriter(arquivo_csv, fieldnames=campos)
        escritor_csv.writeheader()
        campos_view = [
            "video",
            "frame",
            "tempo_segundos",
            "view",
            "layout",
            "deteccoes_pessoa",
            "queda_instantanea",
            "confianca_instantanea",
            "queda_confirmada",
            "confianca_confirmada",
            "confianca_modelo",
            "postura_score",
            "angulo_tronco",
            "centro_y",
            "track_iou",
            "track_distance",
            "transicao",
            "variacao_angulo",
            "deslocamento_vertical",
            "hits",
            "misses",
            "event_frames",
        ]
        escritor_view_csv = csv.DictWriter(
            arquivo_view_csv, fieldnames=campos_view
        )
        escritor_view_csv.writeheader()
        for video in videos:
            resultados.append(
                analisar_video(
                    detector,
                    video,
                    output_dir,
                    escritor_csv,
                    escritor_view_csv,
                )
            )

    avaliacao = avaliar_resultados(resultados, rotulos)
    resumo = {
        "modelo": str(detector.model_path),
        "quantidade_videos": len(resultados),
        "arquivo_rotulos": str(args.rotulos.resolve()) if args.rotulos else None,
        "avaliacao": avaliacao,
        "resultados": resultados,
    }
    (output_dir / "resumo_resultados.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    escrever_resumo_texto(resultados, detector, output_dir, avaliacao)
    print(f"Resultados salvos em: {output_dir}", flush=True)


if __name__ == "__main__":
    main()
