import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from consultancy.models import Partner, ClienteConsultoria
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Parceiros Base", slug="parceiros-base")
    perfil = Perfil.objects.create(
        nome="Admin Parceiros",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Parceiros",
        email="admin.parceiros@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.parceiros@test.com",
        defaults={"email": "admin.parceiros@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


def _partner_base(django_user, email="parceiro@test.com", segmento="outros"):
    return Partner.objects.create(
        nome_responsavel="Responsavel Parceiro",
        email=email,
        senha="hash",
        criado_por=django_user,
        segmento=segmento,
    )


class PartnerCriacaoBasicaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Criação básica de parceiro")
        cls.consultor, cls.django_user = _setup_base()
        cls.partner = _partner_base(cls.django_user)

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.partner.pk)

    def test_str_sem_empresa(self):
        self.assertEqual(str(self.partner), "Responsavel Parceiro")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.partner.ativo)

    def test_segmento_padrao(self):
        self.assertEqual(self.partner.segmento, "outros")


class PartnerComEmpresaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Parceiro com empresa")
        cls.consultor, cls.django_user = _setup_base()
        cls.partner = Partner.objects.create(
            nome_responsavel="Joao Silva",
            nome_empresa="Agencia XYZ",
            email="agencia@test.com",
            senha="hash",
            criado_por=cls.django_user,
            segmento="agencia_viagem",
        )

    def test_str_com_empresa(self):
        self.assertIn("Agencia XYZ", str(self.partner))
        self.assertIn("Joao Silva", str(self.partner))

    def test_segmento_agencia(self):
        self.assertEqual(self.partner.segmento, "agencia_viagem")


class PartnerSegmentosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Parceiros com diferentes segmentos")
        cls.consultor, cls.django_user = _setup_base()

    def test_segmento_consultoria_imigracao(self):
        p = _partner_base(self.django_user, email="ci@test.com", segmento="consultoria_imigracao")
        self.assertEqual(p.segmento, "consultoria_imigracao")

    def test_segmento_advocacia(self):
        p = _partner_base(self.django_user, email="adv@test.com", segmento="advocacia")
        self.assertEqual(p.segmento, "advocacia")

    def test_segmento_educacao(self):
        p = _partner_base(self.django_user, email="edu@test.com", segmento="educacao")
        self.assertEqual(p.segmento, "educacao")


class PartnerSenhaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Senha do parceiro")
        cls.consultor, cls.django_user = _setup_base()
        cls.partner = _partner_base(cls.django_user, email="senha.partner@test.com")

    def test_set_e_check_password(self):
        self.partner.set_password("minhasenha456")
        self.partner.save()
        self.assertTrue(self.partner.check_password("minhasenha456"))

    def test_senha_errada_retorna_false(self):
        self.partner.set_password("correta")
        self.partner.save()
        self.assertFalse(self.partner.check_password("errada"))


class PartnerEmailUnicoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Email único de parceiro")
        cls.consultor, cls.django_user = _setup_base()
        _partner_base(cls.django_user, email="unico@test.com")

    def test_email_duplicado_levanta_erro(self):
        with self.assertRaises(Exception):
            _partner_base(self.django_user, email="unico@test.com")


class PartnerClientesIndicadosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Clientes indicados pelo parceiro")
        cls.consultor, cls.django_user = _setup_base()
        cls.partner = _partner_base(cls.django_user, email="indicador@test.com")
        cls.cliente1 = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Indicado 1",
            cpf="365.481.380-60",
            data_nascimento=datetime.date(1990, 1, 1),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-1111",
            email="ind1@test.com",
            senha="hash",
            criado_por=cls.django_user,
            parceiro_indicador=cls.partner,
        )
        cls.cliente2 = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Indicado 2",
            cpf="073.374.310-71",
            data_nascimento=datetime.date(1992, 2, 2),
            nacionalidade="Brasileiro",
            telefone="(11) 92222-2222",
            email="ind2@test.com",
            senha="hash",
            criado_por=cls.django_user,
            parceiro_indicador=cls.partner,
        )

    def test_dois_clientes_indicados(self):
        self.assertEqual(self.partner.clientes_indicados.count(), 2)

    def test_clientes_corretos(self):
        self.assertIn(self.cliente1, self.partner.clientes_indicados.all())
        self.assertIn(self.cliente2, self.partner.clientes_indicados.all())


class PartnerInativoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Parceiro inativo")
        cls.consultor, cls.django_user = _setup_base()
        cls.partner = Partner.objects.create(
            nome_responsavel="Parceiro Inativo",
            email="inativo.partner@test.com",
            senha="hash",
            criado_por=cls.django_user,
            segmento="outros",
            ativo=False,
        )

    def test_ativo_false(self):
        self.assertFalse(self.partner.ativo)

    def test_pode_reativar(self):
        self.partner.ativo = True
        self.partner.save()
        atualizado = Partner.objects.get(pk=self.partner.pk)
        self.assertTrue(atualizado.ativo)


class PartnerExclusaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_parceiros.py] Excluir parceiro")
        cls.consultor, cls.django_user = _setup_base()

    def test_excluir_parceiro(self):
        partner = _partner_base(self.django_user, email="del.partner@test.com")
        pk = partner.pk
        partner.delete()
        self.assertFalse(Partner.objects.filter(pk=pk).exists())
