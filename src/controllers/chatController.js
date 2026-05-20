const axios = require('axios');
const { dbFirestore, admin } = require('../config/firebaseAdmin');

exports.chat = async (req, res) => {
  const { mensagem } = req.body;
  const usuario = req.session.usuario;

  if (!usuario) {
    return res.status(401).json({
      resposta: 'Usuário não autenticado.'
    });
  }

  if (!mensagem || !mensagem.trim()) {
    return res.status(400).json({
      resposta: 'Digite uma mensagem válida.'
    });
  }

  try {
    const usuarioId = usuario.uid || usuario.id;

    // Buscar último contexto no Firestore
    const snapshot = await dbFirestore
      .collection('interacoes')
      .where('usuario_id', '==', usuarioId)
      .orderBy('criado_em', 'desc')
      .limit(1)
      .get();

    const contexto_anterior = snapshot.empty
      ? null
      : snapshot.docs[0].data().intent_detectada;

    // Chamar API Python
    const pythonUrl = process.env.PYTHON_API_URL?.replace(/\/$/, '');

        if (!pythonUrl) {
          return res.status(500).json({
            resposta: 'API Python não configurada.'
          });
        }

        const response = await axios.post(`${pythonUrl}/chat`, {
          mensagem,
          usuario_id: usuarioId,
          contexto_anterior
        }, {
          timeout: 15000
        });

    const response = await axios.post(`${pythonUrl}/chat`, {
      mensagem,
      usuario_id: usuarioId,
      contexto_anterior
    }, {
      timeout: 15000
    });

    const resposta = response.data.resposta || 'Não consegui responder agora.';
    const intent = response.data.contexto || response.data.intent || 'desconhecida';
    const confianca = response.data.confianca || 0;

    // Salvar interação no Firestore
    await dbFirestore.collection('interacoes').add({
      usuario_id: usuarioId,
      pergunta_usuario: mensagem,
      resposta_bot: resposta,
      intent_detectada: intent,
      fallback_usado: intent === 'fallback' ? 'sim' : 'nao',
      confianca,
      criado_em: admin.firestore.FieldValue.serverTimestamp()
    });

    return res.json({ resposta });

  } catch (error) {
    console.error('Erro no chatController:', error);

    return res.status(500).json({
      resposta: 'Erro ao conectar com IA.'
    });
  }
};