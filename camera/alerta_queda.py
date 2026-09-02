"""Criação e envio dos alertas de queda da AI Health."""

import base64
import html
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import cv2
import requests


def _booleano(nome: str, padrao: bool = False) -> bool:
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _lista_emails(valor: str) -> list[str]:
    return [email.strip() for email in valor.split(",") if email.strip()]


def _telefone_whatsapp(valor: str) -> str:
    telefone = re.sub(r"\D", "", valor)
    if telefone and not 10 <= len(telefone) <= 15:
        raise ValueError(
            "ALERT_WHATSAPP_TO deve conter DDI + DDD + número, somente dígitos."
        )
    return telefone


def _fuso_horario() -> ZoneInfo:
    nome = os.getenv("ALERT_TIMEZONE", "America/Sao_Paulo").strip()
    try:
        return ZoneInfo(nome)
    except ZoneInfoNotFoundError:
        return timezone.utc


@dataclass(frozen=True)
class EventoQueda:
    camera_id: str
    camera_nome: str
    confianca: float
    data: str
    hora: str
    data_hora: str
    instante_iso: str
    imagem_jpeg: bytes
    imagem_base64: str
    mini_relatorio: str

    @classmethod
    def criar(
        cls,
        frame,
        camera_id: str,
        camera_nome: str,
        confianca: float,
    ) -> "EventoQueda":
        largura_maxima = max(320, int(os.getenv("ALERT_IMAGE_MAX_WIDTH", "960")))
        altura, largura = frame.shape[:2]
        if largura > largura_maxima:
            escala = largura_maxima / largura
            frame = cv2.resize(
                frame,
                (largura_maxima, int(altura * escala)),
                interpolation=cv2.INTER_AREA,
            )

        qualidade = int(os.getenv("ALERT_IMAGE_QUALITY", "85"))
        qualidade = max(50, min(95, qualidade))
        codificado, buffer = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), qualidade],
        )
        if not codificado:
            raise RuntimeError("Não foi possível codificar a imagem da queda.")

        agora = datetime.now(_fuso_horario())
        confianca_percentual = round(float(confianca) * 100, 2)
        nome = camera_nome or "Câmera não identificada"
        data = agora.strftime("%d/%m/%Y")
        hora = agora.strftime("%H:%M:%S")
        relatorio = (
            f"Queda confirmada pela inteligência artificial na câmera {nome}, "
            f"em {data} às {hora}, com confiança de "
            f"{confianca_percentual:.2f}%. Verifique a pessoa monitorada "
            "imediatamente e acione ajuda se necessário."
        )
        imagem = buffer.tobytes()

        return cls(
            camera_id=str(camera_id),
            camera_nome=nome,
            confianca=confianca_percentual,
            data=data,
            hora=hora,
            data_hora=f"{data} {hora}",
            instante_iso=agora.isoformat(),
            imagem_jpeg=imagem,
            imagem_base64=base64.b64encode(imagem).decode("ascii"),
            mini_relatorio=relatorio,
        )

    def para_firestore(self) -> dict[str, Any]:
        return {
            "cameraId": self.camera_id,
            "cameraNome": self.camera_nome,
            "confianca": self.confianca,
            "data": self.data,
            "hora": self.hora,
            "dataHora": self.data_hora,
            "instanteIso": self.instante_iso,
            "imagem": self.imagem_base64,
            "descricao": self.mini_relatorio,
        }


