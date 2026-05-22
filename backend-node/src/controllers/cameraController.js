const db = require("../config/db");

async function listarCameras(req, res) {
    try {
        const usuarioId = req.session.usuario.id;

        const [cameras] = await db.query(
            "SELECT * FROM cameras WHERE usuario_id = ? ORDER BY criada_em DESC",
            [usuarioId]
        );

        res.render("cameras", {
            usuario: req.session.usuario,
            cameras
        });
    } catch (erro) {
        console.error("Erro ao listar câmeras:", erro);
        res.status(500).send("Erro ao listar câmeras.");
    }
}

async function cadastrarCamera(req, res) {
    try {
        const usuarioId = req.session.usuario.id;
        const { nome, rtsp_url } = req.body;

        await db.query(
            `INSERT INTO cameras 
            (usuario_id, nome, rtsp_url, status_camera)
            VALUES (?, ?, ?, ?)`,
            [usuarioId, nome, rtsp_url, "offline"]
        );

        res.redirect("/cameras");
    } catch (erro) {
        console.error("Erro ao cadastrar câmera:", erro);
        res.status(500).send("Erro ao cadastrar câmera.");
    }
}

module.exports = {
    listarCameras,
    cadastrarCamera
};