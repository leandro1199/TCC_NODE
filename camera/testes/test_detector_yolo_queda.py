import sys
import unittest
from pathlib import Path
from threading import Lock

import numpy as np


CAMERA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMERA_DIR))

from analisar_videos_queda import avaliar_resultados  # noqa: E402
from detector_yolo_queda import DetectorYOLOQueda  # noqa: E402


def detector_sem_modelo(layout="auto"):
    detector = DetectorYOLOQueda.__new__(DetectorYOLOQueda)
    detector.frame_layout = layout
    detector.confianca_deteccao = 0.25
    detector.limite_queda = 0.52
    detector.frames_confirmacao = 3
    detector.frames_liberacao = 5
    detector.fall_class_ids = set()
    detector._state_lock = Lock()
    detector._inference_lock = Lock()
    detector._stream_states = {}
    detector._last_diagnostics = {}
    return detector


class FakeBox:
    def __init__(self, xyxy, confidence=0.9, class_id=0):
        self.xyxy = np.asarray([xyxy], dtype=np.float32)
        self.conf = np.asarray([confidence], dtype=np.float32)
        self.cls = np.asarray([class_id], dtype=np.float32)


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes
        self.keypoints = None


class FakeModel:
    def predict(self, source, **_kwargs):
        return [
            FakeResult([FakeBox((10, 10, 100, 200))]),
            FakeResult([FakeBox((20, 10, 110, 200))]),
        ][:len(source)]


class TesteDetectorYOLOQueda(unittest.TestCase):
    def test_auto_separa_camera_dupla_vertical(self):
        detector = detector_sem_modelo()
        frame = np.zeros((720, 640, 3), dtype=np.uint8)

        views = detector._split_views(frame)

        self.assertEqual([item[0] for item in views], ["superior", "inferior"])
        self.assertEqual(views[0][1].shape, (360, 640, 3))
        self.assertEqual(views[1][3], 360)

    def test_auto_preserva_frame_unico(self):
        detector = detector_sem_modelo()
        landscape = np.zeros((720, 1280, 3), dtype=np.uint8)
        portrait = np.zeros((1280, 720, 3), dtype=np.uint8)

        self.assertEqual(len(detector._split_views(landscape)), 1)
        self.assertEqual(len(detector._split_views(portrait)), 1)

    def test_tracking_prefere_a_mesma_pessoa(self):
        detector = detector_sem_modelo()
        stream_id = "camera::view:single"
        detector._stream_states[stream_id] = detector._new_stream_state()
        detector._stream_states[stream_id]["tracked_box"] = (10, 10, 100, 200)
        perto = {
            "local_box": (14, 12, 104, 202),
            "model_confidence": 0.55,
            "box_area": 17100,
        }
        longe = {
            "local_box": (400, 20, 520, 230),
            "model_confidence": 0.99,
            "box_area": 25200,
        }

        selecionada, diagnostico = detector._select_tracked_detection(
            stream_id, [longe, perto], 640, 360
        )

        self.assertIs(selecionada, perto)
        self.assertGreater(diagnostico["track_iou"], 0.8)

    def test_transicao_precisa_de_confirmacao_temporal(self):
        detector = detector_sem_modelo()
        stream_id = "camera::view:single"
        for angle, center in ((5, 0.30), (8, 0.31), (10, 0.32)):
            detector._update_stream(
                stream_id, False, 0.0, observation=(angle, center)
            )

        ativo, _, diagnostico = detector._update_stream(
            stream_id, True, 0.7, observation=(55, 0.55)
        )
        self.assertFalse(ativo)
        self.assertTrue(diagnostico["transition"])

        _, _, diagnostico = detector._update_stream(
            stream_id, True, 0.7, observation=(60, 0.56)
        )
        self.assertFalse(diagnostico["transition"])
        ativo, _, _ = detector._update_stream(
            stream_id, True, 0.7, observation=(62, 0.57)
        )
        self.assertTrue(ativo)

    def test_deteccao_mantem_estado_independente_por_visao(self):
        detector = detector_sem_modelo()
        detector.modelo = FakeModel()
        detector.fall_class_ids = {0}
        frame = np.zeros((720, 640, 3), dtype=np.uint8)

        for _ in range(3):
            queda, _, caixas = detector.detectar(frame, stream_id="camera")

        self.assertTrue(queda)
        self.assertEqual(len(detector.obter_diagnostico("camera")), 2)
        self.assertEqual(len(caixas), 2)
        self.assertLess(caixas[0][1], 360)
        self.assertGreaterEqual(caixas[1][1], 360)

    def test_avaliacao_ignora_rotulo_desconhecido(self):
        resultados = [
            {
                "video": "queda.mp4",
                "queda_identificada": True,
                "primeiro_tempo_queda_segundos": 2.4,
            },
            {
                "video": "normal.mp4",
                "queda_identificada": False,
                "primeiro_tempo_queda_segundos": None,
            },
            {
                "video": "pendente.mp4",
                "queda_identificada": False,
                "primeiro_tempo_queda_segundos": None,
            },
        ]
        rotulos = {
            "queda.mp4": {"queda": True, "inicio_queda_segundos": 2.0},
            "normal.mp4": {"queda": False},
            "pendente.mp4": {"queda": None},
        }

        avaliacao = avaliar_resultados(resultados, rotulos)

        self.assertEqual(avaliacao["videos_rotulados"], 2)
        self.assertEqual(avaliacao["videos_sem_rotulo"], 1)
        self.assertEqual(avaliacao["acuracia"], 1.0)
        self.assertEqual(avaliacao["atraso_medio_segundos"], 0.4)


if __name__ == "__main__":
    unittest.main()
