from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from system.models import (
    ConsultancyClient,
    ConsultancyUser,
    DestinationCountry,
    FormAnswer,
    FormQuestion,
    Profile,
    Trip,
    TripClient,
    VisaForm,
    VisaFormStage,
    VisaType,
)
from system.services.form_prefill import prefill_form_answers
from system.services.form_prefill_rules import should_prefill_from_client

User = get_user_model()


class FormPrefillTests(TestCase):
    def setUp(self):
        self.profile = Profile.objects.create(
            name="Administrador Teste",
            can_create=True,
            can_view=True,
            can_update=True,
            can_delete=True,
            is_active=True,
        )
        self.consultant = ConsultancyUser.objects.create(
            name="Consultor Prefill",
            email="prefill.consultor@test.com",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=self.consultant.email,
            email=self.consultant.email,
            password="SenhaForte123!",
        )
        self.country = DestinationCountry.objects.create(
            name="Estados Unidos",
            iso_code="USA",
            is_active=True,
            created_by=self.user,
        )
        self.visa_type = VisaType.objects.create(
            destination_country=self.country,
            name="B1 / B2 (Turismo, Negócios ou Estudos Recreativos)",
            description="",
            is_active=True,
            created_by=self.user,
        )
        self.form = VisaForm.objects.create(visa_type=self.visa_type, is_active=True)
        self.stage_one = VisaFormStage.objects.create(form=self.form, name="Dados Pessoais", order=1)
        self.stage_two = VisaFormStage.objects.create(form=self.form, name="Dados da Viagem", order=2)

        self.client_obj = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Maria",
            last_name="Silva",
            cpf="123.456.789-00",
            birth_date=date(1991, 5, 12),
            nationality="Brasileira",
            phone="(11) 99999-8888",
            secondary_phone="(11) 98888-7777",
            email="maria.silva@test.com",
            password="!",
            zip_code="01001-000",
            street="Rua Teste",
            street_number="100",
            district="Centro",
            city="São Paulo",
            state="SP",
            created_by=self.user,
        )

        self.trip = Trip.objects.create(
            assigned_advisor=self.consultant,
            destination_country=self.country,
            visa_type=self.visa_type,
            planned_departure_date=date(2026, 7, 10),
            planned_return_date=date(2026, 7, 20),
            advisory_fee=1000,
            created_by=self.user,
        )
        TripClient.objects.create(
            trip=self.trip,
            client=self.client_obj,
            visa_type=self.visa_type,
            role="primary",
        )

    def test_prefill_only_stage_one_and_blocks_foreign_address(self):
        q_cpf = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=1,
            question="CPF",
            field_type="text",
            is_required=True,
            is_active=True,
        )
        q_us_address = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=2,
            question="Endereço completo onde ficará nos Estados Unidos",
            field_type="text",
            is_required=False,
            is_active=True,
        )
        q_email_stage_two = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_two,
            order=3,
            question="E-mail",
            field_type="text",
            is_required=False,
            is_active=True,
        )

        questions = (
            self.form.questions.filter(is_active=True)
            .select_related("stage")
            .order_by("order")
        )
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        self.assertTrue(FormAnswer.objects.filter(question=q_cpf, answer_text="123.456.789-00").exists())
        self.assertFalse(FormAnswer.objects.filter(question=q_us_address).exists())
        self.assertFalse(FormAnswer.objects.filter(question=q_email_stage_two).exists())

    def test_prefill_does_not_fill_birthplace_question(self):
        q_birthplace = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=4,
            question="Cidade e estado de Nascimento",
            field_type="text",
            is_required=False,
            is_active=True,
        )

        questions = self.form.questions.filter(is_active=True).select_related("stage")
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        self.assertFalse(FormAnswer.objects.filter(question=q_birthplace).exists())

    def test_prefill_rules_keep_passport_country_and_exclude_employer_phone(self):
        self.assertTrue(should_prefill_from_client("País que emitiu o passaporte"))
        self.assertTrue(should_prefill_from_client("Telefone Primário"))
        self.assertFalse(should_prefill_from_client("Telefone do empregador ou escola"))
        self.assertFalse(
            should_prefill_from_client(
                "Informe nome completo, data de nascimento e parentesco dos seus acompanhantes na viagem"
            )
        )
