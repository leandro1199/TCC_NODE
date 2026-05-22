const bcrypt = require('bcrypt');
const { admin, dbFirestore } = require('../config/firebaseAdmin');

/* =========================
   LOGIN TRADICIONAL (FIRESTORE)
========================= */
const login = async (req, res) => {
  const { email, senha } = req.body;

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
  const { nome, email, senha } = req.body;

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
  firebaseLogin
};