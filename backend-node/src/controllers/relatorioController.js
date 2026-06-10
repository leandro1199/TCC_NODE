const admin = require("firebase-admin");

const db = admin.firestore();

exports.listarRelatorios = async (req, res) => {
    try {
        const snapshot = await db
            .collection("relatorios_queda")
            .orderBy("criadoEm", "desc")
            .get();

        const relatorios = [];

        snapshot.forEach(doc => {
            const dados = doc.data();

            relatorios.push({
                id: doc.id,

                tipo_evento: "Queda detectada",
                descricao: "Queda detectada automaticamente pela inteligência artificial.",

                confianca: dados.confianca || 0,

                imagem_url: dados.imagem
                    ? `data:image/jpeg;base64,${dados.imagem}`
                    : null,

                criado_em: dados.dataHora || "Data não registrada",

                nome_camera: dados.cameraNome || "Câmera removida"
            });
        });

        res.render("relatorios", {
            usuario: req.session.usuario,
            relatorios
        });

    } catch (erro) {
        console.error("Erro ao listar relatórios:", erro);
        res.status(500).send("Erro ao listar relatórios.");
    }
};s