import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from consultancy.models import (
    ClienteConsultoria,
    PaisDestino,
    TipoVisto,
    Viagem,
    Financeiro,
    StatusFinanceiro,
)
from system.models import Modulo, Perfil, UsuarioConsultoria

User = get_user_model()


def _setup_base():
    modulo = Modulo.objects.create(nome="Financeiro Base", slug="financeiro-base")
    perfil = Perfil.objects.create(
        nome="Admin Financeiro",
        pode_criar=True,
        pode_visualizar=True,
        pode_atualizar=True,
        pode_excluir=True,
    )
    perfil.modulos.add(modulo)
    consultor = UsuarioConsultoria.objects.create(
        nome="Admin Financeiro",
        email="admin.fin@test.com",
        perfil=perfil,
        ativo=True,
    )
    consultor.set_password("senha123")
    consultor.save()
    django_user, _ = User.objects.get_or_create(
        username="admin.fin@test.com",
        defaults={"email": "admin.fin@test.com", "is_active": True},
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


def _cliente_base(consultor, django_user, email="cli.fin@test.com", principal=None, cpf=None):
    return ClienteConsultoria.objects.create(
        assessor_responsavel=consultor,
        nome="Cliente Fin",
        cpf=cpf or _cpf_from_email(email),
        data_nascimento=datetime.date(1990, 1, 1),
        nacionalidade="Brasileiro",
        telefone="(11) 91111-1111",
        email=email,
        senha="hash",
        criado_por=django_user,
        cliente_principal=principal,
    )


def _viagem_base(consultor, django_user, sufixo="A"):
    pais = PaisDestino.objects.create(nome=f"Pais Fin {sufixo}", codigo_iso=f"N{sufixo[:2]}", criado_por=django_user)
    visto = TipoVisto.objects.create(pais_destino=pais, nome=f"Turismo Fin {sufixo}", criado_por=django_user)
    return Viagem.objects.create(
        assessor_responsavel=consultor,
        pais_destino=pais,
        tipo_visto=visto,
        data_prevista_viagem=datetime.date(2026, 11, 1),
        data_prevista_retorno=datetime.date(2026, 11, 15),
        criado_por=django_user,
    )


def _financeiro(consultor, django_user, viagem, cliente, valor=1000.00, status=StatusFinanceiro.PENDENTE):
    return Financeiro.objects.create(
        viagem=viagem,
        cliente=cliente,
        assessor_responsavel=consultor,
        valor=valor,
        status=status,
        criado_por=django_user,
    )


class FinanceiroCriacaoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_financeiro.py] Criação de registro financeiro")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="fin.cri@test.com")
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="CR")
        cls.viagem.clientes.add(cls.cliente)
        cls.fin = _financeiro(cls.consultor, cls.django_user, cls.viagem, cls.cliente)

    def test_criado_com_sucesso(self):
        self.assertIsNotNone(self.fin.pk)

    def test_status_pendente_por_padrao(self):
        self.assertEqual(self.fin.status, StatusFinanceiro.PENDENTE)

    def test_str_contem_cliente_valor_status(self):
        s = str(self.fin)
        self.assertIn("Cliente Fin", s)
        self.assertIn("1000", s)
        self.assertIn("Pendente", s)

    def test_valor_gravado_corretamente(self):
        from decimal import Decimal
        self.assertEqual(self.fin.valor, Decimal("1000.00"))


class FinanceiroStatusTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_financeiro.py] Alteração de status financeiro")
        cls.consultor, cls.django_user = _setup_base()
        cls.cliente = _cliente_base(cls.consultor, cls.django_user, email="fin.st@test.com")
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="ST")
        cls.viagem.clientes.add(cls.cliente)

    def test_marcar_como_pago(self):
        fin = _financeiro(self.consultor, self.django_user, self.viagem, self.cliente, status=StatusFinanceiro.PENDENTE)
        fin.status = StatusFinanceiro.PAGO
        fin.data_pagamento = datetime.date.today()
        fin.save()
        atualizado = Financeiro.objects.get(pk=fin.pk)
        self.assertEqual(atualizado.status, StatusFinanceiro.PAGO)
        self.assertEqual(atualizado.data_pagamento, datetime.date.today())

    def test_marcar_como_cancelado(self):
        fin = _financeiro(self.consultor, self.django_user, self.viagem, self.cliente)
        fin.status = StatusFinanceiro.CANCELADO
        fin.save()
        atualizado = Financeiro.objects.get(pk=fin.pk)
        self.assertEqual(atualizado.status, StatusFinanceiro.CANCELADO)


class FinanceiroPropagacaoPagamentoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_financeiro.py] Propagação de pagamento para dependentes")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="fin.prop.p@test.com")
        cls.dep1 = _cliente_base(cls.consultor, cls.django_user, email="fin.prop.d1@test.com", principal=cls.principal)
        cls.dep2 = _cliente_base(cls.consultor, cls.django_user, email="fin.prop.d2@test.com", principal=cls.principal)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="PP")
        cls.viagem.clientes.add(cls.principal, cls.dep1, cls.dep2)

    def test_pagamento_principal_propaga_para_dependentes(self):
        fin_p = _financeiro(self.consultor, self.django_user, self.viagem, self.principal)
        fin_d1 = _financeiro(self.consultor, self.django_user, self.viagem, self.dep1)
        fin_d2 = _financeiro(self.consultor, self.django_user, self.viagem, self.dep2)

        fin_p.status = StatusFinanceiro.PAGO
        fin_p.save()

        fin_d1.refresh_from_db()
        fin_d2.refresh_from_db()

        self.assertEqual(fin_d1.status, StatusFinanceiro.PAGO)
        self.assertEqual(fin_d2.status, StatusFinanceiro.PAGO)

    def test_pagamento_dependente_nao_propaga(self):
        fin_p = _financeiro(self.consultor, self.django_user, self.viagem, self.principal)
        fin_d1 = _financeiro(self.consultor, self.django_user, self.viagem, self.dep1)

        fin_d1.status = StatusFinanceiro.PAGO
        fin_d1.save()

        fin_p.refresh_from_db()
        self.assertEqual(fin_p.status, StatusFinanceiro.PENDENTE)


class FinanceiroPropagacaoSemRegistroDependenteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_financeiro.py] Propagação sem registro do dependente — não cria novo")
        cls.consultor, cls.django_user = _setup_base()
        cls.principal = _cliente_base(cls.consultor, cls.django_user, email="fin.sem.d.p@test.com")
        cls.dep = _cliente_base(cls.consultor, cls.django_user, email="fin.sem.d.d@test.com", principal=cls.principal)
        cls.viagem = _viagem_base(cls.consultor, cls.django_user, sufixo="SD")
        cls.viagem.clientes.add(cls.principal, cls.dep)

    def test_sem_registro_dependente_nao_cria(self):
        fin_p = _financeiro(self.consultor, self.django_user, self.viagem, self.principal)
        fin_p.status = StatusFinanceiro.PAGO
        fin_p.save()
        self.assertFalse(Financeiro.objects.filter(cliente=self.dep, viagem=self.viagem).exists())


class FinanceiroCascadeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        print("\n[test_01_consultancy_financeiro.py] Cascade delete de financeiro")
        cls.consultor, cls.django_user = _setup_base()

    def test_delete_viagem_remove_financeiro(self):
        viagem = _viagem_base(self.consultor, self.django_user, sufixo="DV")
        cliente = _cliente_base(self.consultor, self.django_user, email="del.fin.v@test.com")
        viagem.clientes.add(cliente)
        fin = _financeiro(self.consultor, self.django_user, viagem, cliente)
        fin_pk = fin.pk
        viagem.delete()
        self.assertFalse(Financeiro.objects.filter(pk=fin_pk).exists())
