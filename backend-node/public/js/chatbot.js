document.addEventListener('DOMContentLoaded', () => {
  console.log('chatbot.js carregado');

  const chatbotBox = document.getElementById('chatbotBox');
  const abrirChat = document.getElementById('abrirChat');
  const fecharChat = document.getElementById('fecharChat');
  const chatForm = document.getElementById('chatForm');
  const mensagemInput = document.getElementById('mensagemInput');
  const chatMessages = document.getElementById('chatMessages');

  if (!chatbotBox || !abrirChat || !fecharChat || !chatForm || !mensagemInput || !chatMessages) {
    console.error('Elementos do chatbot não encontrados');
    return;
  }

  abrirChat.addEventListener('click', () => {
    chatbotBox.style.display = 'flex';
    abrirChat.style.display = 'none';
  });

  fecharChat.addEventListener('click', () => {
    chatbotBox.style.display = 'none';
    abrirChat.style.display = 'block';
  });

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const mensagem = mensagemInput.value.trim();
    if (!mensagem) return;

    adicionarMensagem(mensagem, 'user-msg');
    mensagemInput.value = '';

    try {
      const response = await fetch('/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ mensagem })
      });

      const data = await response.json();

      adicionarMensagem(data.resposta || 'Não consegui responder agora.', 'bot-msg');

    } catch (error) {
      console.error(error);
      adicionarMensagem('Erro ao conectar com o chatbot.', 'bot-msg');
    }
  });

  function adicionarMensagem(texto, classe) {
    const div = document.createElement('div');
    div.className = classe;
    div.textContent = texto;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
});