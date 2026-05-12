const express = require("express");
const router = express.Router();
const cameraController = require("../controllers/cameraController");

function verificarLogin(req, res, next) {
    if (!req.session.usuario) {
        return res.redirect("/login");
    }

    next();
}

router.get("/cameras", verificarLogin, cameraController.listarCameras);
router.post("/cameras", verificarLogin, cameraController.cadastrarCamera);

module.exports = router;