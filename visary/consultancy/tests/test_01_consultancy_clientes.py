import datetime
from django.test import TestCase
from django.db.utils import IntegrityError
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    Partner,
    PaisDestino,
    TipoVisto,
    Viagem,
    ClienteViagem,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Clientes Base", slug="clientes-base")
    perfil = Perfil.objects.create(
        nome="Administrador Clientes",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Clientes",
        email="admin.clientes@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.clientes@test.com",
        defaults={"email": "admin.clientes@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


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


def _cliente_base(consultor, django_user, email="cli@test.com", principal=None, cpf=None):
    return ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome="Cliente Base",
        cpf=cpf or _cpf_from_email(email),
        data_nascimento=datetime.date(1990, 6, 15),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-1111",
        email=email,
        senha="hash",
        criado_por=django_user,
        cliente_principal=principal,
    )


class ClienteSemMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente sem membros (principal simples)")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user)

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.cliente.pk)

    def test_is_principal(self):
        self.assertTrue(self.cliente.is_principal)
        self.assertFalse(self.cliente.is_dependente)

    def test_total_dependentes_zero(self):
        self.assertEqual(self.cliente.total_dependentes, 0)

    def test_campos_booleanos_etapa_falsos(self):
        for campo in ("etapa_dados_pessoais", "etapa_endereco", "etapa_membros", "etapa_passaporte"):
            self.assertFalse(getattr(self.cliente, campo), f"{campo} deveria ser False por padrão")

    def test_progresso_etapas_retorna_valor(self):
        self.assertIsNotNone(self.cliente.progresso_etapas)


class ClienteComMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente com membros dependentes")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="principal@test.com")
        cls.dep1 = _cliente_base(cls.consultor, cls.django_user, email="dep1@test.com", principal=cls.principal)
        cls.dep2 = _cliente_base(cls.consultor, cls.django_user, email="dep2@test.com", principal=cls.principal)

    def test_dependentes_vinculados(self):
        self.assertEqual(self.principal.total_dependentes, 2)

    def test_dependente_is_dependente(self):
        self.assertTrue(self.dep1.is_dependente)
        self.assertFalse(self.dep1.is_principal)

    def test_dependente_referencia_principal(self):
        self.assertEqual(self.dep1.cliente_principal, self.principal)

    def test_cascade_delete_principal_remove_dependentes(self):
        dep_pk = self.dep1.pk
        self.principal.delete()
        self.assertFalse(ClienteConsultoria.objects.filter(pk=dep_pk).exists())


class ClienteSemViagemTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente sem viagem")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="semviagem@test.com")

    def test_cliente_sem_viagem_criado(self):
        self.assertIsNotNone(self.cliente.pk)
        self.assertEqual(self.cliente.viagens.count(), 0)


class ClienteComMembrosSemViagemTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente com membros, sem viagem")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="pnv@test.com")
        cls.dep = _cliente_base(cls.consultor, cls.django_user, email="depnv@test.com", principal=cls.principal)

    def test_ambos_sem_viagem(self):
        self.assertEqual(self.principal.viagens.count(), 0)
        self.assertEqual(self.dep.viagens.count(), 0)

    def test_total_dependentes(self):
        self.assertEqual(self.principal.total_dependentes, 1)


class ClienteComViagemSemMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente com viagem, sem membros")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="cvs@test.com")
        cls.pais = PaisDestino.objects.create(nome="Portugal CVS", codigo_iso="PRT", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo CVS", criado_por=cls.django_user)
        cls.viagem = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto,
            data_prevista_viagem=datetime.date(2026, 8, 1),
            data_prevista_retorno=datetime.date(2026, 8, 15),
            valor_assessoria=1500.00,
            criado_por=cls.django_user,
        )
        cls.viagem.clientes.add(cls.cliente)

    def test_cliente_vinculado_a_viagem(self):
        self.assertEqual(self.viagem.clientes.count(), 1)
        self.assertIn(self.cliente, self.viagem.clientes.all())

    def test_cliente_viagem_criado(self):
        self.assertTrue(ClienteViagem.objects.filter(viagem=self.viagem, cliente=self.cliente).exists())


class ClienteComViagemComMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente com viagem e membros (mesmo visto)")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="pcvm@test.com")
        cls.dep = _cliente_base(cls.consultor, cls.django_user, email="dcvm@test.com", principal=cls.principal)
        cls.pais = PaisDestino.objects.create(nome="Espanha CVM", codigo_iso="ESP", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo CVM", criado_por=cls.django_user)
        cls.viagem = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto,
            data_prevista_viagem=datetime.date(2026, 9, 1),
            data_prevista_retorno=datetime.date(2026, 9, 20),
            criado_por=cls.django_user,
        )
        cls.viagem.clientes.add(cls.principal)
        cls.viagem.clientes.add(cls.dep)

    def test_ambos_na_mesma_viagem(self):
        self.assertEqual(self.viagem.clientes.count(), 2)
        self.assertIn(self.principal, self.viagem.clientes.all())
        self.assertIn(self.dep, self.viagem.clientes.all())


class ClienteComViagemMembroVistosDiferentesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Membro com tipo visto diferente — viagem separada")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="pvd_p@test.com")
        cls.dep = _cliente_base(cls.consultor, cls.django_user, email="pvd_d@test.com", principal=cls.principal)
        cls.pais = PaisDestino.objects.create(nome="Italia VD", codigo_iso="ITA", criado_por=cls.django_user)
        cls.visto_a = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo VD A", criado_por=cls.django_user)
        cls.visto_b = TipoVisto.objects.create(pais_destino=cls.pais, nome="Estudante VD B", criado_por=cls.django_user)
        cls.viagem_principal = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto_a,
            data_prevista_viagem=datetime.date(2026, 10, 1),
            data_prevista_retorno=datetime.date(2026, 10, 30),
            criado_por=cls.django_user,
        )
        cls.viagem_dep = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto_b,
            data_prevista_viagem=datetime.date(2026, 10, 1),
            data_prevista_retorno=datetime.date(2026, 10, 30),
            criado_por=cls.django_user,
        )
        cls.viagem_principal.clientes.add(cls.principal)
        cls.viagem_dep.clientes.add(cls.dep)
        ClienteViagem.objects.filter(viagem=cls.viagem_dep, cliente=cls.dep).update(tipo_visto=cls.visto_b)

    def test_viagens_distintas(self):
        self.assertNotEqual(self.viagem_principal.pk, self.viagem_dep.pk)

    def test_tipos_visto_diferentes(self):
        cv = ClienteViagem.objects.get(viagem=self.viagem_dep, cliente=self.dep)
        self.assertEqual(cv.tipo_visto, self.visto_b)
        self.assertNotEqual(cv.tipo_visto, self.visto_a)


class ClienteComParceiroTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Cliente com parceiro indicador")
        cls.consultor, cls.django_user = _setup_base()
        cls.parceiro = Partner.objects.create(
            nome_responsavel="Parceiro Indicador",
            email="parceiro.ind@test.com",
            senha="x",
            criado_por=cls.django_user,
            segmento="outros",
        )
        cls.cliente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Parceiro",
            cpf="138.280.720-05",
            data_nascimento=datetime.date(1985, 3, 20),
            nacionalidade="Brasileiro",
            telefone="(21) 98888-8888",
            email="cliparc@test.com",
            senha="hash",
            criado_por=cls.django_user,
            parceiro_indicador=cls.parceiro,
        )

    def test_parceiro_vinculado(self):
        self.assertEqual(self.cliente.parceiro_indicador, self.parceiro)

    def test_cliente_aparece_no_parceiro(self):
        self.assertIn(self.cliente, self.parceiro.clientes_indicados.all())


class ClienteEtapasCadastroTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Etapas booleanas de cadastro do cliente")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="etapas@test.com")

    def test_marcar_etapa_dados_pessoais(self):
        self.cliente.etapa_dados_pessoais = True
        self.cliente.save()
        atualizado = ClienteConsultoria.objects.get(pk=self.cliente.pk)
        self.assertTrue(atualizado.etapa_dados_pessoais)

    def test_marcar_etapa_endereco(self):
        self.cliente.etapa_endereco = True
        self.cliente.save()
        atualizado = ClienteConsultoria.objects.get(pk=self.cliente.pk)
        self.assertTrue(atualizado.etapa_endereco)

    def test_marcar_etapa_membros(self):
        self.cliente.etapa_membros = True
        self.cliente.save()
        atualizado = ClienteConsultoria.objects.get(pk=self.cliente.pk)
        self.assertTrue(atualizado.etapa_membros)

    def test_marcar_etapa_passaporte(self):
        self.cliente.etapa_passaporte = True
        self.cliente.save()
        atualizado = ClienteConsultoria.objects.get(pk=self.cliente.pk)
        self.assertTrue(atualizado.etapa_passaporte)


class ClientePassaporteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Dados de passaporte do cliente")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Passaporte",
            cpf="699.034.060-00",
            data_nascimento=datetime.date(1980, 1, 1),
            nacionalidade="Brasileiro",
            telefone="(11) 99999-0000",
            email="passport@test.com",
            senha="hash",
            criado_por=cls.django_user,
            tipo_passaporte="comum",
            numero_passaporte="BR123456",
            pais_emissor_passaporte="Brasil",
            data_emissao_passaporte=datetime.date(2018, 1, 1),
            valido_ate_passaporte=datetime.date(2028, 1, 1),
            autoridade_passaporte="DPF",
            cidade_emissao_passaporte="São Paulo",
            passaporte_roubado=False,
        )

    def test_dados_passaporte_gravados(self):
        c = ClienteConsultoria.objects.get(pk=self.cliente.pk)
        self.assertEqual(c.numero_passaporte, "BR123456")
        self.assertEqual(c.pais_emissor_passaporte, "Brasil")
        self.assertFalse(c.passaporte_roubado)


class ClienteEditarExcluirTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_clientes.py] Editar e excluir cliente")
        cls.consultor, cls.django_user = _setup_base()

    def test_editar_email(self):
        cliente = _cliente_base(self.consultor, self.django_user, email="edit@test.com")
        cliente.email = "edit_novo@test.com"
        cliente.save()
        atualizado = ClienteConsultoria.objects.get(pk=cliente.pk)
        self.assertEqual(atualizado.email, "edit_novo@test.com")

    def test_excluir_cliente_sem_dependentes(self):
        cliente = _cliente_base(self.consultor, self.django_user, email="del@test.com")
        pk = cliente.pk
        cliente.delete()
        self.assertFalse(ClienteConsultoria.objects.filter(pk=pk).exists())

    def test_email_duplicado_levanta_erro(self):
        _cliente_base(self.consultor, self.django_user, email="dup@test.com")
        with self.assertRaises(Exception):
            _cliente_base(self.consultor, self.django_user, email="dup@test.com")
