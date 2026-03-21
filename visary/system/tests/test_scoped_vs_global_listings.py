from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import (
    ClienteConsultoria,
    FormularioVisto,
    PaisDestino,
    Perfil,
    Processo,
    TipoVisto,
    UsuarioConsultoria,
    Viagem,
)


User = get_user_model()


class ScopedVsGlobalListingsTests(TestCase):
    def setUp(self):
        self.perfil_atendente = Perfil.objects.create(
            nome="Atendente Teste",
            pode_criar=False,
            pode_visualizar=True,
            pode_atualizar=False,
            pode_excluir=False,
            ativo=True,
        )

        self.assessor_a = UsuarioConsultoria.objects.create(
            nome="Assessor A",
            email="assessor.a@visary.test",
            senha="hash",
            perfil=self.perfil_atendente,
            ativo=True,
        )
        self.assessor_b = UsuarioConsultoria.objects.create(
            nome="Assessor B",
            email="assessor.b@visary.test",
            senha="hash",
            perfil=self.perfil_atendente,
            ativo=True,
        )

        self.auth_user_a = User.objects.create_user(
            username=self.assessor_a.email,
            email=self.assessor_a.email,
            password="senha-segura-123",
        )
        self.auth_user_b = User.objects.create_user(
            username=self.assessor_b.email,
            email=self.assessor_b.email,
            password="senha-segura-123",
        )

        self.cliente_a = self._criar_cliente(
            nome="Cliente Assessor A",
            cpf="111.111.111-11",
            assessor=self.assessor_a,
            criado_por=self.auth_user_a,
        )
        self.cliente_b = self._criar_cliente(
            nome="Cliente Assessor B",
            cpf="222.222.222-22",
            assessor=self.assessor_b,
            criado_por=self.auth_user_b,
        )

        self.pais = PaisDestino.objects.create(
            nome="Canada",
            codigo_iso="CAN",
            ativo=True,
            criado_por=self.auth_user_a,
        )
        self.tipo_visto = TipoVisto.objects.create(
            pais_destino=self.pais,
            nome="Turismo",
            descricao="",
            ativo=True,
            criado_por=self.auth_user_a,
        )
        FormularioVisto.objects.create(tipo_visto=self.tipo_visto, ativo=True)

        self.viagem_a = Viagem.objects.create(
            assessor_responsavel=self.assessor_a,
            pais_destino=self.pais,
            tipo_visto=self.tipo_visto,
            data_prevista_viagem=date(2026, 6, 1),
            data_prevista_retorno=date(2026, 6, 20),
            valor_assessoria=1000,
            criado_por=self.auth_user_a,
        )
        self.viagem_a.clientes.add(self.cliente_a)

        self.viagem_b = Viagem.objects.create(
            assessor_responsavel=self.assessor_b,
            pais_destino=self.pais,
            tipo_visto=self.tipo_visto,
            data_prevista_viagem=date(2026, 7, 1),
            data_prevista_retorno=date(2026, 7, 20),
            valor_assessoria=1500,
            criado_por=self.auth_user_b,
        )
        self.viagem_b.clientes.add(self.cliente_b)

        Processo.objects.create(
            viagem=self.viagem_a,
            cliente=self.cliente_a,
            assessor_responsavel=self.assessor_a,
            criado_por=self.auth_user_a,
        )
        Processo.objects.create(
            viagem=self.viagem_b,
            cliente=self.cliente_b,
            assessor_responsavel=self.assessor_b,
            criado_por=self.auth_user_b,
        )

    def _criar_cliente(self, nome, cpf, assessor, criado_por):
        return ClienteConsultoria.objects.create(
            assessor_responsavel=assessor,
            nome=nome,
            cpf=cpf,
            data_nascimento=date(1990, 1, 1),
            nacionalidade="Brasileira",
            telefone="(11) 99999-9999",
            email=f"{cpf.replace('.', '').replace('-', '')}@email.test",
            senha="hash",
            criado_por=criado_por,
        )

    def test_home_clientes_mostra_apenas_clientes_vinculados_ao_assessor(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:home_clientes"))

        self.assertEqual(response.status_code, 200)
        nomes = {item["cliente"].nome for item in response.context["clientes_com_status"]}
        self.assertIn(self.cliente_a.nome, nomes)
        self.assertNotIn(self.cliente_b.nome, nomes)

    def test_listar_clientes_exibe_todos_os_clientes_independente_do_assessor(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:listar_clientes_view"))

        self.assertEqual(response.status_code, 200)
        nomes = {item["cliente"].nome for item in response.context["clientes_com_status"]}
        self.assertIn(self.cliente_a.nome, nomes)
        self.assertIn(self.cliente_b.nome, nomes)

    def test_listar_viagens_exibe_viagens_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:listar_viagens"))

        self.assertEqual(response.status_code, 200)
        viagens_ids = {item["viagem"].pk for item in response.context["viagens_com_info"]}
        self.assertIn(self.viagem_a.pk, viagens_ids)
        self.assertIn(self.viagem_b.pk, viagens_ids)

    def test_listar_processos_exibe_processos_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:listar_processos"))

        self.assertEqual(response.status_code, 200)
        processos_clientes = {processo.cliente_id for processo in response.context["processos"]}
        self.assertIn(self.cliente_a.pk, processos_clientes)
        self.assertIn(self.cliente_b.pk, processos_clientes)

    def test_listar_formularios_exibe_clientes_de_todos_os_assessores(self):
        self.client.force_login(self.auth_user_a)

        response = self.client.get(reverse("system:listar_formularios"))

        self.assertEqual(response.status_code, 200)
        clientes_ids = {
            cliente_info["cliente"].pk
            for item in response.context["formularios_respostas"]
            for cliente_info in item["clientes"]
        }
        self.assertIn(self.cliente_a.pk, clientes_ids)
        self.assertIn(self.cliente_b.pk, clientes_ids)
