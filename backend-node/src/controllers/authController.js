const bcrypt = require('bcrypt');
const crypto = require('crypto');
const { admin, dbFirestore } = require('../config/firebaseAdmin');
const { enviarEmailRedefinicao } = require('../services/passwordResetMailer');

const DURACAO_TOKEN_REDEFINICAO_MS = 30 * 60 * 1000;

const normalizarEmail = (email = '') => email.trim().toLowerCase();
const emailValido = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

const hashToken = (token) => crypto
  .createHash('sha256')
  .update(token)
  .digest('hex');

const urlBase = (req) => {
  const appUrl = process.env.APP_URL?.trim().replace(/\/$/, '');
  return appUrl || `${req.protocol}://${req.get('host')}`;
};

const buscarUsuarioPorToken = async (token) => {
  if (!/^[a-f0-9]{64}$/i.test(token || '')) {
    return null;
  }

  const tokenHash = hashToken(token);
  const snapshot = await dbFirestore
    .collection('usuarios')
    .where('redefinicao_senha.tokenHash', '==', tokenHash)
    .limit(1)
    .get();

  if (snapshot.empty) {
    return null;
  }

  const documento = snapshot.docs[0];
  const dados = documento.data();
  const redefinicao = dados.redefinicao_senha;
  const expiraEm = redefinicao?.expiraEm?.toMillis?.() || 0;

  if (!redefinicao || expiraEm <= Date.now()) {
    return null;
  }

  return { documento, tokenHash };
};

/* =========================
   LOGIN TRADICIONAL (FIRESTORE)
========================= */
const login = async (req, res) => {
  const email = normalizarEmail(req.body.email);
  const { senha } = req.body;

  try {
    const snapshot = await dbFirestore
      .collection('usuarios')
      .where('email', '==', email)
      .limit(1)
      .get();

    if (snapshot.empty) {
      return res.send('Email ou senha inválidos');
    }

    const doc = snapshot.docs[0];
    const usuario = doc.data();

    if (!usuario.senha) {
      return res.send('Esta conta foi criada com Google. Entre usando o Google.');
    }

    const senhaCorreta = await bcrypt.compare(senha, usuario.senha);

    if (!senhaCorreta) {
      return res.send('Email ou senha inválidos');
    }

    req.session.usuario = {
      id: doc.id,
      uid: doc.id,
      nome: usuario.nome,
      email: usuario.email
    };

    return res.redirect('/paginainicial');

  } catch (err) {
    console.error('Erro ao fazer login:', err);
    return res.send('Erro ao fazer login');
  }
};


