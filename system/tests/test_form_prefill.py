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
            complement="Apto 12",
            district="Centro",
            city="São Paulo",
            state="SP",
            passport_type="regular",
            passport_number="AB123456",
            passport_issuing_country="Brasil",
            passport_issue_date=date(2021, 1, 10),
            passport_expiry_date=date(2031, 1, 9),
            passport_authority="DPF",
            passport_issuing_city="São Paulo",
            passport_stolen=False,
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

    def test_prefill_rules_limit_to_direct_applicant_personal_fields(self):
        self.assertTrue(should_prefill_from_client("País que emitiu o passaporte"))
        self.assertTrue(should_prefill_from_client("Número do Passaporte"))
        self.assertTrue(should_prefill_from_client("Endereço completo"))
        self.assertFalse(should_prefill_from_client("Endereço completo do empregador ou escola"))
        self.assertFalse(should_prefill_from_client("CEP da instituição"))
        self.assertTrue(should_prefill_from_client("Telefone Primário"))
        self.assertFalse(should_prefill_from_client("Telefone do empregador ou escola"))
        self.assertFalse(should_prefill_from_client("1- Data de nascimento (Dia/Mês/Ano)"))
        self.assertFalse(
            should_prefill_from_client(
                "Informe nome completo, data de nascimento e parentesco dos seus acompanhantes na viagem"
            )
        )

    def test_prefill_does_not_duplicate_applicant_data_in_repeated_contact_blocks(self):
        q_name = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=1,
            question="Nome",
            field_type="text",
            is_required=True,
            is_active=True,
        )
        q_contact_name = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=50,
            question="Primeiro nome",
            field_type="text",
            is_required=False,
            is_active=True,
        )
        q_phone = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=51,
            question="Telefone",
            field_type="text",
            is_required=False,
            is_active=True,
        )
        q_contact_phone = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=52,
            question="Telefone",
            field_type="text",
            is_required=False,
            is_active=True,
        )

        questions = self.form.questions.filter(is_active=True).select_related("stage").order_by("order")
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        self.assertTrue(FormAnswer.objects.filter(question=q_name, answer_text="Maria").exists())
        self.assertFalse(FormAnswer.objects.filter(question=q_contact_name).exists())
        self.assertTrue(FormAnswer.objects.filter(question=q_phone, answer_text="(11) 99999-8888").exists())
        self.assertFalse(FormAnswer.objects.filter(question=q_contact_phone).exists())

    def test_prefill_fills_direct_address_and_passport_fields(self):
        questions_data = [
            ("Endereço completo", "text", "Rua Teste, 100, Apto 12, Centro, São Paulo - SP, 01001-000"),
            ("Bairro", "text", "Centro"),
            ("Cidade e estado em que reside", "text", "São Paulo - SP"),
            ("CEP", "text", "01001-000"),
            ("Número do Passaporte Válido", "text", "AB123456"),
            ("País que emitiu o passaporte", "text", "Brasil"),
            ("Data de Emissão", "date", date(2021, 1, 10)),
            ("Válido até", "date", date(2031, 1, 9)),
            ("Órgão Emissor", "text", "DPF"),
            ("Cidade onde foi emitido", "text", "São Paulo"),
        ]
        created = []
        for order, (question, field_type, _expected) in enumerate(questions_data, start=1):
            created.append(
                FormQuestion.objects.create(
                    form=self.form,
                    stage=self.stage_one,
                    order=order,
                    question=question,
                    field_type=field_type,
                    is_required=False,
                    is_active=True,
                )
            )

        questions = self.form.questions.filter(is_active=True).select_related("stage").order_by("order")
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        for question, (_label, field_type, expected) in zip(created, questions_data):
            answer = FormAnswer.objects.get(question=question)
            if field_type == "date":
                self.assertEqual(answer.answer_date, expected)
            else:
                self.assertEqual(answer.answer_text, expected)

    def test_prefill_still_blocks_third_party_address_and_phone(self):
        blocked_questions = [
            "Endereço completo do empregador ou escola",
            "CEP da Instituição",
            "Telefone do contato emergencial",
            "Endereço completo do contato emergencial.",
            "1- Endereço atual",
            "2 - Telefone",
        ]
        created = [
            FormQuestion.objects.create(
                form=self.form,
                stage=self.stage_one,
                order=idx,
                question=question,
                field_type="text",
                is_required=False,
                is_active=True,
            )
            for idx, question in enumerate(blocked_questions, start=1)
        ]

        questions = self.form.questions.filter(is_active=True).select_related("stage").order_by("order")
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        for question in created:
            self.assertFalse(FormAnswer.objects.filter(question=question).exists())

    def test_prefill_does_not_fill_generic_contact_address_after_residential_address(self):
        q_street = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=1,
            question="Endereço(rua/quadra/avenida)",
            field_type="text",
            is_required=True,
            is_active=True,
        )
        q_contact_address = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            order=50,
            question="Endereco completo",
            field_type="text",
            is_required=False,
            is_active=True,
        )

        questions = self.form.questions.filter(is_active=True).select_related("stage").order_by("order")
        existing_answers = {}
        prefill_form_answers(self.trip, self.client_obj, questions, existing_answers)

        self.assertTrue(FormAnswer.objects.filter(question=q_street).exists())
        self.assertFalse(FormAnswer.objects.filter(question=q_contact_address).exists())
