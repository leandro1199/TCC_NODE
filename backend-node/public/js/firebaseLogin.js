import { auth, googleProvider } from './firebaseConfig.js';
import { signInWithPopup } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const botoesGoogle = document.querySelectorAll('.googleLoginBtn');

botoesGoogle.forEach((btnGoogle) => {

  btnGoogle.addEventListener('click', async (e) => {

    e.preventDefault();

    try {

      const result = await signInWithPopup(auth, googleProvider);

      const idToken = await result.user.getIdToken();

      const response = await fetch('/firebase-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idToken })
      });

      const data = await response.json();

      if (data.sucesso) {
        window.location.href = '/paginainicial';
      } else {
        alert('Erro ao criar sessão');
      }

    } catch (error) {
      console.error(error);
      alert('Erro no login com Google');
    }

  });

});