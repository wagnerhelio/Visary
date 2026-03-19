import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from consultancy.models import ClienteConsultoria, EtapaCadastroCliente
from system.models import Modulo, Perfil, UsuarioConsultoria
from system.views.client_views import _processar_finalizacao_etapa_membros


User = get_user_model()


def _setup_admin():
    modulo = Modulo.objects.create(nome="Integ Clientes CPF", slug="integ-clientes-cpf")
    perfil = Perfil.objects.create(
        nome="Admin Integ CPF",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Integ CPF",
        email="admin.cpf@test.com",
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


def _cpf_digits(cpf: str) -> str:
    return "".join(ch for ch in cpf if ch.isdigit())


class CpfDuplicadoDependenteFinalizacaoMembrosTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.consultor, cls.django_user = _setup_admin()

                                                                       
        cls.etapa_membros = EtapaCadastroCliente.objects.create(
            nome="Etapa Membros (Teste)",
            descricao="Teste",
            ordem=10,
            ativo=True,
            campo_booleano="etapa_membros",
        )

        cls.etapas = EtapaCadastroCliente.objects.all()

                                                       
        cls.cpf_existente_formatted = "529.982.247-25"
        cls.cpf_existente_digits = _cpf_digits(cls.cpf_existente_formatted)

        cls.cpf_principal_distinto_formatted = "021.981.890-37"
        cls.cpf_principal_distinto_digits = _cpf_digits(cls.cpf_principal_distinto_formatted)

        cls.cpf_dependente_input_formatted = cls.cpf_existente_formatted
        cls.cpf_dependente_input_digits = cls.cpf_existente_digits

    def _criar_request_com_sessao(self, *, principal_cpf: str, dependente_cpf: str):
        factory = RequestFactory()
        request = factory.post("/cadastrar_cliente", data={})

                                                         
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        request.user = self.django_user

        request._messages = FallbackStorage(request)

        request.session["cliente_dados_temporarios"] = {
            "assessor_responsavel": self.consultor.pk,
            "nome": "Principal Teste CPF",
            "cpf": principal_cpf,
            "data_nascimento": datetime.date(1990, 1, 1),
            "nacionalidade": "Brasileiro",
            "telefone": "(11) 99999-0000",
            "email": "principal.cpf@test.com",
                                                                                         
            "senha": "SenhaPrincipal123",
        }

        request.session["dependentes_temporarios"] = [
            {
                "nome": "Dependente Teste CPF",
                "cpf": dependente_cpf,
                "data_nascimento": "1995-05-10",
                "nacionalidade": "Brasileiro",
                "telefone": "(11) 88888-1111",
                "email": "",
                "assessor_responsavel": self.consultor.pk,
                                                                                         
                "usar_dados_cliente_principal": True,
            }
        ]

        return request

    def test_bloqueia_finalizacao_quando_dependente_cpf_duplicado_formatacao_diferente(self):
                                           
        existente = ClienteConsultoria.objects.create(
            assessor_responsavel=self.consultor,
            nome="Principal Existente CPF (Formatted)",
            cpf=self.cpf_existente_formatted,
            data_nascimento=datetime.date(1980, 2, 2),
            nacionalidade="Brasileiro",
            telefone="(11) 77777-2222",
            email="existente.cpf@test.com",
            senha=make_password("SenhaQualquer123"),
            criado_por=self.django_user,
        )

        before_count = ClienteConsultoria.objects.count()

        request = self._criar_request_com_sessao(
            principal_cpf=self.cpf_principal_distinto_formatted,
            dependente_cpf=self.cpf_dependente_input_digits,                            
        )

        resp = _processar_finalizacao_etapa_membros(request, self.etapa_membros, self.etapas)

        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"etapa_id={self.etapa_membros.pk}", resp.url)
        self.assertEqual(ClienteConsultoria.objects.count(), before_count)

                                                                     
        self.assertIn("dependentes_temporarios", request.session)
        self.assertTrue(request.session.get("dependentes_temporarios"))

                                                       
        messages = [m.message for m in request._messages]
        self.assertTrue(any("Dependente" in m for m in messages))

    def test_bloqueia_finalizacao_quando_dependente_cpf_duplicado_armazenado_em_digitos(self):
                                                                    
        ClienteConsultoria.objects.create(
            assessor_responsavel=self.consultor,
            nome="Principal Existente CPF (Digits)",
            cpf=self.cpf_existente_digits,
            data_nascimento=datetime.date(1982, 3, 3),
            nacionalidade="Brasileiro",
            telefone="(11) 66666-3333",
            email="existente.cpf.digits@test.com",
            senha=make_password("SenhaQualquer123"),
            criado_por=self.django_user,
        )

        before_count = ClienteConsultoria.objects.count()

        request = self._criar_request_com_sessao(
            principal_cpf=self.cpf_principal_distinto_formatted,
            dependente_cpf=self.cpf_dependente_input_formatted,                    
        )

        resp = _processar_finalizacao_etapa_membros(request, self.etapa_membros, self.etapas)

        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"etapa_id={self.etapa_membros.pk}", resp.url)
        self.assertEqual(ClienteConsultoria.objects.count(), before_count)
        self.assertIn("dependentes_temporarios", request.session)

