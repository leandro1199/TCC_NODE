import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, GoogleAuthProvider } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

// Config do Firebase
const firebaseConfig = {
  apiKey: "AIzaSyAvFH-3kQDgFM_xhueEHALmHqv41zoriT4",
  authDomain: "tccveio.firebaseapp.com",
  projectId: "tccveio",
  storageBucket: "tccveio.firebasestorage.app",
  messagingSenderId: "1065848972952",
  appId: "1:1065848972952:web:b6115a58f99546a04612ed",
  measurementId: "G-FJJ2XF70E2"
};

// Inicializa Firebase
const app = initializeApp(firebaseConfig);

// Auth
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();