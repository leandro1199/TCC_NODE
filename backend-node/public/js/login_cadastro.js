const signUpButton = document.getElementById('signUp');
const signInButton = document.getElementById('signIn');
const container = document.getElementById('container');

if (signUpButton && signInButton && container) {

  signUpButton.addEventListener('click', () => {
    container.classList.add('right-panel-active');
  });

  signInButton.addEventListener('click', () => {
    container.classList.remove('right-panel-active');
  });

}

const modalRecuperacao = document.getElementById('modalRecuperacao');
const abrirRecuperacao = document.getElementById('abrirRecuperacao');
const botoesFecharRecuperacao = document.querySelectorAll('[data-fechar-recuperacao]');
const emailLogin = document.querySelector('.sign-in-container input[name="email"]');
const emailRecuperacao = document.getElementById('emailRecuperacao');

const definirModalRecuperacao = (aberto) => {
  if (!modalRecuperacao) return;

  modalRecuperacao.classList.toggle('is-open', aberto);
  modalRecuperacao.setAttribute('aria-hidden', String(!aberto));
  document.body.classList.toggle('modal-aberto', aberto);

  if (aberto) {
    if (emailRecuperacao && emailLogin?.value && !emailRecuperacao.value) {
      emailRecuperacao.value = emailLogin.value;
    }

    emailRecuperacao?.focus();
  } else {
    abrirRecuperacao?.focus();
  }
};

abrirRecuperacao?.addEventListener('click', (event) => {
  event.preventDefault();
  definirModalRecuperacao(true);
});

botoesFecharRecuperacao.forEach((botao) => {
  botao.addEventListener('click', () => definirModalRecuperacao(false));
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && modalRecuperacao?.classList.contains('is-open')) {
    definirModalRecuperacao(false);
  }
});

if (modalRecuperacao?.classList.contains('is-open')) {
  document.body.classList.add('modal-aberto');
}
