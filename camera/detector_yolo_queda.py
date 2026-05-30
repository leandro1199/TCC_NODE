from ultralytics import YOLO


class DetectorYOLOQueda:

    def __init__(self):
        self.modelo = YOLO(
            r"D:\TCC_DNV\runs\detect\train\weights\best.pt"
        )

        self.confianca_minima = 0.50

    def detectar(self, frame):
        resultados = self.modelo(frame, verbose=False)

        queda_detectada = False
        maior_confianca = 0
        caixas = []

        for resultado in resultados:
            for box in resultado.boxes:
                classe = int(box.cls[0])
                nome_classe = resultado.names[classe]
                conf = float(box.conf[0])

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                if "fall" in nome_classe.lower():
                    caixas.append((x1, y1, x2, y2, conf))

                    if conf > maior_confianca:
                        maior_confianca = conf

        if maior_confianca >= self.confianca_minima:
            queda_detectada = True

        return queda_detectada, maior_confianca, caixas