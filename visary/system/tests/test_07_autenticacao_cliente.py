import datetime
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from consultancy.models import ClienteConsultoria
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Auth Cliente", slug="auth-cliente")
    perfil = Perfil.objects.create(
        nome="Perfil Auth Cliente",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Consultor Auth",
        email="consultor.auth@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="consultor.auth@test.com",
        defaults={"email": "consultor.auth@test.com"},
    )
    return consultor, django_user


class ClienteLoginCpfTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_07_autenticacao_cliente.py] Login de cliente por CPF")
        cls.consultor, cls.django_user = _setup_base()
        cls.senha_raw = "MinhaSenha123"
        cls.cliente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Auth CPF",
            cpf="529.982.247-25",
            data_nascimento=datetime.date(1990, 1, 1),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-0001",
            email="auth.cpf@test.com",
            senha=make_password(cls.senha_raw),
            criado_por=cls.django_user,
        )

    def setUp(self):
        self.login_url = reverse("login")

    def test_login_com_cpf_formatado(self):
        response = self.client.post(self.login_url, {
            "identifier": "529.982.247-25",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertIn(response.status_code, [200, 302])
        self.assertIn("cliente_id", self.client.session)
        self.assertEqual(self.client.session["cliente_id"], self.cliente.pk)

    def test_login_com_cpf_sem_mascara(self):
        response = self.client.post(self.login_url, {
            "identifier": "52998224725",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertIn(response.status_code, [200, 302])
        self.assertIn("cliente_id", self.client.session)

    def test_login_seta_cliente_cpf_na_sessao(self):
        self.client.post(self.login_url, {
            "identifier": "529.982.247-25",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertEqual(self.client.session.get("cliente_cpf"), "529.982.247-25")

    def test_login_nao_seta_cliente_email_na_sessao(self):
        self.client.post(self.login_url, {
            "identifier": "529.982.247-25",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertNotIn("cliente_email", self.client.session)

    def test_login_senha_errada_nao_autentica(self):
        response = self.client.post(self.login_url, {
            "identifier": "529.982.247-25",
            "password": "senha_errada",
            "remember_me": False,
        })
        self.assertNotIn("cliente_id", self.client.session)

    def test_login_cpf_invalido_nao_autentica(self):
        response = self.client.post(self.login_url, {
            "identifier": "000.000.000-00",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertNotIn("cliente_id", self.client.session)

    def test_login_cpf_inexistente_nao_autentica(self):
        response = self.client.post(self.login_url, {
            "identifier": "123.456.789-09",
            "password": self.senha_raw,
            "remember_me": False,
        })
        self.assertNotIn("cliente_id", self.client.session)


class ClienteDependenteLoginTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_07_autenticacao_cliente.py] Login de dependente com CPF próprio")
        cls.consultor, cls.django_user = _setup_base()
        cls.senha_principal = "SenhaPrincipal1"
        cls.senha_dependente = "SenhaDependente2"

        cls.principal = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Principal Dep Login",
            cpf="021.981.890-37",
            data_nascimento=datetime.date(1985, 5, 10),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-0002",
            email="principal.dep@test.com",
            senha=make_password(cls.senha_principal),
            criado_por=cls.django_user,
        )
        cls.dependente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Dependente Dep Login",
            cpf="874.282.580-08",
            data_nascimento=datetime.date(2005, 3, 20),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-0003",
            senha=make_password(cls.senha_dependente),
            criado_por=cls.django_user,
            cliente_principal=cls.principal,
        )

    def setUp(self):
        self.login_url = reverse("login")

    def test_principal_e_dependente_tem_cpfs_distintos(self):
        self.assertNotEqual(self.principal.cpf, self.dependente.cpf)

    def test_login_principal_por_cpf_proprio(self):
        response = self.client.post(self.login_url, {
            "identifier": "021.981.890-37",
            "password": self.senha_principal,
            "remember_me": False,
        })
        self.assertIn("cliente_id", self.client.session)
        self.assertEqual(self.client.session["cliente_id"], self.principal.pk)

    def test_login_dependente_por_cpf_proprio(self):
        response = self.client.post(self.login_url, {
            "identifier": "874.282.580-08",
            "password": self.senha_dependente,
            "remember_me": False,
        })
        self.assertIn("cliente_id", self.client.session)
        self.assertEqual(self.client.session["cliente_id"], self.dependente.pk)

    def test_sessoes_principal_e_dependente_independentes(self):
        self.client.post(self.login_url, {
            "identifier": "021.981.890-37",
            "password": self.senha_principal,
            "remember_me": False,
        })
        self.assertEqual(self.client.session["cliente_id"], self.principal.pk)

        self.client.session.flush()

        self.client.post(self.login_url, {
            "identifier": "874.282.580-08",
            "password": self.senha_dependente,
            "remember_me": False,
        })
        self.assertEqual(self.client.session["cliente_id"], self.dependente.pk)
