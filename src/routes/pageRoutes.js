const express = require('express');
const router = express.Router();

function verificarLogin(req, res, next) {
  if (!req.session.usuario) {
    return res.redirect('/login');
  }

  next();
}

// ===== PÁGINAS =====
router.get('/', (req, res) => {
  res.render('paginainicial');
});

router.get('/apresentpj', (req, res) => {
  res.render('apresentpj');
});

router.get('/login', (req, res) => {
  if (req.session.usuario) {
    return res.redirect('/');
  }

  res.render('login_cadastro');
});

router.get('/camerapc', verificarLogin, (req, res) => {
  res.render('camerapc');
});

router.get('/cameraseg', verificarLogin, (req, res) => {
  res.render('cameraseg');
});

module.exports = router;