/* =========================
   CADASTRO TRADICIONAL (FIRESTORE)
========================= */
const cadastro = async (req, res) => {
  const nome = req.body.nome?.trim();
  const email = normalizarEmail(req.body.email);
  const { senha } = req.body;

  if (!nome || !email || !senha) {
    return res.send('Erro: nome, email ou senha não chegaram do formulário.');
  }

  try {
    const snapshot = await dbFirestore
      .collection('usuarios')
      .where('email', '==', email)
      .limit(1)
      .get();

    if (!snapshot.empty) {
      return res.send('Este email já está cadastrado.');
    }

    const senhaHash = await bcrypt.hash(senha, 10);

    const userRef = await dbFirestore.collection('usuarios').add({
      nome,
      email,
      senha: senhaHash,
      provedor: 'email',
      criado_em: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('Usuário cadastrado no Firestore:', userRef.id);

    return res.redirect('/login');

  } catch (err) {
    console.error('Erro ao cadastrar:', err);
    return res.send('Erro ao cadastrar usuário.');
  }
};


/* =========================
   SOLICITAR REDEFINIÇÃO DE SENHA
========================= */
const solicitarRedefinicaoSenha = async (req, res) => {
  const email = normalizarEmail(req.body.email);
  const mensagemGenerica = 'Se o e-mail estiver cadastrado, você receberá um link para redefinir sua senha.';

  try {
    if (!emailValido(email)) {
      return res.status(400).render('login_cadastro', {
        recuperacao: {
          tipo: 'erro',
          mensagem: 'Informe um e-mail válido.'
        }
      });
    }

    const snapshot = await dbFirestore
      .collection('usuarios')
      .where('email', '==', email)
      .limit(1)
      .get();

    let linkDesenvolvimento = null;

    if (!snapshot.empty) {
      const documento = snapshot.docs[0];
      const usuario = documento.data();

      if (usuario.senha && usuario.provedor !== 'google') {
        const ultimaSolicitacao = usuario.redefinicao_senha?.solicitadoEm?.toMillis?.() || 0;
        const podeSolicitar = Date.now() - ultimaSolicitacao >= 60 * 1000;

        if (podeSolicitar) {
          const token = crypto.randomBytes(32).toString('hex');
          const tokenHash = hashToken(token);
          const link = `${urlBase(req)}/redefinir-senha?token=${encodeURIComponent(token)}`;

          await documento.ref.update({
            redefinicao_senha: {
              tokenHash,
              expiraEm: admin.firestore.Timestamp.fromMillis(
                Date.now() + DURACAO_TOKEN_REDEFINICAO_MS
              ),
              solicitadoEm: admin.firestore.FieldValue.serverTimestamp()
            }
          });

          try {
            const emailEnviado = await enviarEmailRedefinicao({
              destinatario: email,
              nome: usuario.nome,
              link
            });

            if (!emailEnviado) {
              if (process.env.NODE_ENV !== 'production') {
                linkDesenvolvimento = link;
                console.log(`Link de redefinição (desenvolvimento): ${link}`);
              } else {
                await documento.ref.update({
                  'redefinicao_senha.tokenHash': admin.firestore.FieldValue.delete(),
                  'redefinicao_senha.expiraEm': admin.firestore.FieldValue.delete()
                });
              }
            }
          } catch (erroEmail) {
            console.error('Erro ao enviar e-mail de redefinição:', erroEmail);

            if (process.env.NODE_ENV !== 'production') {
              linkDesenvolvimento = link;
              console.log(`Link de redefinição (desenvolvimento): ${link}`);
            } else {
              await documento.ref.update({
                'redefinicao_senha.tokenHash': admin.firestore.FieldValue.delete(),
                'redefinicao_senha.expiraEm': admin.firestore.FieldValue.delete()
              });
            }
          }
        }
      }
    }

    return res.render('login_cadastro', {
      recuperacao: {
        tipo: 'sucesso',
        mensagem: mensagemGenerica,
        linkDesenvolvimento
      }
    });
  } catch (err) {
    console.error('Erro ao solicitar redefinição de senha:', err);
    return res.status(500).render('login_cadastro', {
      recuperacao: {
        tipo: 'erro',
        mensagem: 'Não foi possível iniciar a recuperação agora. Tente novamente mais tarde.'
      }
    });
  }
};


/* =========================
   ABRIR/CONCLUIR REDEFINIÇÃO DE SENHA
========================= */
const exibirRedefinicaoSenha = async (req, res) => {
  const { token = '' } = req.query;

  try {
    const usuarioToken = await buscarUsuarioPorToken(token);

    return res.status(usuarioToken ? 200 : 400).render('redefinir_senha', {
      token,
      tokenValido: Boolean(usuarioToken),
      mensagem: usuarioToken
        ? null
        : 'Este link é inválido ou expirou. Solicite uma nova recuperação de senha.'
    });
  } catch (err) {
    console.error('Erro ao validar link de redefinição:', err);
    return res.status(500).render('redefinir_senha', {
      token: '',
      tokenValido: false,
      mensagem: 'Não foi possível validar o link agora. Tente novamente mais tarde.'
    });
  }
};

const redefinirSenha = async (req, res) => {
  const { token = '', senha = '', confirmarSenha = '' } = req.body;

  if (senha.length < 8) {
    return res.status(400).render('redefinir_senha', {
      token,
      tokenValido: true,
      mensagem: 'A nova senha deve ter pelo menos 8 caracteres.'
    });
  }

  if (senha.length > 128) {
    return res.status(400).render('redefinir_senha', {
      token,
      tokenValido: true,
      mensagem: 'A nova senha deve ter no máximo 128 caracteres.'
    });
  }

  if (senha !== confirmarSenha) {
    return res.status(400).render('redefinir_senha', {
      token,
      tokenValido: true,
      mensagem: 'As senhas informadas não são iguais.'
    });
  }

  try {
    const usuarioToken = await buscarUsuarioPorToken(token);

    if (!usuarioToken) {
      return res.status(400).render('redefinir_senha', {
        token: '',
        tokenValido: false,
        mensagem: 'Este link é inválido ou expirou. Solicite uma nova recuperação de senha.'
      });
    }

    const senhaHash = await bcrypt.hash(senha, 10);

    await dbFirestore.runTransaction(async (transaction) => {
      const snapshotAtual = await transaction.get(usuarioToken.documento.ref);
      const dadosAtuais = snapshotAtual.data();
      const redefinicao = dadosAtuais?.redefinicao_senha;
      const expiraEm = redefinicao?.expiraEm?.toMillis?.() || 0;

      if (
        !snapshotAtual.exists ||
        redefinicao?.tokenHash !== usuarioToken.tokenHash ||
        expiraEm <= Date.now()
      ) {
        throw new Error('TOKEN_INVALIDO');
      }

      transaction.update(usuarioToken.documento.ref, {
        senha: senhaHash,
        redefinicao_senha: admin.firestore.FieldValue.delete(),
        senha_atualizada_em: admin.firestore.FieldValue.serverTimestamp()
      });
    });

    return res.render('redefinir_senha', {
      token: '',
      tokenValido: false,
      sucesso: true,
      mensagem: 'Senha redefinida com sucesso. Você já pode entrar com a nova senha.'
    });
  } catch (err) {
    if (err.message === 'TOKEN_INVALIDO') {
      return res.status(400).render('redefinir_senha', {
        token: '',
        tokenValido: false,
        mensagem: 'Este link já foi usado ou expirou. Solicite uma nova recuperação de senha.'
      });
    }

    console.error('Erro ao redefinir senha:', err);
    return res.status(500).render('redefinir_senha', {
      token,
      tokenValido: true,
      mensagem: 'Não foi possível redefinir a senha agora. Tente novamente mais tarde.'
    });
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
        erro: 'Token ausente'
      });
    }

    const decoded = await admin.auth().verifyIdToken(idToken);

    const uid = decoded.uid;
    const email = decoded.email;
    const nome = decoded.name || 'Usuário Google';
    const foto = decoded.picture || '';

    const userRef = dbFirestore.collection('usuarios').doc(uid);
    const doc = await userRef.get();

    if (!doc.exists) {
      await userRef.set({
        uid,
        nome,
        email,
        foto,
        provedor: 'google',
        criado_em: admin.firestore.FieldValue.serverTimestamp()
      });
    } else {
      await userRef.set({
        uid,
        nome,
        email,
        foto,
        atualizado_em: admin.firestore.FieldValue.serverTimestamp()
      }, { merge: true });
    }

    req.session.usuario = {
      id: uid,
      uid,
      nome,
      email,
      foto
    };

    return res.json({ sucesso: true });

  } catch (err) {
    console.error('firebaseLogin error:', err);

    return res.status(401).json({
      sucesso: false,
      erro: 'Token inválido'
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
  firebaseLogin,
  solicitarRedefinicaoSenha,
  exibirRedefinicaoSenha,
  redefinirSenha
};
