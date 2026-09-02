import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


CAMERA_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMERA_DIR))

from alerta_queda import EventoQueda, ServicoAlertaQueda  # noqa: E402


class RespostaFalsa:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        return None

    def json(self):
        return self.dados


class SessaoFalsa:
    def __init__(self):
        self.chamadas = []

    def post(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        if url.endswith("/media"):
            return RespostaFalsa({"id": "media-123"})
        if url.endswith("/messages"):
            return RespostaFalsa({"messages": [{"id": "wamid-123"}]})
        return RespostaFalsa({"id": "email-123"})


class TesteAlertaQueda(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        self.evento = EventoQueda.criar(
            self.frame,
            camera_id="camera-1",
            camera_nome="Sala",
            confianca=0.91,
        )

    def test_evento_contem_imagem_data_hora_e_relatorio(self):
        dados = self.evento.para_firestore()
        self.assertEqual(dados["cameraNome"], "Sala")
        self.assertEqual(dados["confianca"], 91.0)
        self.assertTrue(dados["imagem"])
        self.assertRegex(dados["data"], r"\d{2}/\d{2}/\d{4}")
        self.assertRegex(dados["hora"], r"\d{2}:\d{2}:\d{2}")
        self.assertIn("Queda confirmada", dados["descricao"])

    def test_simulacao_nao_faz_requisicoes(self):
        sessao = SessaoFalsa()
        ambiente = {
            "ALERTS_ENABLED": "true",
            "ALERT_DRY_RUN": "true",
            "ALERT_EMAIL_TO": "cuidador@example.com",
            "RESEND_API_KEY": "re_teste",
            "EMAIL_FROM": "AI Health <teste@example.com>",
            "ALERT_WHATSAPP_TO": "5511999999999",
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            resultado = ServicoAlertaQueda(sessao).enviar(self.evento)

        self.assertEqual(resultado["email"]["status"], "simulado")
        self.assertEqual(resultado["whatsapp"]["status"], "simulado")
        self.assertEqual(sessao.chamadas, [])

    def test_status_nao_expoe_credenciais(self):
        ambiente = {
            "ALERTS_ENABLED": "true",
            "ALERT_DRY_RUN": "true",
            "ALERT_EMAIL_TO": "cuidador@example.com",
            "RESEND_API_KEY": "segredo-resend",
            "EMAIL_FROM": "AI Health <teste@example.com>",
            "ALERT_WHATSAPP_TO": "5511999999999",
            "WHATSAPP_ACCESS_TOKEN": "segredo-meta",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            status = ServicoAlertaQueda().status_configuracao()

        self.assertTrue(status["email_configurado"])
        self.assertTrue(status["whatsapp_configurado"])
        self.assertNotIn("segredo-resend", str(status))
        self.assertNotIn("segredo-meta", str(status))

    def test_envio_direto_anexa_imagem_nos_dois_canais(self):
        sessao = SessaoFalsa()
        ambiente = {
            "ALERTS_ENABLED": "true",
            "ALERT_DRY_RUN": "false",
            "ALERT_EMAIL_TO": "cuidador@example.com",
            "RESEND_API_KEY": "re_teste",
            "EMAIL_FROM": "AI Health <teste@example.com>",
            "ALERT_WHATSAPP_TO": "+55 (11) 99999-9999",
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
            "WHATSAPP_GRAPH_API_VERSION": "v23.0",
            "WHATSAPP_TEMPLATE_NAME": "",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            resultado = ServicoAlertaQueda(sessao).enviar(self.evento)

        self.assertEqual(resultado["email"]["status"], "enviado")
        self.assertEqual(resultado["whatsapp"]["status"], "enviado")
        self.assertEqual(len(sessao.chamadas), 3)
        email = sessao.chamadas[0][1]["json"]
        mensagem = sessao.chamadas[2][1]["json"]
        self.assertTrue(email["attachments"][0]["content"])
        self.assertEqual(mensagem["type"], "image")
        self.assertEqual(mensagem["image"]["id"], "media-123")

    def test_template_whatsapp_recebe_cinco_campos_do_relatorio(self):
        sessao = SessaoFalsa()
        ambiente = {
            "ALERTS_ENABLED": "true",
            "ALERT_DRY_RUN": "false",
            "ALERT_EMAIL_TO": "",
            "ALERT_WHATSAPP_TO": "5511999999999",
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-id",
            "WHATSAPP_TEMPLATE_NAME": "alerta_queda_ai_health",
            "WHATSAPP_TEMPLATE_LANGUAGE": "pt_BR",
        }
        with patch.dict(os.environ, ambiente, clear=False):
            resultado = ServicoAlertaQueda(sessao).enviar(self.evento)

        mensagem = sessao.chamadas[-1][1]["json"]
        parametros = mensagem["template"]["components"][1]["parameters"]
        self.assertEqual(resultado["whatsapp"]["modo"], "template")
        self.assertEqual(len(parametros), 5)
        self.assertEqual(parametros[0]["text"], "Sala")


if __name__ == "__main__":
    unittest.main()
