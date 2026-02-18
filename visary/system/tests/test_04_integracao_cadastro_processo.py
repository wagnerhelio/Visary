import datetime
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    PaisDestino,
    TipoVisto,
    Viagem,
    Processo,
    StatusProcesso,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _cpf_from_email(email: str) -> str:
    digits = str(abs(hash(email)))[:9].zfill(9)
    def dig(d):
        w = len(d) + 1
        s = sum(int(x) * (w - i) for i, x in enumerate(d))
        r = s % 11
        return "0" if r < 2 else str(11 - r)
    d1 = dig(digits)
    d2 = dig(digits + d1)
    raw = digits + d1 + d2
    return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"


def _setup_admin():
    modulo = Modulo.objects.create(nome="Integ Processos", slug="integ-processos")
    perfil = Perfil.objects.create(
        nome="Admin Integ Processos",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Processos Integ",
        email="admin.integ.proc@test.com",
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


def _criar_viagem_com_cliente(consultor, django_user, sufixo="A"):
    pais = PaisDestino.objects.create(nome=f"Pais Proc Integ {sufixo}", codigo_iso=f"I{sufixo[:2]}", criado_por=django_user)
    visto = TipoVisto.objects.create(pais_destino=pais, nome=f"Turismo PI {sufixo}", criado_por=django_user)
    viagem = Viagem.objects.create(
        assessor_responsavel=consultor,
        pais_destino=pais,
        tipo_visto=visto,
        data_prevista_viagem=datetime.date(2027, 1, 10),
        data_prevista_retorno=datetime.date(2027, 1, 25),
        criado_por=django_user,
    )
    email_cliente = f"proc.integ.{sufixo.lower()}@test.com"
    cliente = ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome=f"Cliente Proc Integ {sufixo}",
        cpf=_cpf_from_email(email_cliente),
        data_nascimento=datetime.date(1990, 1, 1),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-6666",
        email=email_cliente,
        senha="hash",
        criado_por=django_user,
    )
    viagem.clientes.add(cliente)
    return viagem, cliente


class HomeProcessosAcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_04_integracao_cadastro_processo.py] Acesso à home de processos")
        cls.consultor, cls.django_user = _setup_admin()

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_home_processos_status_200(self):
        url = reverse("system:home_processos")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_home_processos_sem_login_redireciona(self):
        self.client.logout()
        url = reverse("system:home_processos")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 301])

    def test_home_processos_contexto_processos(self):
        url = reverse("system:home_processos")
        resp = self.client.get(url)
        self.assertIn("processos", resp.context)


class CriarProcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_04_integracao_cadastro_processo.py] Criar processo via POST")
        cls.consultor, cls.django_user = _setup_admin()
        cls.viagem, cls.cliente = _criar_viagem_com_cliente(cls.consultor, cls.django_user, sufixo="CP")

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_get_criar_processo_status_200(self):
        url = reverse("system:criar_processo")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_criar_processo_valido(self):
        url = reverse("system:criar_processo")
        payload = {
            "viagem": self.viagem.pk,
            "cliente": self.cliente.pk,
            "assessor_responsavel": self.consultor.pk,
        }
        resp = self.client.post(url, payload, follow=True)
        self.assertIn(resp.status_code, [200, 302])
        self.assertTrue(
            Processo.objects.filter(viagem=self.viagem, cliente=self.cliente).exists()
        )


class ListagemProcessosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_04_integracao_cadastro_processo.py] Listagem de processos")
        cls.consultor, cls.django_user = _setup_admin()
        cls.viagem, cls.cliente = _criar_viagem_com_cliente(cls.consultor, cls.django_user, sufixo="LP")
        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_processo_aparece_na_listagem(self):
        url = reverse("system:home_processos")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        processos = resp.context.get("processos", [])
        pks = [p.pk for p in processos]
        self.assertIn(self.processo.pk, pks)


class DetalheProcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_04_integracao_cadastro_processo.py] Detalhe de processo")
        cls.consultor, cls.django_user = _setup_admin()
        cls.viagem, cls.cliente = _criar_viagem_com_cliente(cls.consultor, cls.django_user, sufixo="DP")
        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )

    def setUp(self):
        self.client.login(username=self.django_user.username, password="senha123")

    def test_detalhe_processo_status_200(self):
        url = reverse("system:editar_processo", kwargs={"processo_id": self.processo.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
