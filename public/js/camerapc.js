const video = document.getElementById('video');
const canvas = document.getElementById('canvas');

const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const speakBtn = document.getElementById('speakBtn');

const sessaoStatus = document.getElementById('sessaoStatus');
const emocaoAtual = document.getElementById('emocaoAtual');
const confiancaAtual = document.getElementById('confiancaAtual');
const perguntaAtual = document.getElementById('perguntaAtual');
const textoFalado = document.getElementById('textoFalado');
const relatorioFinal = document.getElementById('relatorioFinal');

let stream = null;
let sessaoIniciada = false;

startBtn.addEventListener('click', async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false
    });

    video.srcObject = stream;
    sessaoIniciada = true;

    startBtn.disabled = true;
    stopBtn.disabled = false;
    speakBtn.disabled = false;

    sessaoStatus.textContent = 'Iniciada';
    emocaoAtual.textContent = 'Aguardando análise';
    confiancaAtual.textContent = '---';
    perguntaAtual.textContent = 'Como você está se sentindo agora?';
    textoFalado.textContent = 'Nenhuma fala capturada.';
    relatorioFinal.textContent = 'Sessão em andamento...';

  } catch (error) {
    console.error(error);
    sessaoStatus.textContent = 'Erro ao abrir câmera';
    relatorioFinal.textContent = 'Não foi possível acessar a câmera. Verifique a permissão do navegador.';
  }
});

stopBtn.addEventListener('click', () => {
  if (stream) {
    stream.getTracks().forEach(track => track.stop());
    video.srcObject = null;
  }

  stream = null;
  sessaoIniciada = false;

  startBtn.disabled = false;
  stopBtn.disabled = true;
  speakBtn.disabled = true;

  sessaoStatus.textContent = 'Encerrada';
  emocaoAtual.textContent = '---';
  confiancaAtual.textContent = '---';
  perguntaAtual.textContent = 'Sessão encerrada.';
  textoFalado.textContent = 'Nenhuma fala capturada.';

  relatorioFinal.textContent =
    'Relatório da sessão:\n' +
    '- Câmera encerrada com sucesso.\n' +
    '- Nenhum alerta crítico registrado.\n' +
    '- Nenhuma análise emocional conectada ainda.';
});

speakBtn.addEventListener('click', () => {
  if (!sessaoIniciada) return;

  textoFalado.textContent = 'Função de voz ainda será conectada.';
});