import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from consultancy.models import (
    PaisDestino,
    TipoVisto,
    FormularioVisto,
    PerguntaFormulario,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_admin():
    modulo = Modulo.objects.create(nome="Integ Formularios", slug="integ-formularios")
    perfil = Perfil.objects.create(
        nome="Admin Integ Formularios",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Forms Integ",
        email="admin.integ.forms@test.com",
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


class HomeFormulariosAcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_05_integracao_cadastro_formulario.py] Acesso à home de formulários")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_formularios_status_200(self):
        url = reverse("system:home_formularios")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_home_formularios_sem_login_redireciona(self):
        self.client.logout()
        url = reverse("system:home_formularios")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 301])

    def test_home_formularios_contexto_formularios(self):
        url = reverse("system:home_formularios")
        resp = self.client.get(url)
        self.assertIn("formularios", resp.context)


class FormularioVistoListagemTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_05_integracao_cadastro_formulario.py] Listagem de formulários de visto")
        cls.consultor, cls.django_user = _setup_admin()
        cls.pais = PaisDestino.objects.create(nome="Pais Forms Integ", codigo_iso="PFI", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Visto Forms Integ", criado_por=cls.django_user)
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_formulario_aparece_na_listagem(self):
        url = reverse("system:home_formularios")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        formularios = resp.context.get("formularios", [])
        pks = [f.pk for f in formularios]
        self.assertIn(self.formulario.pk, pks)


class EditarFormularioClienteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_05_integracao_cadastro_formulario.py] Editar formulário de visto")
        cls.consultor, cls.django_user = _setup_admin()
        cls.pais = PaisDestino.objects.create(nome="Pais Edit Form", codigo_iso="PEF", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Visto Edit Form", criado_por=cls.django_user)
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_get_editar_formulario_status_200(self):
        url = reverse("system:editar_formulario_cliente", kwargs={"formulario_id": self.formulario.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_adicionar_pergunta(self):
        url = reverse("system:editar_formulario_cliente", kwargs={"formulario_id": self.formulario.pk})
        payload = {
            "pergunta": "Qual é o objetivo da viagem?",
            "tipo_campo": "texto",
            "obrigatorio": True,
            "ordem": 1,
        }
        resp = self.client.post(url, payload, follow=True)
        self.assertIn(resp.status_code, [200, 302])


class HomeTiposFormularioTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_05_integracao_cadastro_formulario.py] Acesso à home de tipos de formulário")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_tipos_formulario_status_200(self):
        url = reverse("system:home_tipos_formulario")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
