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
- Alerta de queda por e-mail e WhatsApp com imagem e mini relatório
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

## Câmeras com duas lentes no mesmo quadro

O detector reconhece automaticamente o formato vertical usado pela câmera de
teste, no qual as duas lentes aparecem empilhadas em um quadro de 640x720. Cada
metade é processada como uma visão independente, com histórico temporal e
rastreamento próprios. Isso evita que a alternância entre as duas imagens seja
interpretada como deslocamento vertical de uma queda.

O comportamento pode ser controlado no `backend-node/.env`:

```env
# auto, single ou vertical_dual
YOLO_FRAME_LAYOUT=auto
```

Use `single` quando uma câmera vertical comum for identificada incorretamente
como câmera dupla. Use `vertical_dual` para forçar a separação das duas lentes.

## Avaliação com vídeos rotulados

Edite `camera/rotulos_videos.json` e informe, para cada vídeo, se ocorreu uma
queda e o instante real em que ela começou. Enquanto `queda` estiver como
`null`, o vídeo será processado, mas não entrará nas métricas de acerto.

Depois, processe os vídeos:

```powershell
cd camera
..\.venv-camera\Scripts\python.exe analisar_videos_queda.py `
  gravacoes\video_1.mp4 gravacoes\video_2.mp4 `
  gravacoes\video_3.mp4 gravacoes\video_4.mp4
```

Além do vídeo anotado e de `metricas_por_frame.csv`, a análise gera
`metricas_por_view.csv`, com ângulo do tronco, posição vertical, continuidade do
rastreamento, transições e estado da confirmação para cada lente. O resumo
calcula precisão, sensibilidade, especificidade, acurácia e atraso médio somente
quando houver rótulos preenchidos.

## Alertas de queda por e-mail e WhatsApp

A API cria um único evento quando a queda é confirmada. O evento contém:

- imagem JPEG do momento detectado;
- nome e identificador da câmera;
- data e hora no fuso configurado;
- confiança da detecção;
- mini relatório com orientação para verificação imediata.

O processamento ocorre em segundo plano para não interromper o vídeo. Novos
alertas da mesma transmissão respeitam `ALERT_COOLDOWN_SECONDS` (60 segundos
por padrão). No modo online, o evento também é salvo em `relatorios_queda` no
Firestore, incluindo o resultado de cada canal.

As configurações ficam no mesmo `backend-node/.env` usado pelo site. Copie as
variáveis de `backend-node/.env.example`. Para o primeiro teste seguro, use:

```env
ALERTS_ENABLED=true
ALERT_DRY_RUN=true
ALERT_EMAIL_TO=seu-email@example.com
ALERT_WHATSAPP_TO=5511999999999
```

Com `ALERT_DRY_RUN=true`, o relatório e os payloads são montados, mas nenhuma
requisição externa é enviada. Depois da validação, altere para `false`.

O e-mail usa `RESEND_API_KEY` e `EMAIL_FROM` e leva a imagem anexada e exibida
no corpo. O WhatsApp usa a Cloud API oficial da Meta e requer:

```env
WHATSAPP_ACCESS_TOKEN=seu_token
WHATSAPP_PHONE_NUMBER_ID=seu_phone_number_id
WHATSAPP_GRAPH_API_VERSION=v23.0
```

Para um alerta iniciado automaticamente pelo sistema, crie e aprove no
WhatsApp Manager um template chamado `alerta_queda_ai_health`, com cabeçalho
do tipo imagem e cinco variáveis de texto no corpo, nesta ordem:

1. câmera;
2. data;
3. hora;
4. confiança;
5. mini relatório.

Configure então:

```env
WHATSAPP_TEMPLATE_NAME=alerta_queda_ai_health
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
```

Sem um template, a integração envia uma mensagem de imagem direta, apropriada
somente quando houver uma janela de atendimento aberta no WhatsApp.

Execute os testes sem chamadas reais:

```powershell
python -m unittest camera.testes.test_alerta_queda -v
```

Com a API iniciada, consulte `http://127.0.0.1:5002/status_alertas` para
confirmar se os dois canais estão configurados. A rota nunca mostra tokens,
e-mails ou números de telefone.

## Autor

Leandro Bernardo de Souza
