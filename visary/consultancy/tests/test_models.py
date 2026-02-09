import datetime
from django.db.utils import IntegrityError
from django.urls import reverse
from django.test import TestCase

from consultancy.models import (
    ClienteConsultoria,
    Partner,
    Viagem,
    ClienteViagem,
    PaisDestino,
    TipoVisto,
    FormularioVisto,
    PerguntaFormulario,
    OpcaoSelecao,
    RespostaFormulario,
)
from consultancy.apps import ConsultancyConfig
from system.models import UsuarioConsultoria


class ConsultancyModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create security/domain objects required by models
        from system.models import Perfil, Modulo  # type: ignore
        from django.utils.text import slugify
        mod = Modulo.objects.create(nome="Test Modulo", slug=slugify("Test Modulo"))
        perfil = Perfil.objects.create(nome="Administrador", descricao="test", ativo=True)

        # Create a user to act as assessor/creator
        cls.user = UsuarioConsultoria.objects.create(
            nome="Administrador Teste",
            email="admin@example.com",
            perfil=perfil,
            ativo=True,
        )
        cls.user.set_password("adminpass")
        cls.user.save()

        # Related data for travels and clients
        cls.pais = PaisDestino.objects.create(nome="Brasil", codigo_iso="BRA")
        cls.tipo = TipoVisto.objects.create(pais_destino=cls.pais, nome="Turismo")

        cls.principal = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.user,
            nome="Cliente Principal",
            data_nascimento=datetime.date(1990, 1, 1),
            nacionalidade="Brasil",
            telefone="(11) 99999-9999",
            email="principal@example.com",
            senha="hash",
            criado_por=cls.user,
        )

        cls.dependente = ClienteConsultoria.objects.create(
            assessor_responsavel=cls.user,
            cliente_principal=cls.principal,
            nome="Dependente",
            data_nascimento=datetime.date(2010, 1, 1),
            nacionalidade="Brasil",
            telefone="(11) 99999-9998",
            email="dependente@example.com",
            senha="hash",
            criado_por=cls.user,
        )

    def test_cliente_crud_and_relations(self):
        # Read
        c = ClienteConsultoria.objects.get(pk=self.__class__.principal.pk)
        self.assertEqual(c.nome, "Cliente Principal")

        # Update
        c.email = "principal_updated@example.com"
        c.save()
        c_refresh = ClienteConsultoria.objects.get(pk=c.pk)
        self.assertEqual(c_refresh.email, "principal_updated@example.com")

        # Delete and ensure cascade safety (not deleting related objects here)
        dep_pk = self.__class__.dependente.pk
        self.__class__.dependente.delete()
        self.assertFalse(ClienteConsultoria.objects.filter(pk=dep_pk).exists())

    def test_dependece_and_principal_flags(self):
        self.assertTrue(self.__class__.principal.is_principal)
        self.assertFalse(self.__class__.principal.is_dependente)
        self.assertTrue(self.__class__.dependente.is_dependente)
        self.assertFalse(self.__class__.dependente.is_principal)

        self.assertIsInstance(self.__class__.principal.total_dependentes, int)

    def test_partner_crud_and_password(self):
        partner = Partner(
            nome_responsavel="Parceiro X",
            email="parceiro@example.com",
            senha="initial",
            criado_por=self.__class__.user,
        )
        partner.set_password("secret")
        partner.save()
        self.assertTrue(partner.check_password("secret"))

        partner.email = "parceiro2@example.com"
        partner.save()
        self.assertEqual(partner.email, "parceiro2@example.com")

    def test_pais_destino_and_tipo_visto_uniqueness(self):
        # Unique together on TipoVisto (pais_destino, nome)
        with self.assertRaises(IntegrityError):
            TipoVisto.objects.create(pais_destino=self.__class__.pais, nome=self.__class__.tipo.nome)

    def test_viagem_and_cliente_viagem(self):
        viagem = Viagem.objects.create(
            assessor_responsavel=self.user,
            pais_destino=self.pais,
            tipo_visto=self.tipo,
            data_prevista_viagem=datetime.date(2026, 12, 1),
            data_prevista_retorno=datetime.date(2026, 12, 15),
            valor_assessoria=0.00,
            criado_por=self.__class__.user,
        )
        viagem.clientes.add(self.__class__.principal)
        self.assertEqual(viagem.clientes.count(), 1)
        cv = ClienteViagem.objects.create(viagem=viagem, cliente=self.__class__.principal, tipo_visto=self.tipo)
        self.assertEqual(cv.viagem, viagem)

    def test_form_and_resposta_crud(self):
        formulario = FormularioVisto.objects.create(tipo_visto=self.tipo, ativo=True)
        pergunta = PerguntaFormulario.objects.create(
            formulario=formulario, pergunta="Qual o motivo da viagem?", tipo_campo="texto"
        )
        opcao = OpcaoSelecao.objects.create(pergunta=pergunta, texto="Negócio", ordem=0)
        self.assertEqual(str(pergunta), f"{pergunta.pergunta} ({pergunta.get_tipo_campo_display()})" )

        viagem = Viagem.objects.create(
            assessor_responsavel=self.user,
            pais_destino=self.pais,
            tipo_visto=self.tipo,
            data_prevista_viagem=datetime.date(2026, 12, 1),
            data_prevista_retorno=datetime.date(2026, 12, 15),
            valor_assessoria=0.0,
            criado_por=self.__class__.user,
        )
        cliente = self.__class__.principal
        resp = {f"pergunta_{pergunta.pk}": "Alguma resposta"}
        r = RespostaFormulario.objects.create(
            viagem=viagem, cliente=cliente, pergunta=pergunta, resposta_texto="Alguma resposta"
        )
        self.assertIn("Alguma", r.get_resposta_display())
