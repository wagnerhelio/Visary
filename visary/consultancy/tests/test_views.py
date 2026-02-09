from django.urls import reverse
from django.test import TestCase, Client
from system.models import UsuarioConsultoria, Perfil, Modulo
from consultancy.models import Partner
from django.utils.text import slugify


class ConsultancyViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Minimal security setup
        mod = Modulo.objects.create(nome="Test Modulo", slug=slugify("Test Modulo"))
        perfil = Perfil.objects.create(nome="Administrador", descricao="test", ativo=True)
        cls.user = UsuarioConsultoria.objects.create(
            nome="Test User",
            email="test.user@example.com",
            perfil=perfil,
            ativo=True,
        )
        cls.user.set_password("testpass")
        cls.user.save()

    def setUp(self):
        self.client = Client()
        self.client.login(username=self.__class__.user.email, password="testpass")

    def test_home_partners_view_access(self):
        url = reverse("system:home_partners")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (200, 301, 302))

    def test_criar_partner_view_post(self):
        url = reverse("system:criar_partner")
        data = {
            "nome_responsavel": "Parceiro Teste",
            "nome_empresa": "Empresa Teste",
            "cpf": "",
            "cnpj": "",
            "email": "partner@example.com",
            "senha": "secret123",
            "telefone": "(11)99999-9999",
            "segmento": "outros",
            "cidade": "Cidade",
            "estado": "ST",
            "ativo": True,
        }
        resp = self.client.post(url, data)
        self.assertIn(resp.status_code, (302, 301))
        self.assertTrue(Partner.objects.filter(email="partner@example.com").exists())
