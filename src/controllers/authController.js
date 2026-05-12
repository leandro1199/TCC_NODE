const db = require('../config/db');
const bcrypt = require('bcrypt');

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

const logout = (req, res) => {
  req.session.destroy(() => {
    res.redirect('/');
  });
};

module.exports = {
  login,
  cadastro,
  logout
};