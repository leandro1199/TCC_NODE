const express = require('express');
const path = require('path');
const session = require('express-session');

const app = express();

// TEMPLATE ENGINE
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, '..', 'views'));

// MIDDLEWARES
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// STATIC
app.use(express.static(path.join(__dirname, '..', 'public')));

// SESSION
app.use(
  session({
    secret: process.env.SESSION_SECRET || 'segredo_dev',
    resave: false,
    saveUninitialized: false
  })
);

// USUÁRIO DISPONÍVEL NOS EJS
app.use((req, res, next) => {
  res.locals.usuario = req.session.usuario || null;
  next();
});

// ROTAS
const authRoutes = require('./routes/authRoutes');
const pageRoutes = require('./routes/pageRoutes');
const chatRoutes = require('./routes/chatRoutes');
const cameraRoutes = require('./routes/cameraRoutes');
const relatorioRoutes = require('./routes/relatorioRoutes');

app.use(authRoutes);
app.use(pageRoutes);
app.use(chatRoutes);
app.use(cameraRoutes);
app.use(relatorioRoutes);

// ROTA 404
app.use((req, res) => {
  res.status(404).send('Página não encontrada.');
});

module.exports = app;