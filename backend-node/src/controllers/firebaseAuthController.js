const { admin, dbFirestore } = require('../config/firebaseAdmin');

exports.firebaseLogin = async (req, res) => {
  const { idToken } = req.body;

  try {
    // 1️⃣ validar token vindo do Firebase
    const decodedToken = await admin.auth().verifyIdToken(idToken);
    const uid = decodedToken.uid;
    const email = decodedToken.email;
    const nome = decodedToken.name || 'Usuário';

    // 2️⃣ CRIAR USUÁRIO NO FIRESTORE AUTOMATICAMENTE
    const userRef = dbFirestore.collection('usuarios').doc(uid);
    const doc = await userRef.get();

    if (!doc.exists) {
      await userRef.set({
        nome,
        email,
        criado_em: new Date()
      });
      console.log('Usuário criado no Firestore');
    }

// busca usuário mysql
    const [rows] = await db.execute(
      'SELECT * FROM usuarios WHERE email = ?',
      [email]
    );

    let userId;

    if (rows.length === 0) {

      const [result] = await db.execute(
        'INSERT INTO usuarios (nome, email, senha) VALUES (?, ?, ?)',
        [nome, email, 'FIREBASE_AUTH']
      );

      userId = result.insertId;

    } else {
      userId = rows[0].id;
    }

    req.session.usuario = {
      id: userId,
      uidFirebase: uid,
      nome,
      email
    };

    res.json({ sucesso: true });

  } catch (error) {
    console.error(error);
    res.status(401).json({ erro: 'Token inválido' });
  }
};