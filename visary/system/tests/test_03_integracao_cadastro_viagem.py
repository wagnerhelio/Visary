import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from consultancy.models import PaisDestino, TipoVisto, Viagem
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_admin():
    modulo = Modulo.objects.create(nome="Integ Viagens", slug="integ-viagens")
    perfil = Perfil.objects.create(
        nome="Admin Integ Viagens",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Viagens Integ",
        email="admin.integ.viag@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username=consultor.email,
        defaults={"email": consultor.email, "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


class HomeViagensAcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_03_integracao_cadastro_viagem.py] Acesso à home de viagens")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_viagens_status_200(self):
        url = reverse("system:home_viagens")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_home_viagens_sem_login_redireciona(self):
        self.client.logout()
        url = reverse("system:home_viagens")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 301])

    def test_home_viagens_contexto_viagens(self):
        url = reverse("system:home_viagens")
        resp = self.client.get(url)
        self.assertIn("viagens", resp.context)


class HomePaisesDestinoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_03_integracao_cadastro_viagem.py] Acesso à home de países destino")
        cls.consultor, cls.django_user = _setup_admin()
        cls.pais = PaisDestino.objects.create(nome="Brasil PD Integ", codigo_iso="BRI", criado_por=cls.django_user)

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_paises_status_200(self):
        url = reverse("system:home_paises_destino")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_pais_aparece_na_listagem(self):
        url = reverse("system:home_paises_destino")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        paises = resp.context.get("paises", [])
        nomes = [p.nome for p in paises]
        self.assertIn("Brasil PD Integ", nomes)


class CriarPaisDestinoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_03_integracao_cadastro_viagem.py] Criar país de destino via POST")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_post_criar_pais_destino(self):
        url = reverse("system:criar_pais_destino")
        payload = {"nome": "Canada Integ POST", "codigo_iso": "CAN"}
        resp = self.client.post(url, payload, follow=True)
        self.assertIn(resp.status_code, [200, 302])
        self.assertTrue(PaisDestino.objects.filter(nome="Canada Integ POST").exists())


class HomeTiposVistoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_03_integracao_cadastro_viagem.py] Acesso à home de tipos de visto")
        cls.consultor, cls.django_user = _setup_admin()
        cls.pais = PaisDestino.objects.create(nome="Australia TV Integ", codigo_iso="AUT", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Work Visa", criado_por=cls.django_user)

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_tipos_visto_status_200(self):
        url = reverse("system:home_tipos_visto")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_tipo_visto_aparece_na_listagem(self):
        url = reverse("system:home_tipos_visto")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        tipos = resp.context.get("tipos_visto", [])
        nomes = [t.nome for t in tipos]
        self.assertIn("Work Visa", nomes)


class CriarViagemTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_03_integracao_cadastro_viagem.py] Criar viagem via POST")
        cls.consultor, cls.django_user = _setup_admin()
        cls.pais = PaisDestino.objects.create(nome="Nova Zelandia", codigo_iso="NZL", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo NZ", criado_por=cls.django_user)

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_get_criar_viagem_status_200(self):
        url = reverse("system:criar_viagem")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_criar_viagem_valida(self):
        url = reverse("system:criar_viagem")
        payload = {
            "assessor_responsavel": self.consultor.pk,
            "pais_destino": self.pais.pk,
            "tipo_visto": self.visto.pk,
            "data_prevista_viagem": "2026-12-01",
            "data_prevista_retorno": "2026-12-15",
            "valor_assessoria": "1500.00",
        }
        resp = self.client.post(url, payload, follow=True)
        self.assertIn(resp.status_code, [200, 302])
        self.assertTrue(Viagem.objects.filter(pais_destino=self.pais).exists())
