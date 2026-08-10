# Sistema Inteligente de Monitoramento para Idosos

Projeto desenvolvido como Trabalho de Conclusão de Curso (TCC).

## Objetivo

Desenvolver um sistema capaz de monitorar idosos em tempo real utilizando câmeras IP, inteligência artificial e Firebase, permitindo a identificação automática de situações de risco, como quedas.

## Tecnologias Utilizadas

- Python
- Flask
- Firebase
- OpenCV
- MediaPipe
- FFmpeg
- HTML/CSS/JavaScript
- MySQL

## Estrutura do Projeto

```text
camera/
├── api_camera.py
├── detector_queda.py
├── firebase-key.json
└── testes/
```

## Funcionalidades

- Monitoramento de câmeras IP (RTSP)
- Detecção automática de quedas
- Integração com Firebase
- Alertas em tempo real
- Streaming de vídeo

## Instalação

Clone o projeto:

```bash
git clone <url-do-repositorio>
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Para treinamento com uma GPU NVIDIA compatível, instale também o PyTorch
com CUDA:

```bash
python -m pip install -r requirements-gpu.txt
```

O script `treinar_yolo_pose.py` seleciona automaticamente a primeira GPU
CUDA disponível. O dispositivo também pode ser definido explicitamente:

```powershell
$env:YOLO_DEVICE = "0"
python treinar_yolo_pose.py
```

Para retomar um treinamento interrompido pelo último checkpoint:

```powershell
$env:YOLO_DEVICE = "0"
$env:YOLO_RESUME_CHECKPOINT = "..\runs\pose\fall_pose_v2\weights\last.pt"
python treinar_yolo_pose.py
```

Ao migrar uma execução iniciada em CPU para CUDA, o script cria
automaticamente uma cópia `last-gpu.pt` compatível com AMP e preserva o
checkpoint original.

Execute a aplicação:

```bash
python api_camera.py
```

## Autor

Leandro Bernardo de Souza
