import cv2
import os
import glob
import random
import shutil

ORIGEM_FALL = r"C:\TCC_NODE\camera\testes\videos\Fall\Raw_Video"
ORIGEM_NO_FALL = r"C:\TCC_NODE\camera\testes\videos\No_Fall\Raw_Video"

SAIDA = r"C:\TCC_NODE\camera\dataset_video"

INTERVALO_FRAMES = 5

def criar_pastas():
    for split in ["train", "val"]:
        for classe in ["Fall", "No_Fall"]:
            os.makedirs(os.path.join(SAIDA, split, classe), exist_ok=True)

def extrair_frames(pasta_videos, classe):
    videos = glob.glob(os.path.join(pasta_videos, "*.mp4"))
    contador = 0

    for video_path in videos:
        cap = cv2.VideoCapture(video_path)
        frame_id = 0

        nome_video = os.path.splitext(os.path.basename(video_path))[0]

        while True:
            ret, frame = cap.read()

            if not ret:
                break

            if frame_id % INTERVALO_FRAMES == 0:
                split = "train" if random.random() < 0.8 else "val"

                nome_frame = f"{classe}_{nome_video}_{frame_id}.jpg"
                caminho_saida = os.path.join(SAIDA, split, classe, nome_frame)

                cv2.imwrite(caminho_saida, frame)
                contador += 1

            frame_id += 1

        cap.release()

    print(f"{classe}: {contador} frames extraídos")

criar_pastas()
extrair_frames(ORIGEM_FALL, "Fall")
extrair_frames(ORIGEM_NO_FALL, "No_Fall")

print("Extração finalizada.")