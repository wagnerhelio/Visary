from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from system.services.passport_ocr import extract_passport_data_from_document


User = get_user_model()


class PassportOcrServiceTests(TestCase):
    @patch("system.services.passport_ocr._collect_lines_multisource")
    @patch("system.services.passport_ocr._extract_images")
    def test_extract_passport_data_from_document_parses_mrz(self, mock_extract_images, mock_collect_lines):
        mock_extract_images.return_value = [object()]
        mock_collect_lines.return_value = {
            "rapidocr": [
                "P<BRAFERREIRA<<VITTORIA<EMIDIA<<<<<<<<<<<<<<<<",
                "AB12345679BRA9001012F3201012<<<<<<<<<<<<<<00",
            ],
            "pytesseract": [
                "P<BRAFERREIRA<<VITTORIA<EMIDIA<<<<<<<<<<<<<<<<",
                "AB12345679BRA9001012F3201012<<<<<<<<<<<<<<00",
            ],
        }

        document = SimpleUploadedFile("passport.png", b"fake-bytes", content_type="image/png")
        result = extract_passport_data_from_document(document)

        fields = result["fields"]
        self.assertEqual(fields.get("numero_passaporte"), "AB1234567")
        self.assertEqual(fields.get("pais_emissor_passaporte"), "BRA")
        self.assertEqual(fields.get("nacionalidade"), "BRA")
        self.assertEqual(fields.get("data_nascimento"), "1990-01-01")
        self.assertEqual(fields.get("valido_ate_passaporte"), "2032-01-01")

    @patch("system.services.passport_ocr._collect_lines_multisource")
    @patch("system.services.passport_ocr._extract_images")
    def test_extract_passport_data_from_document_ignora_linha_de_assinatura(self, mock_extract_images, mock_collect_lines):
        mock_extract_images.return_value = [object()]
        mock_collect_lines.return_value = {
            "rapidocr": ["ASSINATURA DO TITULAR SIGNATUREDU TITULAIRE"],
            "pytesseract": ["ASSINATURA DO TITULAR SIGNATUREDU TITULAIRE"],
        }

        document = SimpleUploadedFile("passport.png", b"fake-bytes", content_type="image/png")
        result = extract_passport_data_from_document(document)

        self.assertNotIn("nome", result["fields"])


class PassportOcrApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ocr.user@test.com",
            email="ocr.user@test.com",
            password="senha-segura-123",
        )
        self.client.force_login(self.user)

    def test_api_extrair_passaporte_retorna_erro_sem_documento(self):
        response = self.client.post(reverse("system:api_extrair_passaporte"), data={})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("Envie um documento", payload["error"])

    @patch("system.views.client_views.extract_passport_data_from_document")
    def test_api_extrair_passaporte_salva_campos_na_sessao_quando_solicitado(self, mock_extract):
        mock_extract.return_value = {
            "fields": {
                "nome": "Vittoria Emidia Ferreira Guimaraes",
                "numero_passaporte": "AB1234567",
            },
            "warnings": ["Extração parcial. Revise cuidadosamente os dados antes de salvar."],
        }
        document = SimpleUploadedFile("passport.png", b"fake-bytes", content_type="image/png")

        response = self.client.post(
            reverse("system:api_extrair_passaporte"),
            data={"documento": document, "target": "cliente", "persist_in_session": "true"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["fields"]["numero_passaporte"], "AB1234567")
        self.assertIn("passport_ocr_cliente", self.client.session)
