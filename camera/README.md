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

Execute a aplicação:

```bash
python api_camera.py
```

## Autor

Leandro Bernardo de Souza