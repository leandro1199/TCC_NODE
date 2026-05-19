const db = require('../config/db');
const bcrypt = require('bcrypt');

// 🔐 Firebase Admin
const { admin } = require('../config/firebaseAdmin');

/* =========================
   LOGIN TRADICIONAL (MYSQL)
========================= */
const login = async (req, res) => {
  const { email, senha } = req.body;

  try {
    const [rows] = await db.execute(
      'SELECT * FROM usuarios WHERE email = ?',
      [email]
    );

    if (rows.length === 0) {
      return res.send('Usuário não encontrado');
    }

    const usuario = rows[0];

    const senhaCorreta = await bcrypt.compare(senha, usuario.senha);

    if (!senhaCorreta) {
      return res.send('Senha incorreta');
    }

    req.session.usuario = {
      id: usuario.id,
      nome: usuario.nome,
      email: usuario.email
    };

    return res.redirect('/');

  } catch (err) {
    console.error(err);
    return res.send('Erro ao fazer login');
  }
};


/* =========================
   CADASTRO TRADICIONAL
========================= */
const cadastro = async (req, res) => {
  const { nome, email, senha } = req.body;

  console.log('DADOS RECEBIDOS NO CADASTRO:', req.body);

  if (!nome || !email || !senha) {
    return res.send('Erro: nome, email ou senha não chegaram do formulário.');
  }

  try {
    const senhaHash = await bcrypt.hash(senha, 10);

    const [resultado] = await db.execute(
      'INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)',
      [nome, email, senhaHash]
    );

    console.log('USUÁRIO CADASTRADO COM ID:', resultado.insertId);

    return res.redirect('/login');

  } catch (err) {
    console.error('ERRO AO CADASTRAR:', err);
    return res.send('Erro ao cadastrar usuário: ' + err.message);
  }
};


/* =========================
   LOGOUT
========================= */
const logout = (req, res) => {
  req.session.destroy(() => {
    res.redirect('/');
  });
};


/* =========================
   LOGIN GOOGLE (FIREBASE)
========================= */
const firebaseLogin = async (req, res) => {
  try {
    const { idToken } = req.body;

    if (!idToken) {
      return res.status(400).json({
        sucesso: false,
        erro: "Token ausente"
      });
    }

    // 🔐 valida token Firebase
    const decoded = await admin.auth().verifyIdToken(idToken);

    const uid = decoded.uid;
    const email = decoded.email;
    const nome = decoded.name || "Usuário Google";

    // 🧠 verifica se existe no MySQL
    const [rows] = await db.execute(
      'SELECT * FROM usuarios WHERE email = ?',
      [email]
    );

    let userId;

    if (rows.length === 0) {
      const [result] = await db.execute(
        'INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)',
        [nome, email, 'GOOGLE_AUTH']
      );

      userId = result.insertId;
    } else {
      userId = rows[0].id;
    }

    // 🍪 sessão unificada
    req.session.usuario = {
      id: userId,
      nome,
      email,
      uidFirebase: uid
    };

    return res.json({ sucesso: true });

  } catch (err) {
    console.error('firebaseLogin error:', err);

    return res.status(401).json({
      sucesso: false,
      erro: "Token inválido"
    });
  }
};


/* =========================
   EXPORT
========================= */
module.exports = {
  login,
  cadastro,
  logout,
  firebaseLogin
};