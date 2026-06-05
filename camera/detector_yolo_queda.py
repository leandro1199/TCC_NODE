from ultralytics import YOLO


class DetectorYOLOQueda:

    def __init__(self):
        self.modelo = YOLO("C:\\TCC_NODE\\runs\\pose\\train\\weights\\best.pt")
        self.confianca_minima = 0.40

    def detectar(self, frame):
        resultados = self.modelo(frame, verbose=False)

        pessoa_detectada = False
        maior_confianca = 0
        caixas = []

        for resultado in resultados:
            for box in resultado.boxes:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                if conf >= self.confianca_minima:
                    pessoa_detectada = True
                    caixas.append((x1, y1, x2, y2, conf))

                    if conf > maior_confianca:
                        maior_confianca = conf

        return pessoa_detectada, maior_confianca, caixas