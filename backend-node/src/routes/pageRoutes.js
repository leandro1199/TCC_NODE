const express = require('express');
const router = express.Router();

const requireAuth = require('../middlewares/autoMiddleware');


// ===== PÁGINA PRINCIPAL =====

router.get('/', (req, res) => {

  if (req.session.usuario) {
    return res.redirect('/paginainicial');
  }

  res.render('apresentpj');
});


// ===== LOGIN =====

router.get('/login', (req, res) => {

  if (req.session.usuario) {
    return res.redirect('/paginainicial');
  }

  res.render('login_cadastro');
});


// ===== PÁGINA INICIAL =====

router.get('/paginainicial', requireAuth, (req, res) => {
  res.render('paginainicial');
});


// ===== PÁGINAS PRIVADAS =====

router.get('/camerapc', requireAuth, (req, res) => {
  res.render('camerapc');
});

router.get('/cameraseg', requireAuth, (req, res) => {
  res.render('cameraseg');
});

const {
  listarCameras,
  cadastrarCamera
} = require('../controllers/cameraController');

router.get('/cameras', requireAuth, listarCameras);
router.post('/cameras', requireAuth, cadastrarCamera);

module.exports = router;