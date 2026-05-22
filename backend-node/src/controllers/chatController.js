const axios = require('axios');
const { dbFirestore, admin } = require('../config/firebaseAdmin');

exports.chat = async (req, res) => {
  const { mensagem } = req.body;
  const usuario = req.session.usuario;

  // Usuário não autenticado
  if (!usuario) {
    return res.status(401).json({
      resposta: 'Usuário não autenticado.'
    });
  }

  // Mensagem vazia
  if (!mensagem || !mensagem.trim()) {
    return res.status(400).json({
      resposta: 'Digite uma mensagem válida.'
    });
  }

  try {
    // UID Firebase ou ID MySQL
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

    // URL da API Python
    const pythonUrl = process.env.PYTHON_API_URL?.replace(/\/$/, '');

    if (!pythonUrl) {
      return res.status(500).json({
        resposta: 'API Python não configurada.'
      });
    }

    // Chamada para API Python
    const pythonResponse = await axios.post(
      `${pythonUrl}/chat`,
      {
        mensagem,
        usuario_id: usuarioId,
        contexto_anterior
      },
      {
        timeout: 15000
      }
    );

    // Dados retornados pela IA
    const resposta =
      pythonResponse.data.resposta ||
      'Não consegui responder agora.';

    const intent =
      pythonResponse.data.contexto ||
      pythonResponse.data.intent ||
      'desconhecida';

    const confianca =
      pythonResponse.data.confianca || 0;

    // Salvar interação no Firestore
    await dbFirestore.collection('interacoes').add({
      usuario_id: usuarioId,
      pergunta_usuario: mensagem,
      resposta_bot: resposta,
      intent_detectada: intent,
      fallback_usado:
        intent === 'fallback' ? 'sim' : 'nao',
      confianca,
      criado_em:
        admin.firestore.FieldValue.serverTimestamp()
    });

    // Resposta final
    return res.json({ resposta });

  } catch (error) {
    console.error('Erro no chatController:', error);

    return res.status(500).json({
      resposta: 'Erro ao conectar com IA.'
    });
  }
};