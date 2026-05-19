const express = require('express');
const router = express.Router();
const requireAuth = require('../middlewares/requireAuth');

// ===== PÁGINAS PÚBLICAS =====
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


// ===== PÁGINAS PRIVADAS (PROTEGIDAS) =====
router.get('/camerapc', requireAuth, (req, res) => {
  res.render('camerapc');
});

router.get('/cameraseg', requireAuth, (req, res) => {
  res.render('cameraseg');
});

module.exports = router;