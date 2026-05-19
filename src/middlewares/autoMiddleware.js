module.exports = function (req, res, next) {
  if (!req.session.usuario) {
    return res.redirect('/login'); // manda para tela de login
  }
  next();
};