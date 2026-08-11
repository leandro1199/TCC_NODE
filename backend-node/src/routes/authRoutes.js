const express = require('express');
const router = express.Router();

const authController = require('../controllers/authController');

// login tradicional
router.post('/login', authController.login);
router.post('/cadastro', authController.cadastro);
router.get('/logout', authController.logout);

// redefinição de senha
router.post('/esqueci-senha', authController.solicitarRedefinicaoSenha);
router.get('/redefinir-senha', authController.exibirRedefinicaoSenha);
router.post('/redefinir-senha', authController.redefinirSenha);

// 🔐 Firebase Google login (NOVO)
router.post('/firebase-login', authController.firebaseLogin);

module.exports = router;
