const db = require('../config/db');
const axios = require('axios');

exports.chat = async (req, res) => {
  const { mensagem } = req.body;
  const usuario = req.session.usuario;

  if (!usuario) {
    return res.status(401).json({
      resposta: 'Usuário não autenticado.'
    });
  }

  try {
    // 🔥 BUSCAR CONTEXTO ANTERIOR
    const [rows] = await db.execute(
      `SELECT intent_detectada 
       FROM interacoes 
       WHERE usuario_id = ? 
       ORDER BY criado_em DESC 
       LIMIT 1`,
      [usuario.id]
    );

    const contexto_anterior = rows.length > 0 ? rows[0].intent_detectada : null;

    // 🔥 CHAMAR PYTHON
    const response = await axios.post('http://127.0.0.1:5001/chat', {
      mensagem,
      usuario_id: usuario.id,
      contexto_anterior
    });

    const resposta = response.data.resposta;
    const intent = response.data.contexto || 'desconhecida';

    // 🔥 SALVAR NO BANCO
    await db.execute(
      `INSERT INTO interacoes 
      (usuario_id, pergunta_usuario, resposta_bot, intent_detectada, fallback_usado, confianca)
      VALUES (?, ?, ?, ?, ?, ?)`,
      [
        usuario.id,
        mensagem,
        resposta,
        intent,
        intent === 'fallback' ? 'sim' : 'nao',
        1.0
      ]
    );

    return res.json({ resposta });

  } catch (error) {
    console.error(error);
    return res.json({ resposta: 'Erro ao conectar com IA.' });
  }
};