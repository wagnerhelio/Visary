import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    PaisDestino,
    TipoVisto,
    Viagem,
    ClienteViagem,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Viagens Base", slug="viagens-base")
    perfil = Perfil.objects.create(
        nome="Admin Viagens",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Viagens",
        email="admin.viagens@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.viagens@test.com",
        defaults={"email": "admin.viagens@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


def _cliente_base(consultor, django_user, email="cli.viagem@test.com"):
    return ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome="Cliente Viagem",
        data_nascimento=datetime.date(1990, 1, 1),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-1111",
        email=email,
        senha="hash",
        criado_por=django_user,
    )


def _viagem_base(consultor, django_user, pais, visto, **kwargs):
    defaults = dict(
        assessor_responsavel=consultor,
        pais_destino=pais,
        tipo_visto=visto,
        data_prevista_viagem=datetime.date(2026, 8, 1),
        data_prevista_retorno=datetime.date(2026, 8, 15),
        valor_assessoria=1000.00,
        criado_por=django_user,
    )
    defaults.update(kwargs)
    return Viagem.objects.create(**defaults)


class PaisDestinoCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Criação de país de destino")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(
            nome="Portugal PD",
            codigo_iso="PRT",
            criado_por=cls.django_user,
        )

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.pais.pk)

    def test_str_retorna_nome(self):
        self.assertEqual(str(self.pais), "Portugal PD")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.pais.ativo)

    def test_nome_unico(self):
        with self.assertRaises(Exception):
            PaisDestino.objects.create(nome="Portugal PD", criado_por=self.django_user)


class TipoVistoCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Criação de tipo de visto")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Espanha TV", codigo_iso="ESP", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(
            pais_destino=cls.pais,
            nome="Turismo",
            criado_por=cls.django_user,
        )

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.visto.pk)

    def test_str_contem_nome_e_pais(self):
        self.assertIn("Turismo", str(self.visto))
        self.assertIn("Espanha TV", str(self.visto))

    def test_ativo_por_padrao(self):
        self.assertTrue(self.visto.ativo)

    def test_unique_together_pais_nome(self):
        with self.assertRaises(Exception):
            TipoVisto.objects.create(
                pais_destino=self.pais,
                nome="Turismo",
                criado_por=self.django_user,
            )

    def test_tipos_diferentes_mesmo_pais_permitido(self):
        visto2 = TipoVisto.objects.create(
            pais_destino=self.pais,
            nome="Estudante",
            criado_por=self.django_user,
        )
        self.assertIsNotNone(visto2.pk)


class ViagemCriacaoBasicaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Criação básica de viagem")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Italia VB", codigo_iso="ITA", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo VB", criado_por=cls.django_user)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, cls.pais, cls.visto)

    def test_criada_com_sucesso(self):
        self.assertIsNotNone(self.viagem.pk)

    def test_str_contem_pais_e_data(self):
        self.assertIn("Italia VB", str(self.viagem))
        self.assertIn("01/08/2026", str(self.viagem))

    def test_valor_assessoria(self):
        from decimal import Decimal
        self.assertEqual(self.viagem.valor_assessoria, Decimal("1000.00"))

    def test_sem_clientes_inicialmente(self):
        self.assertEqual(self.viagem.clientes.count(), 0)


class ViagemComClienteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Viagem com cliente vinculado")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Franca VC", codigo_iso="FRA", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo VC", criado_por=cls.django_user)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, cls.pais, cls.visto)
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="vcli@test.com")
        cls.viagem.clientes.add(cls.cliente)

    def test_cliente_vinculado(self):
        self.assertEqual(self.viagem.clientes.count(), 1)
        self.assertIn(self.cliente, self.viagem.clientes.all())

    def test_cliente_viagem_intermediario_criado(self):
        self.assertTrue(
            ClienteViagem.objects.filter(viagem=self.viagem, cliente=self.cliente).exists()
        )

    def test_viagem_aparece_no_cliente(self):
        self.assertIn(self.viagem, self.cliente.viagens.all())


class ViagemComMultiplosClientesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Viagem com múltiplos clientes")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Alemanha MC", codigo_iso="DEU", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo MC", criado_por=cls.django_user)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, cls.pais, cls.visto)
        cls.c1 = _cliente_base(cls.consultor, cls.django_user, email="mc1@test.com")
        cls.c2 = _cliente_base(cls.consultor, cls.django_user, email="mc2@test.com")
        cls.c3 = _cliente_base(cls.consultor, cls.django_user, email="mc3@test.com")
        cls.viagem.clientes.add(cls.c1, cls.c2, cls.c3)

    def test_tres_clientes_vinculados(self):
        self.assertEqual(self.viagem.clientes.count(), 3)

    def test_todos_presentes(self):
        clientes = self.viagem.clientes.all()
        for c in (self.c1, self.c2, self.c3):
            self.assertIn(c, clientes)


class ClienteViagemTipoVistoEspecificoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] ClienteViagem com tipo visto específico")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Japao TV", codigo_iso="JPN", criado_por=cls.django_user)
        cls.visto_a = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo TVA", criado_por=cls.django_user)
        cls.visto_b = TipoVisto.objects.create(pais_destino=cls.pais, nome="Estudante TVB", criado_por=cls.django_user)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, cls.pais, cls.visto_a)
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="tv.esp@test.com")
        cls.viagem.clientes.add(cls.cliente)
        ClienteViagem.objects.filter(viagem=cls.viagem, cliente=cls.cliente).update(tipo_visto=cls.visto_b)

    def test_tipo_visto_especifico_gravado(self):
        cv = ClienteViagem.objects.get(viagem=self.viagem, cliente=self.cliente)
        self.assertEqual(cv.tipo_visto, self.visto_b)
        self.assertNotEqual(cv.tipo_visto, self.visto_a)

    def test_str_contem_cliente_e_viagem(self):
        cv = ClienteViagem.objects.get(viagem=self.viagem, cliente=self.cliente)
        self.assertIn("Cliente Viagem", str(cv))


class ViagemExclusaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_viagens.py] Exclusão de viagem e cascade")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="Mexico EX", codigo_iso="MEX", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo EX", criado_por=cls.django_user)

    def test_excluir_viagem_remove_cliente_viagem(self):
        viagem = _viagem_base(self.consultor, self.django_user, self.pais, self.visto)
        cliente = _cliente_base(self.consultor, self.django_user, email="excl.viag@test.com")
        viagem.clientes.add(cliente)
        cv_pk = ClienteViagem.objects.get(viagem=viagem, cliente=cliente).pk
        viagem.delete()
        self.assertFalse(ClienteViagem.objects.filter(pk=cv_pk).exists())

    def test_excluir_pais_cascade_tipos_visto(self):
        pais = PaisDestino.objects.create(nome="Temporario", codigo_iso="TMP", criado_por=self.django_user)
        visto = TipoVisto.objects.create(pais_destino=pais, nome="Tipo Temp", criado_por=self.django_user)
        visto_pk = visto.pk
        pais.delete()
        self.assertFalse(TipoVisto.objects.filter(pk=visto_pk).exists())
