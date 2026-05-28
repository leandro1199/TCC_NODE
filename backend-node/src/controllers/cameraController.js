const { admin, dbFirestore } = require('../config/firebaseAdmin');

async function listarCameras(req, res) {
  try {
    const usuarioId = req.session.usuario.uid || req.session.usuario.id;

    const snapshot = await dbFirestore
      .collection('cameras')
      .where('usuario_id', '==', usuarioId)
      .get();

    const cameras = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    }));

    cameras.sort((a, b) => {
      const dataA = a.criado_em?.toMillis?.() || 0;
      const dataB = b.criado_em?.toMillis?.() || 0;
      return dataB - dataA;
    });

    res.render('cameras', {
      usuario: req.session.usuario,
      cameras
    });

  } catch (erro) {
    console.error('Erro ao listar câmeras:', erro);
    res.status(500).send('Erro ao listar câmeras.');
  }
}

async function cadastrarCamera(req, res) {
  try {
    const usuarioId = req.session.usuario.uid || req.session.usuario.id;
    const { nome, rtsp_url } = req.body;

    if (!nome || !rtsp_url) {
      return res.send('Nome e URL RTSP são obrigatórios.');
    }

    await dbFirestore.collection('cameras').add({
      usuario_id: usuarioId,
      nome,
      rtsp_url,
      status_camera: 'offline',
      criado_em: admin.firestore.FieldValue.serverTimestamp()
    });

    res.redirect('/cameras');

  } catch (erro) {
    console.error('Erro ao cadastrar câmera:', erro);
    res.status(500).send('Erro ao cadastrar câmera.');
  }
}

module.exports = {
  listarCameras,
  cadastrarCamera
};