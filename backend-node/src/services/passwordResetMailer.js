const escaparHtml = (texto = '') => String(texto)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

const enviarEmailRedefinicao = async ({ destinatario, nome, link }) => {
  const apiKey = process.env.RESEND_API_KEY;
  const remetente = process.env.EMAIL_FROM;

  if (!apiKey || !remetente) {
    console.warn('E-mail de recuperação não enviado: configure RESEND_API_KEY e EMAIL_FROM.');
    return false;
  }

  const nomeSeguro = escaparHtml(nome || 'usuário');
  const linkSeguro = escaparHtml(link);

  const resposta = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'User-Agent': 'ai-health-password-reset/1.0'
    },
    body: JSON.stringify({
      from: remetente,
      to: [destinatario],
      subject: 'Redefinição de senha - AI Health',
      html: `
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#0f172a">
          <h1 style="color:#2563eb">Redefinição de senha</h1>
          <p>Olá, ${nomeSeguro}.</p>
          <p>Recebemos uma solicitação para redefinir sua senha na AI Health.</p>
          <p style="margin:32px 0">
            <a href="${linkSeguro}" style="background:#2563eb;color:#fff;padding:14px 22px;border-radius:999px;text-decoration:none;font-weight:bold">
              Criar nova senha
            </a>
          </p>
          <p>O link é válido por 30 minutos e só pode ser utilizado uma vez.</p>
          <p>Se você não solicitou a alteração, ignore este e-mail.</p>
        </div>
      `
    })
  });

  if (!resposta.ok) {
    const detalhe = await resposta.text();
    throw new Error(`Falha ao enviar e-mail de recuperação (${resposta.status}): ${detalhe}`);
  }

  return true;
};

module.exports = { enviarEmailRedefinicao };
