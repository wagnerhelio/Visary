import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    PaisDestino,
    TipoVisto,
    Viagem,
    Processo,
    EtapaProcesso,
    StatusProcesso,
    ViagemStatusProcesso,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Processos Base", slug="processos-base")
    perfil = Perfil.objects.create(
        nome="Admin Processos",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Processos",
        email="admin.processos@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.processos@test.com",
        defaults={"email": "admin.processos@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


def _cliente_base(consultor, django_user, email="cli.proc@test.com"):
    return ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome="Cliente Processo",
        data_nascimento=datetime.date(1990, 1, 1),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-1111",
        email=email,
        senha="hash",
        criado_por=django_user,
    )


def _viagem_base(consultor, django_user, sufixo="A"):
    pais = PaisDestino.objects.create(nome=f"Pais Proc {sufixo}", codigo_iso=f"P{sufixo[:2]}", criado_por=django_user)
    visto = TipoVisto.objects.create(pais_destino=pais, nome=f"Turismo Proc {sufixo}", criado_por=django_user)
    viagem = Viagem.objects.create(
        assessor_responsavel=consultor,
        pais_destino=pais,
        tipo_visto=visto,
        data_prevista_viagem=datetime.date(2026, 9, 1),
        data_prevista_retorno=datetime.date(2026, 9, 15),
        criado_por=django_user,
    )
    return viagem


class StatusProcessoCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] Criação de StatusProcesso")
        cls.status = StatusProcesso.objects.create(
            nome="Documentação",
            prazo_padrao_dias=10,
            ordem=1,
        )

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.status.pk)

    def test_str_sem_tipo_visto(self):
        self.assertEqual(str(self.status), "Documentação")

    def test_ativo_por_padrao(self):
        self.assertTrue(self.status.ativo)

    def test_prazo_padrao(self):
        self.assertEqual(self.status.prazo_padrao_dias, 10)


class StatusProcessoComTipoVistoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] StatusProcesso vinculado a tipo de visto")
        cls.consultor, cls.django_user = _setup_base()
        cls.pais = PaisDestino.objects.create(nome="StatusPais", codigo_iso="STP", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="StatusVisto", criado_por=cls.django_user)
        cls.status = StatusProcesso.objects.create(
            nome="Entrevista",
            tipo_visto=cls.visto,
            ordem=2,
        )

    def test_str_contem_visto_e_nome(self):
        self.assertIn("StatusVisto", str(self.status))
        self.assertIn("Entrevista", str(self.status))


class ProcessoCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] Criação de processo")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="processo.cri@test.com")
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="CR")
        cls.viagem.clientes.add(cls.cliente)
        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.processo.pk)

    def test_str_contem_cliente_e_viagem(self):
        self.assertIn("Cliente Processo", str(self.processo))

    def test_sem_etapas_inicialmente(self):
        self.assertEqual(self.processo.total_etapas, 0)
        self.assertEqual(self.processo.etapas_concluidas, 0)

    def test_progresso_zero_sem_etapas(self):
        self.assertEqual(self.processo.progresso_percentual, 0)

    def test_unique_together_viagem_cliente(self):
        with self.assertRaises(Exception):
            Processo.objects.create(
                viagem=self.viagem,
                cliente=self.cliente,
                assessor_responsavel=self.consultor,
                criado_por=self.django_user,
            )


class ProcessoComEtapasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] Processo com etapas")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="etapa.proc@test.com")
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="ET")
        cls.viagem.clientes.add(cls.cliente)
        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )
        cls.status1 = StatusProcesso.objects.create(nome="Etapa 1", ordem=1)
        cls.status2 = StatusProcesso.objects.create(nome="Etapa 2", ordem=2)
        cls.status3 = StatusProcesso.objects.create(nome="Etapa 3", ordem=3)
        cls.etapa1 = EtapaProcesso.objects.create(processo=cls.processo, status=cls.status1, ordem=1)
        cls.etapa2 = EtapaProcesso.objects.create(processo=cls.processo, status=cls.status2, ordem=2)
        cls.etapa3 = EtapaProcesso.objects.create(processo=cls.processo, status=cls.status3, concluida=True, ordem=3)

    def test_total_etapas(self):
        self.assertEqual(self.processo.total_etapas, 3)

    def test_etapas_concluidas(self):
        self.assertEqual(self.processo.etapas_concluidas, 1)

    def test_progresso_percentual(self):
        self.assertEqual(self.processo.progresso_percentual, 33)

    def test_str_etapa_concluida(self):
        self.assertIn("✓", str(self.etapa3))

    def test_str_etapa_nao_concluida(self):
        self.assertIn("○", str(self.etapa1))


class EtapaConcluidaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] Marcar etapa como concluída")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="conc.etapa@test.com")
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="CO")
        cls.viagem.clientes.add(cls.cliente)
        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )
        cls.status = StatusProcesso.objects.create(nome="Concluir Etapa", ordem=1)
        cls.etapa = EtapaProcesso.objects.create(
            processo=cls.processo,
            status=cls.status,
            ordem=1,
        )

    def test_concluir_etapa(self):
        self.etapa.concluida = True
        self.etapa.data_conclusao = datetime.date.today()
        self.etapa.save()
        atualizada = EtapaProcesso.objects.get(pk=self.etapa.pk)
        self.assertTrue(atualizada.concluida)
        self.assertEqual(atualizada.data_conclusao, datetime.date.today())


class ViagemStatusProcessoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] ViagemStatusProcesso")
        cls.consultor, cls.django_user = _setup_base()
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="VS")
        cls.status = StatusProcesso.objects.create(nome="Status Viagem", ordem=1)
        cls.vsp = ViagemStatusProcesso.objects.create(
            viagem=cls.viagem,
            status=cls.status,
        )

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.vsp.pk)

    def test_ativo_por_padrao(self):
        self.assertTrue(self.vsp.ativo)

    def test_unique_together_viagem_status(self):
        with self.assertRaises(Exception):
            ViagemStatusProcesso.objects.create(
                viagem=self.viagem,
                status=self.status,
            )


class ProcessoCascadeDeleteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_processos.py] Cascade delete em processo")
        cls.consultor, cls.django_user = _setup_base()

    def test_delete_viagem_remove_processo(self):
        viagem = _viagem_base(self.consultor, self.django_user, sufixo="DV")
        cliente = _cliente_base(self.consultor, self.django_user, email="del.proc.v@test.com")
        viagem.clientes.add(cliente)
        processo = Processo.objects.create(
            viagem=viagem,
            cliente=cliente,
            assessor_responsavel=self.consultor,
            criado_por=self.django_user,
        )
        proc_pk = processo.pk
        viagem.delete()
        self.assertFalse(Processo.objects.filter(pk=proc_pk).exists())
