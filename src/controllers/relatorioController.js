const db = require("../config/db");

exports.listarRelatorios = async (req, res) => {
    try {
        const usuarioId = req.session.usuario.id;

        const [relatorios] = await db.query(
            `SELECT 
                relatorios.id,
                relatorios.tipo_evento,
                relatorios.descricao,
                relatorios.confianca,
                relatorios.imagem_url,
                relatorios.criado_em,
                cameras.nome AS nome_camera
             FROM relatorios
             LEFT JOIN cameras ON relatorios.camera_id = cameras.id
             WHERE relatorios.usuario_id = ?
             ORDER BY relatorios.criado_em DESC`,
            [usuarioId]
        );

        res.render("relatorios", {
            usuario: req.session.usuario,
            relatorios
        });
    } catch (erro) {
        console.error("Erro ao listar relatórios:", erro);
        res.status(500).send("Erro ao listar relatórios.");
    }
};