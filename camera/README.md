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
- EJS/CSS/JavaScript
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

## Teste com câmera real em modo offline

Por padrão, a API usa a webcam local de índice `0`, processa os frames no
próprio computador e não acessa o Firebase. Execute:

```powershell
cd camera
..\.venv-camera\Scripts\python.exe api_camera.py
```

Abra `http://127.0.0.1:5002/video_feed/offline` ou a página `/cameraseg` da
aplicação Node. Para escolher outra webcam:

```powershell
$env:CAMERA_OFFLINE_SOURCE = "1"
..\.venv-camera\Scripts\python.exe api_camera.py
```

Uma câmera IP na mesma rede local também pode ser usada sem internet:

```powershell
$env:CAMERA_OFFLINE_SOURCE = "rtsp://192.168.1.50:554/stream1"
$env:CAMERA_RTSP_USER = "usuario"
$env:CAMERA_RTSP_PASSWORD = "senha"
..\.venv-camera\Scripts\python.exe api_camera.py
```

Em fontes RTSP, a API usa automaticamente o VLC instalado no computador para
compatibilidade com câmeras que não funcionam no FFmpeg/OpenCV. Defina
`VLC_PATH` se o VLC estiver fora do diretório padrão. Para forçar o OpenCV,
use `CAMERA_RTSP_BACKEND=opencv`.

Para a câmera configurada atualmente em `192.168.1.5`, use o inicializador
seguro. Ele abre o substream `/onvif2` e solicita a senha sem salvá-la:

```powershell
cd camera
.\iniciar_camera_offline.ps1
```

Para usar o stream principal, execute
`.\iniciar_camera_offline.ps1 -Perfil onvif1`.

### Gravações de teste

O gravador abre a prévia da câmera, aguarda o primeiro frame e mostra uma
contagem regressiva de três segundos antes de gravar. A senha deve ser
informada apenas pela variável de ambiente da sessão:

```powershell
$env:CAMERA_RTSP_USER = "admin"
$env:CAMERA_RTSP_PASSWORD = "senha"
python gravar_camera_vlc.py --numero 1 --duracao 10 --contagem 3
```

Os vídeos são salvos em `camera/gravacoes`. Se o nome já existir, o gravador
adiciona data e hora ao novo arquivo sem sobrescrever a gravação anterior.

Para voltar ao cadastro de câmeras pelo Firebase, defina `CAMERA_MODE=online`.

## Autor

Leandro Bernardo de Souza