class ServicoAlertaQueda:
    """Envia o mesmo evento por e-mail e WhatsApp sem misturar credenciais."""

    def __init__(self, sessao=None):
        self.sessao = sessao or requests.Session()
        self.habilitado = _booleano("ALERTS_ENABLED", False)
        self.simulacao = _booleano("ALERT_DRY_RUN", True)
        self.timeout = float(os.getenv("ALERT_HTTP_TIMEOUT", "20"))

    def status_configuracao(self) -> dict[str, Any]:
        email_pronto = bool(
            _lista_emails(os.getenv("ALERT_EMAIL_TO", ""))
            and os.getenv("RESEND_API_KEY", "").strip()
            and os.getenv("EMAIL_FROM", "").strip()
        )
        try:
            destino_whatsapp = _telefone_whatsapp(
                os.getenv("ALERT_WHATSAPP_TO", "")
            )
        except ValueError:
            destino_whatsapp = ""
        whatsapp_pronto = bool(
            destino_whatsapp
            and os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
            and os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        )
        return {
            "habilitado": self.habilitado,
            "simulacao": self.simulacao,
            "email_configurado": email_pronto,
            "whatsapp_configurado": whatsapp_pronto,
            "whatsapp_modo": (
                "template"
                if os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip()
                else "sessao"
            ),
        }

    def enviar(self, evento: EventoQueda) -> dict[str, dict[str, Any]]:
        if not self.habilitado:
            return {
                "email": {"status": "desativado"},
                "whatsapp": {"status": "desativado"},
            }

        resultados = {}
        for canal, funcao in (
            ("email", self._enviar_email),
            ("whatsapp", self._enviar_whatsapp),
        ):
            try:
                resultados[canal] = funcao(evento)
            except Exception as erro:  # cada canal falha de forma independente
                resultados[canal] = {
                    "status": "erro",
                    "mensagem": str(erro)[:500],
                }
                print(f"Falha no alerta por {canal}: {erro}", flush=True)
        return resultados

    def _enviar_email(self, evento: EventoQueda) -> dict[str, Any]:
        destinatarios = _lista_emails(os.getenv("ALERT_EMAIL_TO", ""))
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        remetente = os.getenv("EMAIL_FROM", "").strip()
        if not destinatarios:
            return {"status": "nao_configurado"}
        if not api_key or not remetente:
            raise RuntimeError("Configure RESEND_API_KEY e EMAIL_FROM para o e-mail.")

        nome = html.escape(evento.camera_nome)
        relatorio = html.escape(evento.mini_relatorio)
        payload = {
            "from": remetente,
            "to": destinatarios,
            "subject": f"🚨 Alerta de queda - {evento.camera_nome}",
            "html": f"""
                <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#0f172a">
                  <div style="background:#b91c1c;color:#fff;padding:20px;border-radius:16px 16px 0 0">
                    <h1 style="margin:0;font-size:24px">🚨 Queda detectada</h1>
                  </div>
                  <div style="padding:24px;border:1px solid #fecaca;border-top:0;border-radius:0 0 16px 16px">
                    <p><strong>Câmera:</strong> {nome}</p>
                    <p><strong>Data:</strong> {evento.data}</p>
                    <p><strong>Hora:</strong> {evento.hora}</p>
                    <p><strong>Confiança da detecção:</strong> {evento.confianca:.2f}%</p>
                    <img src="cid:queda-detectada" alt="Imagem da queda detectada"
                         style="width:100%;height:auto;border-radius:12px;margin:12px 0">
                    <h2 style="font-size:18px">Mini relatório</h2>
                    <p style="line-height:1.6">{relatorio}</p>
                    <p style="color:#991b1b;font-weight:bold">Este é um alerta automático. Verifique a situação imediatamente.</p>
                  </div>
                </div>
            """,
            "text": evento.mini_relatorio,
            "attachments": [
                {
                    "content": evento.imagem_base64,
                    "filename": "queda-detectada.jpg",
                    "contentId": "queda-detectada",
                }
            ],
        }
        if self.simulacao:
            return {
                "status": "simulado",
                "destinatarios": len(destinatarios),
                "possui_imagem": True,
            }

        resposta = self.sessao.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ai-health-fall-alert/1.0",
            },
            json=payload,
            timeout=self.timeout,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        return {"status": "enviado", "id": dados.get("id")}

    def _enviar_whatsapp(self, evento: EventoQueda) -> dict[str, Any]:
        destino = _telefone_whatsapp(os.getenv("ALERT_WHATSAPP_TO", ""))
        token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
        phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        versao = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v23.0").strip()
        if not destino:
            return {"status": "nao_configurado"}
        if not token or not phone_id:
            raise RuntimeError(
                "Configure WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID."
            )

        legenda = (
            "🚨 *ALERTA DE QUEDA - AI HEALTH*\n\n"
            f"📷 Câmera: {evento.camera_nome}\n"
            f"📅 Data: {evento.data}\n"
            f"🕐 Hora: {evento.hora}\n"
            f"🎯 Confiança: {evento.confianca:.2f}%\n\n"
            f"*Mini relatório:* {evento.mini_relatorio}"
        )
        template = os.getenv("WHATSAPP_TEMPLATE_NAME", "").strip()
        idioma = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_BR").strip()

        if self.simulacao:
            return {
                "status": "simulado",
                "modo": "template" if template else "sessao",
                "possui_imagem": True,
            }

        base_url = f"https://graph.facebook.com/{versao}/{phone_id}"
        cabecalho = {"Authorization": f"Bearer {token}"}
        upload = self.sessao.post(
            f"{base_url}/media",
            headers=cabecalho,
            data={"messaging_product": "whatsapp"},
            files={
                "file": (
                    "queda-detectada.jpg",
                    evento.imagem_jpeg,
                    "image/jpeg",
                )
            },
            timeout=self.timeout,
        )
        upload.raise_for_status()
        media_id = upload.json().get("id")
        if not media_id:
            raise RuntimeError("A Meta não retornou o ID da imagem enviada.")

        if template:
            corpo = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "template",
                "template": {
                    "name": template,
                    "language": {"code": idioma},
                    "components": [
                        {
                            "type": "header",
                            "parameters": [
                                {"type": "image", "image": {"id": media_id}}
                            ],
                        },
                        {
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": evento.camera_nome},
                                {"type": "text", "text": evento.data},
                                {"type": "text", "text": evento.hora},
                                {
                                    "type": "text",
                                    "text": f"{evento.confianca:.2f}%",
                                },
                                {"type": "text", "text": evento.mini_relatorio},
                            ],
                        },
                    ],
                },
            }
            modo = "template"
        else:
            corpo = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "image",
                "image": {"id": media_id, "caption": legenda[:1024]},
            }
            modo = "sessao"

        resposta = self.sessao.post(
            f"{base_url}/messages",
            headers={**cabecalho, "Content-Type": "application/json"},
            json=corpo,
            timeout=self.timeout,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        mensagens = dados.get("messages") or []
        return {
            "status": "enviado",
            "modo": modo,
            "id": mensagens[0].get("id") if mensagens else None,
            "media_id": media_id,
        }
