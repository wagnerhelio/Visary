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
    FormularioVisto,
    PerguntaFormulario,
    RespostaFormulario,
    Financeiro,
    StatusFinanceiro,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_admin():
    modulo = Modulo.objects.create(nome="Fluxo Completo", slug="fluxo-completo")
    perfil = Perfil.objects.create(
        nome="Admin Fluxo Completo",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Fluxo",
        email="admin.fluxo@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.fluxo@test.com",
        defaults={"email": "admin.fluxo@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


class FluxoCompletoClienteSimplesSemMembroTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_06_integracao_fluxo_completo.py] Fluxo completo — cliente simples (sem membros)")
        cls.consultor, cls.django_user = _setup_admin()

        cls.pais = PaisDestino.objects.create(nome="Franca FC", codigo_iso="FFC", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo FC", criado_por=cls.django_user)

        cls.cliente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Cliente Fluxo Simples",
            data_nascimento=datetime.date(1985, 3, 15),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-7777",
            email="fluxo.simples@test.com",
            senha="hash",
            criado_por=cls.django_user,
        )

        cls.viagem = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto,
            data_prevista_viagem=datetime.date(2027, 3, 1),
            data_prevista_retorno=datetime.date(2027, 3, 15),
            valor_assessoria=2000.00,
            criado_por=cls.django_user,
        )
        cls.viagem.clientes.add(cls.cliente)

        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)
        cls.pergunta = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Tem seguro viagem?",
            tipo_campo="booleano",
            obrigatorio=True,
            ordem=1,
        )
        cls.resposta = RespostaFormulario.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            pergunta=cls.pergunta,
            resposta_booleano=True,
        )

        cls.status_doc = StatusProcesso.objects.create(nome="Documentação FC", ordem=1)
        cls.status_ent = StatusProcesso.objects.create(nome="Entrevista FC", ordem=2)

        cls.processo = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )
        cls.etapa1 = EtapaProcesso.objects.create(processo=cls.processo, status=cls.status_doc, ordem=1)
        cls.etapa2 = EtapaProcesso.objects.create(processo=cls.processo, status=cls.status_ent, ordem=2)

        cls.financeiro = Financeiro.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            assessor_responsavel=cls.consultor,
            valor=2000.00,
            status=StatusFinanceiro.PENDENTE,
            criado_por=cls.django_user,
        )

    def test_cliente_vinculado_a_viagem(self):
        self.assertIn(self.cliente, self.viagem.clientes.all())

    def test_formulario_respondido(self):
        self.assertEqual(self.resposta.get_resposta_display(), "Sim")

    def test_processo_com_duas_etapas(self):
        self.assertEqual(self.processo.total_etapas, 2)
        self.assertEqual(self.processo.etapas_concluidas, 0)
        self.assertEqual(self.processo.progresso_percentual, 0)

    def test_concluir_primeira_etapa_atualiza_progresso(self):
        self.etapa1.concluida = True
        self.etapa1.save()
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.etapas_concluidas, 1)
        self.assertEqual(self.processo.progresso_percentual, 50)

    def test_financeiro_pendente_inicial(self):
        self.assertEqual(self.financeiro.status, StatusFinanceiro.PENDENTE)

    def test_pagar_financeiro_muda_status(self):
        self.financeiro.status = StatusFinanceiro.PAGO
        self.financeiro.data_pagamento = datetime.date.today()
        self.financeiro.save()
        atualizado = Financeiro.objects.get(pk=self.financeiro.pk)
        self.assertEqual(atualizado.status, StatusFinanceiro.PAGO)


class FluxoCompletoClienteComMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_06_integracao_fluxo_completo.py] Fluxo completo — cliente com membros")
        cls.consultor, cls.django_user = _setup_admin()

        cls.pais = PaisDestino.objects.create(nome="Portugal FCM", codigo_iso="PCM", criado_por=cls.django_user)
        cls.visto = TipoVisto.objects.create(pais_destino=cls.pais, nome="Residencia FCM", criado_por=cls.django_user)

        cls.principal = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Principal Fluxo Membros",
            data_nascimento=datetime.date(1980, 5, 20),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-8888",
            email="principal.fcm@test.com",
            senha="hash",
            criado_por=cls.django_user,
        )
        cls.dep1 = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.consultor,
            nome="Dependente FCM 1",
            data_nascimento=datetime.date(2005, 1, 1),
            nacionalidade="Brasileiro",
            telefone="(11) 91111-9999",
            email="dep1.fcm@test.com",
            senha="hash",
            criado_por=cls.django_user,
            cliente_principal=cls.principal,
        )

        cls.viagem = Viagem.objects.create(
            assessor_responsavel=cls.consultor,
            pais_destino=cls.pais,
            tipo_visto=cls.visto,
            data_prevista_viagem=datetime.date(2027, 6, 1),
            data_prevista_retorno=datetime.date(2027, 8, 31),
            valor_assessoria=5000.00,
            criado_por=cls.django_user,
        )
        cls.viagem.clientes.add(cls.principal, cls.dep1)

        cls.proc_principal = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.principal,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )
        cls.proc_dep1 = Processo.objects.create(
            viagem=cls.viagem,
            cliente=cls.dep1,
            assessor_responsavel=cls.consultor,
            criado_por=cls.django_user,
        )

        cls.fin_principal = Financeiro.objects.create(
            viagem=cls.viagem,
            cliente=cls.principal,
            assessor_responsavel=cls.consultor,
            valor=3000.00,
            status=StatusFinanceiro.PENDENTE,
            criado_por=cls.django_user,
        )
        cls.fin_dep1 = Financeiro.objects.create(
            viagem=cls.viagem,
            cliente=cls.dep1,
            assessor_responsavel=cls.consultor,
            valor=2000.00,
            status=StatusFinanceiro.PENDENTE,
            criado_por=cls.django_user,
        )

    def test_principal_tem_dependente(self):
        self.assertEqual(self.principal.total_dependentes, 1)

    def test_ambos_na_viagem(self):
        clientes = self.viagem.clientes.all()
        self.assertIn(self.principal, clientes)
        self.assertIn(self.dep1, clientes)

    def test_dois_processos_na_viagem(self):
        self.assertEqual(self.viagem.processos.count(), 2)

    def test_pagamento_principal_propaga_dependente(self):
        self.fin_principal.status = StatusFinanceiro.PAGO
        self.fin_principal.save()
        self.fin_dep1.refresh_from_db()
        self.assertEqual(self.fin_dep1.status, StatusFinanceiro.PAGO)

    def test_excluir_principal_remove_dependente(self):
        dep_pk = self.dep1.pk
        self.principal.delete()
        self.assertFalse(ClienteConsultoria.objects.filter(pk=dep_pk).exists())
