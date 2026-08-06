import math
import os
from collections import deque
from pathlib import Path
from threading import Lock

import numpy as np
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def _default_model_path() -> Path:
    candidates = (
        BASE_DIR / "yolov8n-pose.pt",
        PROJECT_DIR / "runs" / "pose" / "fall_pose_v2" / "weights" / "best.pt",
        PROJECT_DIR / "runs" / "pose" / "train" / "weights" / "best.pt",
    )
    return next((path for path in candidates if path.exists()), candidates[-1])


class DetectorYOLOQueda:
    """Detecta postura de queda e, em vídeo, confirma em vários frames."""

    FALL_CLASS_NAMES = {"fall", "fallen", "falling", "queda", "caida", "caido"}

    def __init__(
        self,
        model_path=None,
        confianca_deteccao=None,
        limite_queda=None,
        frames_confirmacao=None,
        frames_liberacao=None,
    ):
        configured_path = model_path or os.getenv("YOLO_MODEL_PATH")
        self.model_path = (
            Path(configured_path).expanduser().resolve()
            if configured_path else _default_model_path().resolve()
        )
        if not self.model_path.exists():
            raise FileNotFoundError(f"Modelo YOLO não encontrado: {self.model_path}")

        self.confianca_deteccao = float(
            confianca_deteccao
            if confianca_deteccao is not None
            else os.getenv("YOLO_DETECTION_CONFIDENCE", "0.25")
        )
        self.limite_queda = float(
            limite_queda
            if limite_queda is not None
            else os.getenv("YOLO_FALL_THRESHOLD", "0.52")
        )
        self.frames_confirmacao = int(
            frames_confirmacao
            if frames_confirmacao is not None
            else os.getenv("YOLO_CONFIRMATION_FRAMES", "3")
        )
        self.frames_liberacao = int(
            frames_liberacao
            if frames_liberacao is not None
            else os.getenv("YOLO_RELEASE_FRAMES", "5")
        )

        if not 0.0 <= self.confianca_deteccao <= 1.0:
            raise ValueError("YOLO_DETECTION_CONFIDENCE deve estar entre 0 e 1.")
        if not 0.0 <= self.limite_queda <= 1.0:
            raise ValueError("YOLO_FALL_THRESHOLD deve estar entre 0 e 1.")
        if self.frames_confirmacao < 1 or self.frames_liberacao < 1:
            raise ValueError("Os limites de frames devem ser maiores que zero.")

        self.modelo = YOLO(str(self.model_path))
        if getattr(self.modelo, "task", None) != "pose":
            raise ValueError(
                f"O modelo precisa ser YOLO Pose; tarefa encontrada: {self.modelo.task!r}."
            )

        names = self.modelo.names
        if isinstance(names, dict):
            names_by_id = names
        else:
            names_by_id = dict(enumerate(names))
        self.fall_class_ids = {
            int(class_id)
            for class_id, name in names_by_id.items()
            if self._normalize_class_name(name) in self.FALL_CLASS_NAMES
        }

        self._inference_lock = Lock()
        self._state_lock = Lock()
        self._stream_states = {}

    @staticmethod
    def _normalize_class_name(name) -> str:
        return str(name).strip().lower().replace("í", "i").replace("ã", "a")

    @staticmethod
    def _visible_center(points, confidence, indices, minimum=0.25):
        valid = [index for index in indices if confidence[index] >= minimum]
        if not valid:
            return None
        return np.mean(points[valid], axis=0)

    @classmethod
    def _posture_metrics(cls, points, confidence, box):
        """Retorna (pontuação horizontal, ângulo do tronco em graus)."""
        points = np.asarray(points, dtype=np.float32)
        confidence = np.asarray(confidence, dtype=np.float32)
        if points.shape != (17, 2) or confidence.shape[0] != 17:
            return None, None

        shoulders = cls._visible_center(points, confidence, (5, 6))
        hips = cls._visible_center(points, confidence, (11, 12))

        torso_horizontal = 0.0
        angle_from_vertical = None
        if shoulders is not None and hips is not None:
            delta = hips - shoulders
            angle_from_vertical = math.degrees(
                math.atan2(abs(float(delta[0])), abs(float(delta[1])) + 1e-6)
            )
            torso_horizontal = float(
                np.clip((angle_from_vertical - 25.0) / 45.0, 0.0, 1.0)
            )

        body_indices = (5, 6, 11, 12, 13, 14, 15, 16)
        visible = np.array(
            [points[index] for index in body_indices if confidence[index] >= 0.25]
        )
        axis_horizontal = 0.0
        keypoint_aspect = 0.0
        if len(visible) >= 4:
            centered = visible - visible.mean(axis=0)
            covariance = np.cov(centered, rowvar=False)
            values, vectors = np.linalg.eigh(covariance)
            main_axis = vectors[:, int(np.argmax(values))]
            axis_horizontal = abs(float(main_axis[0]))

            width = float(np.ptp(visible[:, 0]))
            height = float(np.ptp(visible[:, 1]))
            keypoint_aspect = float(np.clip((width / max(height, 1.0) - 0.45) / 0.9, 0.0, 1.0))

        x1, y1, x2, y2 = box
        box_aspect = float(
            np.clip(((x2 - x1) / max(y2 - y1, 1.0) - 0.55) / 0.85, 0.0, 1.0)
        )
        body_horizontal = max(torso_horizontal, axis_horizontal)
        score = 0.50 * body_horizontal + 0.30 * keypoint_aspect + 0.20 * box_aspect
        return score, angle_from_vertical

    @classmethod
    def _posture_score(cls, points, confidence, box) -> float | None:
        return cls._posture_metrics(points, confidence, box)[0]

    def _update_stream(self, stream_id, detected, confidence, observation=None):
        with self._state_lock:
            state = self._stream_states.setdefault(
                str(stream_id),
                {
                    "hits": 0,
                    "misses": 0,
                    "active": False,
                    "confidence": 0.0,
                    "event_frames": 0,
                    "history": deque(maxlen=31),
                },
            )

            transition = False
            if observation is not None:
                torso_angle, center_y = observation
                recent = list(state["history"])
                if torso_angle is not None and len(recent) >= 3:
                    valid_angles = [item[0] for item in recent if item[0] is not None]
                    valid_centers = [item[1] for item in recent]
                    if valid_angles and valid_centers:
                        angle_change = torso_angle - min(valid_angles)
                        downward_change = center_y - min(valid_centers)
                        transition = (
                            detected
                            and torso_angle >= 40.0
                            and angle_change >= 25.0
                            and downward_change >= 0.07
                        )
                state["history"].append((torso_angle, center_y))

            if transition:
                state["event_frames"] = max(12, self.frames_confirmacao * 4)
            elif state["event_frames"] > 0:
                state["event_frames"] -= 1

            if self.fall_class_ids:
                event_evidence = detected
            else:
                event_evidence = detected and (
                    state["active"] or transition or state["event_frames"] > 0
                )

            if event_evidence:
                state["hits"] += 1
                state["misses"] = 0
                state["confidence"] = float(confidence)
                if state["hits"] >= self.frames_confirmacao:
                    state["active"] = True
            else:
                state["hits"] = max(0, state["hits"] - 1)
                state["misses"] += 1
                if state["misses"] >= self.frames_liberacao:
                    state.update(
                        hits=0, misses=0, active=False, confidence=0.0
                    )
            return state["active"], state["confidence"]

    def reset_stream(self, stream_id) -> None:
        with self._state_lock:
            self._stream_states.pop(str(stream_id), None)

    def detectar(self, frame, stream_id=None):
        if frame is None or not hasattr(frame, "shape"):
            raise ValueError("Frame inválido para detecção.")

        with self._inference_lock:
            resultados = self.modelo.predict(
                source=frame,
                conf=self.confianca_deteccao,
                iou=0.60,
                imgsz=640,
                verbose=False,
            )

        maior_confianca = 0.0
        caixas = []
        best_observation = None
        best_observation_confidence = -1.0
        frame_height = float(frame.shape[0])

        for resultado in resultados:
            boxes = resultado.boxes
            keypoints = resultado.keypoints
            if boxes is None:
                continue

            for index, box in enumerate(boxes):
                model_confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())

                posture = None
                torso_angle = None
                if keypoints is not None and index < len(keypoints.xy):
                    points = keypoints.xy[index].cpu().numpy()
                    if keypoints.conf is None:
                        point_confidence = np.ones(17, dtype=np.float32)
                    else:
                        point_confidence = keypoints.conf[index].cpu().numpy()
                    posture, torso_angle = self._posture_metrics(
                        points, point_confidence, (x1, y1, x2, y2)
                    )

                if model_confidence > best_observation_confidence:
                    best_observation_confidence = model_confidence
                    best_observation = (
                        torso_angle,
                        ((y1 + y2) / 2.0) / max(frame_height, 1.0),
                    )

                if self.fall_class_ids:
                    is_fall = class_id in self.fall_class_ids
                    fall_confidence = model_confidence
                else:
                    if posture is None:
                        fall_confidence = model_confidence
                        is_fall = model_confidence >= max(0.75, self.limite_queda)
                    else:
                        fall_confidence = 0.55 * model_confidence + 0.45 * posture
                        is_fall = posture >= 0.40 and fall_confidence >= self.limite_queda

                if is_fall:
                    confidence = float(np.clip(fall_confidence, 0.0, 1.0))
                    caixas.append((int(x1), int(y1), int(x2), int(y2), confidence))
                    maior_confianca = max(maior_confianca, confidence)

        queda_instantanea = bool(caixas)
        if stream_id is None:
            return queda_instantanea, maior_confianca, caixas

        queda_confirmada, confianca_confirmada = self._update_stream(
            stream_id,
            queda_instantanea,
            maior_confianca,
            observation=best_observation,
        )
        return queda_confirmada, confianca_confirmada, caixas
