from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import ClientRegistrationStep, ClientStepField, ConsultancyUser, Profile

User = get_user_model()


class DependentRegisterFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = Profile.objects.create(
            name="Administrador Dependentes",
            can_create=True,
            can_view=True,
            can_update=True,
            can_delete=True,
            is_active=True,
        )
        cls.consultant = ConsultancyUser.objects.create(
            name="Raquel Dependentes",
            email="raquel.dependentes@visary.test",
            profile=cls.profile,
            password="!",
            is_active=True,
        )
        cls.user = User.objects.create_user(
            username=cls.consultant.email,
            email=cls.consultant.email,
            password="senha-segura-123",
        )
        cls.personal_step = cls._create_step(
            "Dados Pessoais",
            1,
            "etapa_dados_pessoais",
            [
                "assessor_responsavel",
                "nome",
                "sobrenome",
                "cpf",
                "data_nascimento",
                "nacionalidade",
                "telefone",
                "email",
                "senha",
                "confirmar_senha",
            ],
            optional_fields={"email"},
        )
        cls._create_step(
            "Endereço",
            2,
            "etapa_endereco",
            ["cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf"],
            required=False,
        )
        cls._create_step(
            "Dados do Passaporte",
            3,
            "etapa_passaporte",
            [
                "tipo_passaporte",
                "tipo_passaporte_outro",
                "numero_passaporte",
                "pais_emissor_passaporte",
                "data_emissao_passaporte",
                "valido_ate_passaporte",
                "autoridade_passaporte",
                "cidade_emissao_passaporte",
                "passaporte_roubado",
            ],
            required=True,
            optional_fields={"tipo_passaporte_outro", "passaporte_roubado"},
        )
        cls.members_step = cls._create_step(
            "Adicionar Membros",
            4,
            "etapa_membros",
            ["observacoes"],
            required=False,
        )

    @classmethod
    def _create_step(
        cls,
        name,
        order,
        boolean_field,
        field_names,
        required=True,
        optional_fields=None,
    ):
        optional_fields = optional_fields or set()
        step = ClientRegistrationStep.objects.create(
            name=name,
            order=order,
            boolean_field=boolean_field,
            is_active=True,
        )
        for index, field_name in enumerate(field_names, start=1):
            ClientStepField.objects.create(
                step=step,
                field_name=field_name,
                field_type="text",
                order=index,
                is_required=required and field_name not in optional_fields,
                is_active=True,
            )
        return step

    def setUp(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["client_temp_data"] = {
            "assigned_advisor": self.consultant.pk,
            "first_name": "Jocemari",
            "last_name": "Coutinho",
            "cpf": "529.982.247-25",
            "birth_date": date(1973, 1, 1).isoformat(),
            "nationality": "BRA",
            "phone": "(62) 99999-1532",
            "email": "jocemari@example.test",
            "password": "senha-segura-123",
            "step_personal_data": True,
            "step_address": True,
            "step_passport": True,
        }
        session.save()

    def test_dependent_stage_renders_mapped_form_fields(self):
        response = self.client.get(
            f"{reverse('system:register_client')}?stage_id={self.members_step.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="form-dependente"')
        self.assertContains(response, 'name="first_name"')
        self.assertContains(response, 'name="last_name"')
        self.assertContains(response, 'name="cpf"')
        self.assertContains(response, 'name="birth_date"')
        self.assertContains(response, 'name="nationality"')
        self.assertContains(response, 'name="phone"')
        self.assertContains(response, 'name="zip_code"')
        self.assertContains(response, 'name="passport_number"')

    def test_dependent_stage_blocks_missing_required_passport_fields(self):
        response = self.client.post(
            f"{reverse('system:register_client')}?stage_id={self.members_step.pk}",
            data={
                "form_type": "dependent",
                "assigned_advisor": self.consultant.pk,
                "first_name": "Maria",
                "last_name": "Silva",
                "cpf": "168.995.350-09",
                "birth_date": "1988-02-03",
                "nationality": "BRA",
                "phone": "(62) 99999-1111",
                "email": "maria.silva@example.test",
                "password": "senha-segura-123",
                "confirm_password": "senha-segura-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("temp_dependents", self.client.session)
        self.assertContains(response, "passport_number")
        self.assertContains(response, "Este campo é obrigatório.")

    def test_dependent_stage_summary_uses_first_and_last_name(self):
        session = self.client.session
        session["temp_dependents"] = [
            {
                "first_name": "Maria",
                "last_name": "Silva",
                "cpf": "16899535009",
            }
        ]
        session.save()

        response = self.client.get(
            f"{reverse('system:register_client')}?stage_id={self.members_step.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maria Silva")
        self.assertNotContains(response, "Sem nome")

    def test_use_primary_data_keeps_dependent_password_optional(self):
        response = self.client.post(
            f"{reverse('system:register_client')}?stage_id={self.members_step.pk}",
            data={
                "form_type": "dependent",
                "use_primary_data": "on",
                "assigned_advisor": self.consultant.pk,
                "first_name": "Ana",
                "last_name": "Costa",
                "cpf": "168.995.350-09",
                "birth_date": "1990-04-05",
                "nationality": "BRA",
                "phone": "(62) 99999-2222",
                "passport_type": "regular",
                "passport_number": "AB123456",
                "passport_issuing_country": "BRA",
                "passport_issue_date": "2020-01-01",
                "passport_expiry_date": "2030-01-01",
                "passport_authority": "DPF",
                "passport_issuing_city": "Goiânia",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.client.session["temp_dependents"]), 1)
        self.assertTrue(self.client.session["temp_dependents"][0]["use_primary_data"])
