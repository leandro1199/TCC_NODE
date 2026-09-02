import math
import os
from copy import deepcopy
from collections import deque
from pathlib import Path
from threading import Lock

import numpy as np
from ultralytics import YOLO


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def _default_model_path() -> Path:
    candidates = (
        PROJECT_DIR / "runs" / "pose" / "fall_pose_v2" / "weights" / "best.pt",
        PROJECT_DIR / "runs" / "pose" / "train" / "weights" / "best.pt",
        BASE_DIR / "yolov8n-pose.pt",
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
        frame_layout=None,
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
        self.frame_layout = (
            frame_layout or os.getenv("YOLO_FRAME_LAYOUT", "auto")
        ).strip().lower()

        if not 0.0 <= self.confianca_deteccao <= 1.0:
            raise ValueError("YOLO_DETECTION_CONFIDENCE deve estar entre 0 e 1.")
        if not 0.0 <= self.limite_queda <= 1.0:
            raise ValueError("YOLO_FALL_THRESHOLD deve estar entre 0 e 1.")
        if self.frames_confirmacao < 1 or self.frames_liberacao < 1:
            raise ValueError("Os limites de frames devem ser maiores que zero.")
        if self.frame_layout not in {"auto", "single", "vertical_dual"}:
            raise ValueError(
                "YOLO_FRAME_LAYOUT deve ser auto, single ou vertical_dual."
            )

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
        self._last_diagnostics = {}

    @staticmethod
    def _normalize_class_name(name) -> str:
        return str(name).strip().lower().replace("í", "i").replace("ã", "a")

    def _split_views(self, frame):
        """Separa streams de câmera dupla sem alterar as coordenadas de saída."""
        height, width = frame.shape[:2]
        layout = self.frame_layout

        if layout == "auto":
            half_height = height // 2
            half_aspect = width / max(half_height, 1)
            looks_like_vertical_dual = (
                height > width
                and height % 2 == 0
                and 1.45 <= half_aspect <= 2.15
            )
            layout = "vertical_dual" if looks_like_vertical_dual else "single"

        if layout == "vertical_dual":
            middle = height // 2
            if middle < 2 or height - middle < 2:
                return [("single", frame, 0, 0)]
            return [
                ("superior", frame[:middle, :], 0, 0),
                ("inferior", frame[middle:, :], 0, middle),
            ]

        return [("single", frame, 0, 0)]

    @staticmethod
    def _box_iou(first, second) -> float:
        if first is None or second is None:
            return 0.0
        ax1, ay1, ax2, ay2 = first
        bx1, by1, bx2, by2 = second
        intersection_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
        intersection_height = max(0.0, min(ay2, by2) - max(ay1, by1))
        intersection = intersection_width * intersection_height
        first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = first_area + second_area - intersection
        return float(intersection / union) if union > 0 else 0.0

    @staticmethod
    def _center_distance(first, second, width, height) -> float:
        if first is None or second is None:
            return 1.0
        first_center = ((first[0] + first[2]) / 2, (first[1] + first[3]) / 2)
        second_center = (
            (second[0] + second[2]) / 2,
            (second[1] + second[3]) / 2,
        )
        dx = (first_center[0] - second_center[0]) / max(float(width), 1.0)
        dy = (first_center[1] - second_center[1]) / max(float(height), 1.0)
        return float(math.hypot(dx, dy))

    @staticmethod
    def _new_stream_state():
        return {
            "hits": 0,
            "misses": 0,
            "active": False,
            "confidence": 0.0,
            "event_frames": 0,
            "history": deque(maxlen=31),
            "tracked_box": None,
            "transition_latched": False,
        }

    def _select_tracked_detection(
        self,
        stream_id,
        detections,
        frame_width,
        frame_height,
    ):
        """Mantém a observação temporal presa à mesma pessoa quando possível."""
        if not detections:
            return None, {"track_iou": 0.0, "track_distance": 1.0}

        with self._state_lock:
            state = self._stream_states.setdefault(
                str(stream_id), self._new_stream_state()
            )
            previous_box = state.get("tracked_box")

            if previous_box is None:
                selected = max(
                    detections,
                    key=lambda item: item["model_confidence"] * item["box_area"],
                )
                track_iou = 0.0
                track_distance = 0.0
            else:
                ranked = []
                for detection in detections:
                    track_iou = self._box_iou(previous_box, detection["local_box"])
                    track_distance = self._center_distance(
                        previous_box,
                        detection["local_box"],
                        frame_width,
                        frame_height,
                    )
                    continuity = max(track_iou, max(0.0, 1.0 - track_distance / 0.45))
                    score = 0.75 * continuity + 0.25 * detection["model_confidence"]
                    ranked.append((score, track_iou, track_distance, detection))
                _, track_iou, track_distance, selected = max(
                    ranked, key=lambda item: item[0]
                )

            state["tracked_box"] = selected["local_box"]
            return selected, {
                "track_iou": float(track_iou),
                "track_distance": float(track_distance),
            }

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
                str(stream_id), self._new_stream_state()
            )

            transition_candidate = False
            angle_change = 0.0
            downward_change = 0.0
            if observation is not None:
                torso_angle, center_y = observation
                recent = list(state["history"])
                if torso_angle is not None and len(recent) >= 3:
                    valid_angles = [item[0] for item in recent if item[0] is not None]
                    valid_centers = [item[1] for item in recent]
                    if valid_angles and valid_centers:
                        angle_change = torso_angle - min(valid_angles)
                        downward_change = center_y - min(valid_centers)
                        transition_candidate = (
                            detected
                            and torso_angle >= 40.0
                            and angle_change >= 25.0
                            and downward_change >= 0.07
                        )
                state["history"].append((torso_angle, center_y))

            transition = bool(
                transition_candidate and not state["transition_latched"]
            )

            if transition:
                state["transition_latched"] = True
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
                        hits=0,
                        misses=0,
                        active=False,
                        confidence=0.0,
                        event_frames=0,
                        transition_latched=False,
                    )
            diagnostics = {
                "transition": bool(transition),
                "angle_change": float(angle_change),
                "downward_change": float(downward_change),
                "hits": int(state["hits"]),
                "misses": int(state["misses"]),
                "event_frames": int(state["event_frames"]),
                "active": bool(state["active"]),
            }
            return state["active"], state["confidence"], diagnostics

    def reset_stream(self, stream_id) -> None:
        stream_id = str(stream_id)
        prefix = f"{stream_id}::view:"
        with self._state_lock:
            keys = [
                key for key in self._stream_states
                if key == stream_id or key.startswith(prefix)
            ]
            for key in keys:
                self._stream_states.pop(key, None)
            self._last_diagnostics.pop(stream_id, None)

    def obter_diagnostico(self, stream_id):
        """Retorna uma cópia segura da última decisão de cada visão."""
        with self._state_lock:
            return deepcopy(self._last_diagnostics.get(str(stream_id), []))

    def detectar(self, frame, stream_id=None):
        if frame is None or not hasattr(frame, "shape"):
            raise ValueError("Frame inválido para detecção.")

        views = self._split_views(frame)
        with self._inference_lock:
            resultados = self.modelo.predict(
                source=[view[1] for view in views],
                conf=self.confianca_deteccao,
                iou=0.60,
                imgsz=640,
                verbose=False,
            )

        caixas = []
        diagnostics = []
        confirmed_views = []
        instantaneous_confidences = []

        for (view_name, view_frame, offset_x, offset_y), resultado in zip(
            views, resultados
        ):
            view_height, view_width = view_frame.shape[:2]
            detections = []
            boxes = resultado.boxes
            keypoints = resultado.keypoints
            if boxes is None:
                boxes = []

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

                local_box = (x1, y1, x2, y2)
                global_box = (
                    x1 + offset_x,
                    y1 + offset_y,
                    x2 + offset_x,
                    y2 + offset_y,
                )
                detections.append({
                    "local_box": local_box,
                    "global_box": global_box,
                    "box_area": max(1.0, (x2 - x1) * (y2 - y1)),
                    "model_confidence": model_confidence,
                    "posture_score": posture,
                    "torso_angle": torso_angle,
                    "center_y": ((y1 + y2) / 2.0) / max(float(view_height), 1.0),
                    "is_fall": bool(is_fall),
                    "fall_confidence": float(np.clip(fall_confidence, 0.0, 1.0)),
                })

                if is_fall:
                    confidence = float(np.clip(fall_confidence, 0.0, 1.0))
                    caixas.append((
                        int(global_box[0]),
                        int(global_box[1]),
                        int(global_box[2]),
                        int(global_box[3]),
                        confidence,
                    ))

            if stream_id is None:
                instantaneous_confidences.extend(
                    item["fall_confidence"]
                    for item in detections
                    if item["is_fall"]
                )
                continue

            view_stream_id = f"{stream_id}::view:{view_name}"
            selected, tracking = self._select_tracked_detection(
                view_stream_id,
                detections,
                view_width,
                view_height,
            )
            detected = bool(selected and selected["is_fall"])
            confidence = selected["fall_confidence"] if detected else 0.0
            observation = (
                (selected["torso_angle"], selected["center_y"])
                if selected is not None else None
            )
            active, confirmed_confidence, state = self._update_stream(
                view_stream_id,
                detected,
                confidence,
                observation=observation,
            )
            if active:
                confirmed_views.append((view_name, confirmed_confidence))

            diagnostics.append({
                "view": view_name,
                "layout": (
                    "vertical_dual" if len(views) == 2 else "single"
                ),
                "detections": len(detections),
                "instantaneous_fall": detected,
                "instantaneous_confidence": float(confidence),
                "confirmed_fall": bool(active),
                "confirmed_confidence": float(confirmed_confidence),
                "model_confidence": (
                    float(selected["model_confidence"])
                    if selected is not None else 0.0
                ),
                "posture_score": (
                    None if selected is None or selected["posture_score"] is None
                    else float(selected["posture_score"])
                ),
                "torso_angle": (
                    None if selected is None or selected["torso_angle"] is None
                    else float(selected["torso_angle"])
                ),
                "center_y": (
                    None if selected is None else float(selected["center_y"])
                ),
                **tracking,
                **state,
            })

        if stream_id is None:
            confidence = max(instantaneous_confidences, default=0.0)
            return bool(instantaneous_confidences), confidence, caixas

        with self._state_lock:
            self._last_diagnostics[str(stream_id)] = deepcopy(diagnostics)

        confidence = max(
            (item[1] for item in confirmed_views),
            default=0.0,
        )
        return bool(confirmed_views), confidence, caixas
