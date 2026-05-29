import cv2
import mediapipe as mp


class DetectorQueda:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.mp_draw = mp.solutions.drawing_utils

        self.pose = self.mp_pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            min_detection_confidence=0.5
        )

    def analisar_imagem(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resultado = self.pose.process(rgb)

        queda = False
        mensagem = "Pessoa nao detectada"

        if resultado.pose_landmarks:
            pontos = resultado.pose_landmarks.landmark

            ombro_esq = pontos[self.mp_pose.PoseLandmark.LEFT_SHOULDER]
            ombro_dir = pontos[self.mp_pose.PoseLandmark.RIGHT_SHOULDER]
            quadril_esq = pontos[self.mp_pose.PoseLandmark.LEFT_HIP]
            quadril_dir = pontos[self.mp_pose.PoseLandmark.RIGHT_HIP]

            ombro_x = (ombro_esq.x + ombro_dir.x) / 2
            ombro_y = (ombro_esq.y + ombro_dir.y) / 2

            quadril_x = (quadril_esq.x + quadril_dir.x) / 2
            quadril_y = (quadril_esq.y + quadril_dir.y) / 2

            diferenca_x = abs(ombro_x - quadril_x)
            diferenca_y = abs(ombro_y - quadril_y)

            if diferenca_x > diferenca_y:
                queda = True
                mensagem = "Possivel queda detectada"
            else:
                mensagem = "Pessoa em pe ou sentada"

            self.mp_draw.draw_landmarks(
                frame,
                resultado.pose_landmarks,
                self.mp_pose.POSE_CONNECTIONS
            )

        if queda:
            cv2.putText(frame, "QUEDA DETECTADA", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
        else:
            cv2.putText(frame, mensagem, (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        return queda, mensagem, frame