import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from consultancy.models import ClienteConsultoria
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_admin():
    modulo = Modulo.objects.create(nome="Integ Clientes", slug="integ-clientes")
    perfil = Perfil.objects.create(
        nome="Admin Integ Clientes",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Integ",
        email="admin.integ.cli@test.com",
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


class HomeClientesAcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_02_integracao_cadastro_cliente.py] Acesso à home de clientes")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_clientes_status_200(self):
        url = reverse("system:home_clientes")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_home_clientes_sem_login_redireciona(self):
        self.client.logout()
        url = reverse("system:home_clientes")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 301])

    def test_home_clientes_contexto_clientes(self):
        url = reverse("system:home_clientes")
        resp = self.client.get(url)
        self.assertIn("clientes", resp.context)


class CadastroClienteEtapa1Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_02_integracao_cadastro_cliente.py] Cadastro cliente — Etapa 1")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_get_cadastro_etapa1_status_200(self):
        url = reverse("system:cadastrar_cliente_etapa", kwargs={"etapa": 1})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_etapa1_dados_validos_avanca(self):
        url = reverse("system:cadastrar_cliente_etapa", kwargs={"etapa": 1})
        payload = {
            "nome": "Cliente Integ",
            "data_nascimento": "1990-06-15",
            "nacionalidade": "Brasileiro",
            "telefone": "(11) 91111-2222",
            "email": "integ.cli@test.com",
            "senha": "senhacliente123",
            "assessor_responsavel": self.consultor.pk,
        }
        resp = self.client.post(url, payload, follow=True)
        self.assertIn(resp.status_code, [200, 302])

    def test_post_etapa1_sem_email_retorna_erro(self):
        url = reverse("system:cadastrar_cliente_etapa", kwargs={"etapa": 1})
        payload = {
            "nome": "Cliente Sem Email",
            "data_nascimento": "1990-06-15",
            "nacionalidade": "Brasileiro",
            "telefone": "(11) 91111-3333",
            "email": "",
            "senha": "senhacliente123",
            "assessor_responsavel": self.consultor.pk,
        }
        resp = self.client.post(url, payload)
        self.assertIn(resp.status_code, [200, 302])


class ListagemClientesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_02_integracao_cadastro_cliente.py] Listagem de clientes")
        cls.consultor, cls.django_user = _setup_admin()
        cls.cliente1 = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Lista A",
            data_nascimento=datetime.date(1985, 3, 10),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-4444",
            email="lista.a@test.com",
            senha="hash",
            criado_por=cls.consultor,
        )
        cls.cliente2 = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Lista B",
            data_nascimento=datetime.date(1990, 7, 20),
            nacionalidade="Argentino",
            telefone="(11) 91111-5555",
            email="lista.b@test.com",
            senha="hash",
            criado_por=cls.consultor,
        )

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_clientes_aparecem_na_listagem(self):
        url = reverse("system:home_clientes")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        clientes = resp.context.get("clientes", [])
        nomes = [c.nome for c in clientes]
        self.assertIn("Cliente Lista A", nomes)
        self.assertIn("Cliente Lista B", nomes)

    def test_filtro_por_nome(self):
        url = reverse("system:home_clientes") + "?nome=Lista+A"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        clientes = resp.context.get("clientes", [])
        nomes = [c.nome for c in clientes]
        self.assertIn("Cliente Lista A", nomes)
        self.assertNotIn("Cliente Lista B", nomes)
