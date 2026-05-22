const express = require("express");
const router = express.Router();
const relatorioController = require("../controllers/relatorioController");

function verificarLogin(req, res, next) {
    if (!req.session.usuario) {
        return res.redirect("/login");
    }
    next();
}

router.get("/relatorios", verificarLogin, relatorioController.listarRelatorios);

module.exports = router;