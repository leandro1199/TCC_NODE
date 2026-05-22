const { dbFirestore, admin } = require("../config/firebaseAdmin");
const pool = require("../config/db"); // seu pool mysql

exports.criarUsuarioFirestore = async (req, res) => {
  try {
    const uid = req.usuarioFirebase.uid;
    const email = req.usuarioFirebase.email;
    const nome = req.usuarioFirebase.name || "Usuário";
    const foto = req.usuarioFirebase.picture || "";

    /* ================= FIRESTORE ================= */
    const userRef = dbFirestore.collection("usuarios").doc(uid);
    const doc = await userRef.get();

    if (!doc.exists) {
      await userRef.set({
        uid,
        nome,
        email,
        foto,
        criadoEm: admin.firestore.FieldValue.serverTimestamp()
      });
    }

    /* ================= MYSQL ================= */
    const [rows] = await pool.query(
      "SELECT id FROM usuarios WHERE firebase_uid = ?",
      [uid]
    );

    if (rows.length === 0) {
      await pool.query(
        "INSERT INTO usuarios (nome, email, senha, firebase_uid) VALUES (?, ?, ?, ?)",
        [nome, email, "firebase_auth", uid]
      );
    }

    res.send("Usuário sincronizado nos dois bancos 🔥");
  } catch (error) {
    console.error(error);
    res.status(500).send("Erro ao criar usuário");
  }
};