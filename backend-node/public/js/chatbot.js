document.addEventListener('DOMContentLoaded', () => {

  console.log('chatbot.js carregado');

  const chatbotBox = document.getElementById('chatbotBox');
  const abrirChat = document.getElementById('abrirChat');
  const fecharChat = document.getElementById('fecharChat');

  const chatForm = document.getElementById('chatForm');
  const mensagemInput = document.getElementById('mensagemInput');
  const chatMessages = document.getElementById('chatMessages');

  if (
    !chatbotBox ||
    !abrirChat ||
    !fecharChat ||
    !chatForm ||
    !mensagemInput ||
    !chatMessages
  ) {
    console.error('Elementos do chatbot não encontrados');
    return;
  }

  // ABRIR CHAT

  abrirChat.addEventListener('click', () => {

    chatbotBox.style.display = 'flex';
    abrirChat.style.display = 'none';

  });

  // FECHAR CHAT

  fecharChat.addEventListener('click', () => {

    chatbotBox.style.display = 'none';
    abrirChat.style.display = 'block';

  });

  // ENVIAR MENSAGEM

  chatForm.addEventListener('submit', async (e) => {

    e.preventDefault();

    const mensagem = mensagemInput.value.trim();

    if (!mensagem) return;

    adicionarMensagem(mensagem, 'user-msg');

    mensagemInput.value = '';

    try {

      const response = await fetch(
        'https://tcc-node.onrender.com/chat',
        {
          method: 'POST',

          headers: {
            'Content-Type': 'application/json'
          },

          body: JSON.stringify({
            mensagem: mensagem
          })
        }
      );

      // ERRO DA API

      if (!response.ok) {

        adicionarMensagem(
          'Erro ao conectar com a IA.',
          'bot-msg'
        );

        return;
      }

      const data = await response.json();

      adicionarMensagem(
        data.resposta || 'Não consegui responder agora.',
        'bot-msg'
      );

    } catch (error) {

      console.error('Erro:', error);

      adicionarMensagem(
        'Servidor offline ou indisponível.',
        'bot-msg'
      );
    }

  });

  // ADICIONAR MENSAGEM

  function adicionarMensagem(texto, classe) {

    const div = document.createElement('div');

    div.className = classe;

    div.textContent = texto;

    chatMessages.appendChild(div);

    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

});