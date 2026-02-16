import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    PaisDestino,
    TipoVisto,
    Viagem,
    FormularioVisto,
    PerguntaFormulario,
    OpcaoSelecao,
    RespostaFormulario,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Formularios Base", slug="formularios-base")
    perfil = Perfil.objects.create(
        nome="Admin Formularios",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Formularios",
        email="admin.forms@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.forms@test.com",
        defaults={"email": "admin.forms@test.com", "is_active": True},
    )
    django_user.set_password("senha123")
    django_user.save()
    return consultor, django_user


def _pais_visto_viagem(consultor, django_user, sufixo="A"):
    pais = PaisDestino.objects.create(nome=f"Pais Form {sufixo}", codigo_iso=f"F{sufixo[:2]}", criado_por=django_user)
    visto = TipoVisto.objects.create(pais_destino=pais, nome=f"Turismo Form {sufixo}", criado_por=django_user)
    viagem = Viagem.objects.create(
        assessor_responsavel=consultor,
        pais_destino=pais,
        tipo_visto=visto,
        data_prevista_viagem=datetime.date(2026, 10, 1),
        data_prevista_retorno=datetime.date(2026, 10, 15),
        criado_por=django_user,
    )
    return pais, visto, viagem


def _cliente_base(consultor, django_user, email="cli.form@test.com"):
    return ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome="Cliente Form",
        data_nascimento=datetime.date(1990, 1, 1),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-1111",
        email=email,
        senha="hash",
        criado_por=django_user,
    )


class FormularioVistoCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_formularios.py] Criação de FormularioVisto")
        cls.consultor, cls.django_user = _setup_base()
        _, cls.visto, _ = _pais_visto_viagem(cls.consultor, cls.django_user, sufixo="FV")
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.formulario.pk)

    def test_str_contem_nome_visto(self):
        self.assertIn("Turismo Form FV", str(self.formulario))

    def test_ativo_por_padrao(self):
        self.assertTrue(self.formulario.ativo)

    def test_onetone_unico_por_tipo_visto(self):
        with self.assertRaises(Exception):
            FormularioVisto.objects.create(tipo_visto=self.visto)


class PerguntaFormularioTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_formularios.py] Perguntas do formulário")
        cls.consultor, cls.django_user = _setup_base()
        _, cls.visto, _ = _pais_visto_viagem(cls.consultor, cls.django_user, sufixo="PF")
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)
        cls.perg_texto = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Qual é o seu nome completo?",
            tipo_campo="texto",
            obrigatorio=True,
            ordem=1,
        )
        cls.perg_data = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Qual é a data de nascimento?",
            tipo_campo="data",
            ordem=2,
        )
        cls.perg_sel = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Qual é o estado civil?",
            tipo_campo="selecao",
            ordem=3,
        )

    def test_total_perguntas(self):
        self.assertEqual(self.formulario.perguntas.count(), 3)

    def test_pergunta_texto_obrigatoria(self):
        self.assertTrue(self.perg_texto.obrigatorio)

    def test_pergunta_data_nao_obrigatoria(self):
        self.assertFalse(self.perg_data.obrigatorio)

    def test_str_contem_pergunta_e_tipo(self):
        self.assertIn("Qual é o seu nome completo?", str(self.perg_texto))
        self.assertIn("Texto", str(self.perg_texto))

    def test_unique_together_formulario_ordem(self):
        with self.assertRaises(Exception):
            PerguntaFormulario.objects.create(
                formulario=self.formulario,
                pergunta="Outra pergunta",
                tipo_campo="texto",
                ordem=1,
            )


class OpcaoSelecaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_formularios.py] Opções de seleção")
        cls.consultor, cls.django_user = _setup_base()
        _, cls.visto, _ = _pais_visto_viagem(cls.consultor, cls.django_user, sufixo="OS")
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)
        cls.pergunta = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Estado civil",
            tipo_campo="selecao",
            ordem=1,
        )
        cls.opcao1 = OpcaoSelecao.objects.create(pergunta=cls.pergunta, texto="Solteiro", ordem=1)
        cls.opcao2 = OpcaoSelecao.objects.create(pergunta=cls.pergunta, texto="Casado", ordem=2)
        cls.opcao3 = OpcaoSelecao.objects.create(pergunta=cls.pergunta, texto="Divorciado", ordem=3)

    def test_total_opcoes(self):
        self.assertEqual(self.pergunta.opcoes.count(), 3)

    def test_str_contem_texto_e_pergunta(self):
        self.assertIn("Solteiro", str(self.opcao1))

    def test_unique_together_pergunta_ordem(self):
        with self.assertRaises(Exception):
            OpcaoSelecao.objects.create(pergunta=self.pergunta, texto="Outro", ordem=1)


class RespostaFormularioTextoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_formularios.py] Resposta de formulário — texto")
        cls.consultor, cls.django_user = _setup_base()
        _, cls.visto, cls.viagem = _pais_visto_viagem(cls.consultor, cls.django_user, sufixo="RT")
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="resp.txt@test.com")
        cls.viagem.clientes.add(cls.cliente)
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)
        cls.pergunta = PerguntaFormulario.objects.create(
            formulario=cls.formulario,
            pergunta="Profissão",
            tipo_campo="texto",
            ordem=1,
        )
        cls.resposta = RespostaFormulario.objects.create(
            viagem=cls.viagem,
            cliente=cls.cliente,
            pergunta=cls.pergunta,
            resposta_texto="Engenheiro",
        )

    def test_criada_com_sucesso(self):
        self.assertIsNotNone(self.resposta.pk)

    def test_get_resposta_display_texto(self):
        self.assertEqual(self.resposta.get_resposta_display(), "Engenheiro")

    def test_str_contem_cliente_e_pergunta(self):
        self.assertIn("Cliente Form", str(self.resposta))
        self.assertIn("Profissão", str(self.resposta))


class RespostaFormularioDiversosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_formularios.py] Respostas de formulário — diversos tipos")
        cls.consultor, cls.django_user = _setup_base()
        _, cls.visto, cls.viagem = _pais_visto_viagem(cls.consultor, cls.django_user, sufixo="RD")
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="resp.div@test.com")
        cls.viagem.clientes.add(cls.cliente)
        cls.formulario = FormularioVisto.objects.create(tipo_visto=cls.visto)
        cls.perg_data = PerguntaFormulario.objects.create(
            formulario=cls.formulario, pergunta="Data entrada", tipo_campo="data", ordem=1
        )
        cls.perg_num = PerguntaFormulario.objects.create(
            formulario=cls.formulario, pergunta="Renda mensal", tipo_campo="numero", ordem=2
        )
        cls.perg_bool = PerguntaFormulario.objects.create(
            formulario=cls.formulario, pergunta="Tem passagem?", tipo_campo="booleano", ordem=3
        )
        cls.resp_data = RespostaFormulario.objects.create(
            viagem=cls.viagem, cliente=cls.cliente, pergunta=cls.perg_data,
            resposta_data=datetime.date(2026, 11, 1),
        )
        cls.resp_num = RespostaFormulario.objects.create(
            viagem=cls.viagem, cliente=cls.cliente, pergunta=cls.perg_num,
            resposta_numero=5000.00,
        )
        cls.resp_bool = RespostaFormulario.objects.create(
            viagem=cls.viagem, cliente=cls.cliente, pergunta=cls.perg_bool,
            resposta_booleano=True,
        )

    def test_display_data(self):
        self.assertEqual(self.resp_data.get_resposta_display(), "01/11/2026")

    def test_display_numero(self):
        self.assertIn("5000", self.resp_num.get_resposta_display())

    def test_display_booleano_sim(self):
        self.assertEqual(self.resp_bool.get_resposta_display(), "Sim")

    def test_unique_together_viagem_cliente_pergunta(self):
        with self.assertRaises(Exception):
            RespostaFormulario.objects.create(
                viagem=self.viagem,
                cliente=self.cliente,
                pergunta=self.perg_data,
                resposta_data=datetime.date(2026, 12, 1),
            )
