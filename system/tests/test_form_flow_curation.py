import json
from contextlib import redirect_stderr, redirect_stdout
from html import unescape
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

from system.management.commands.seed_visa_forms import Command as SeedVisaFormsCommand
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
from system.services.form_responses import process_form_answers

User = get_user_model()


class DisplayRuleSerializationTests(SimpleTestCase):
    def test_json_attr_serializes_display_rule_as_valid_json(self):
        rendered = Template(
            "{% load dict_filters %}"
            "<div data-rule='{{ rule|json_attr }}'></div>"
        ).render(
            Context(
                {
                    "rule": {
                        "type": "show_if",
                        "question_order": 10,
                        "value": ["sim", "nao"],
                    }
                }
            )
        )

        raw_rule = rendered.split("data-rule='", 1)[1].split("'", 1)[0]

        self.assertEqual(
            json.loads(unescape(raw_rule)),
            {"type": "show_if", "question_order": 10, "value": ["sim", "nao"]},
        )


class FormAnswerVisibilityTests(TestCase):
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
            name="Consultor Formulário",
            email="consultor.formulario@test.com",
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
        self.stage_one = VisaFormStage.objects.create(
            form=self.form,
            name="Dados Pessoais",
            order=1,
        )
        self.stage_two = VisaFormStage.objects.create(
            form=self.form,
            name="Empregos Anteriores",
            order=2,
        )
        self.client_obj = ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Maria",
            last_name="Silva",
            cpf="123.456.789-00",
            birth_date="1991-05-12",
            nationality="Brasileira",
            phone="(11) 99999-8888",
            email="maria.silva@test.com",
            password="!",
            created_by=self.user,
        )
        self.trip = Trip.objects.create(
            assigned_advisor=self.consultant,
            destination_country=self.country,
            visa_type=self.visa_type,
            planned_departure_date="2026-07-10",
            planned_return_date="2026-07-20",
            advisory_fee=1000,
            created_by=self.user,
        )
        TripClient.objects.create(
            trip=self.trip,
            client=self.client_obj,
            visa_type=self.visa_type,
            role="primary",
        )
        self.trigger_question = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_one,
            question="Já teve empregos anteriores?",
            field_type="boolean",
            is_required=True,
            order=10,
            is_active=True,
        )
        self.conditional_question = FormQuestion.objects.create(
            form=self.form,
            stage=self.stage_two,
            question="Endereço completo do empregador anterior",
            field_type="text",
            is_required=True,
            order=11,
            is_active=True,
            display_rule={"type": "show_if", "question_order": 10, "value": "sim"},
        )

    def test_cross_stage_rule_uses_existing_answer_to_require_visible_question(self):
        FormAnswer.objects.create(
            trip=self.trip,
            client=self.client_obj,
            question=self.trigger_question,
            answer_boolean=True,
        )

        saved_count, errors = process_form_answers(
            {},
            self.trip,
            self.client_obj,
            [self.conditional_question],
            existing_answers={
                answer.question_id: answer
                for answer in FormAnswer.objects.filter(trip=self.trip, client=self.client_obj)
            },
            state_questions=[self.trigger_question, self.conditional_question],
        )

        self.assertEqual(saved_count, 0)
        self.assertEqual(
            errors,
            ["A pergunta 'Endereço completo do empregador anterior' é obrigatória."],
        )

    def test_hidden_conditional_question_removes_stale_answer(self):
        trigger_answer = FormAnswer.objects.create(
            trip=self.trip,
            client=self.client_obj,
            question=self.trigger_question,
            answer_boolean=False,
        )
        stale_answer = FormAnswer.objects.create(
            trip=self.trip,
            client=self.client_obj,
            question=self.conditional_question,
            answer_text="Resposta antiga",
        )

        saved_count, errors = process_form_answers(
            {},
            self.trip,
            self.client_obj,
            [self.conditional_question],
            existing_answers={
                trigger_answer.question_id: trigger_answer,
                stale_answer.question_id: stale_answer,
            },
            state_questions=[self.trigger_question, self.conditional_question],
        )

        self.assertEqual(saved_count, 0)
        self.assertEqual(errors, [])
        self.assertFalse(
            FormAnswer.objects.filter(
                trip=self.trip,
                client=self.client_obj,
                question=self.conditional_question,
            ).exists()
        )


class VisaFormSeedCurationTests(TestCase):
    def test_eua_b1_b2_seed_uses_legacy_stage_sequence_from_json(self):
        silence = StringIO()
        with redirect_stdout(silence), redirect_stderr(silence):
            call_command(
                "seed_visa_forms",
                file="FORMULARIO_EUA_B1_B2.json",
                stdout=silence,
            )

        form = VisaForm.objects.get(
            visa_type__name="B1 / B2 (Turismo, Negocios ou Estudos Recreativos)"
        )
        stages = list(
            form.stages.filter(is_active=True)
            .order_by("order")
            .values_list("order", "name")
        )

        self.assertEqual(len(stages), 24)
        self.assertEqual(
            stages[:5],
            [
                (1, "Dados Pessoais"),
                (2, "Dados do Cônjuge"),
                (3, "Passaporte"),
                (4, "Dados da Viagem"),
                (5, "Dados da Escola"),
            ],
        )
        self.assertFalse(
            FormQuestion.objects.filter(
                form=form,
                question__in=[
                    "Endereço completo do empregador anterior",
                    "CEP do empregador anterior",
                    "Telefone do empregador anterior",
                    "Endereço completo da Instituição",
                    "CEP da Instituição",
                ],
                stage__order=1,
            ).exists()
        )

        stage_one_questions = list(
            FormQuestion.objects.filter(form=form, stage__order=1, is_active=True)
            .order_by("order")
            .values_list("question", flat=True)
        )
        self.assertEqual(
            stage_one_questions[:7],
            [
                "Nome",
                "Sobrenome",
                "Nomes Anteriores",
                "E-mail",
                "Você usou outros e-mails nos últimos cinco anos",
                "Sexo",
                "Você possui conta em alguma rede social? Se sim, informar a plataforma e nome de usuário",
            ],
        )

    def test_seed_preserves_question_identity_when_order_changes(self):
        profile = Profile.objects.create(name="Perfil", is_active=True)
        consultant = ConsultancyUser.objects.create(
            name="Consultor",
            email="consultor.seed@test.com",
            profile=profile,
            password="!",
            is_active=True,
        )
        user = User.objects.create_user(
            username="seed@test.com",
            email="seed@test.com",
            password="SenhaForte123!",
        )
        country = DestinationCountry.objects.create(
            name="País Teste",
            iso_code="TST",
            is_active=True,
            created_by=user,
        )
        visa_type = VisaType.objects.create(
            destination_country=country,
            name="Visto Teste",
            description="",
            is_active=True,
            created_by=user,
        )
        form = VisaForm.objects.create(visa_type=visa_type, is_active=True)
        stage = VisaFormStage.objects.create(form=form, name="Dados", order=1)
        q_address = FormQuestion.objects.create(
            form=form,
            stage=stage,
            question="Endereço(rua/quadra/avenida)",
            field_type="text",
            order=1,
        )
        q_phone = FormQuestion.objects.create(
            form=form,
            stage=stage,
            question="Telefone Primário",
            field_type="text",
            order=2,
        )
        client = ConsultancyClient.objects.create(
            assigned_advisor=consultant,
            first_name="Cliente",
            last_name="Teste",
            cpf="300.300.300-30",
            birth_date="1990-01-01",
            nationality="Brasileira",
            phone="(62) 99999-0000",
            email="cliente.seed@test.com",
            password="!",
            created_by=user,
        )
        trip = Trip.objects.create(
            assigned_advisor=consultant,
            destination_country=country,
            visa_type=visa_type,
            planned_departure_date="2026-07-10",
            planned_return_date="2026-07-20",
            advisory_fee=1000,
            created_by=user,
        )
        FormAnswer.objects.create(
            trip=trip,
            client=client,
            question=q_phone,
            answer_text="(62) 99999-0000",
        )

        command = SeedVisaFormsCommand()
        command._sync_questions(
            form,
            {
                "tipo_visto": "Visto Teste",
                "perguntas": [
                    {
                        "ordem": 1,
                        "pergunta": "Telefone Primário",
                        "tipo_campo": "texto",
                        "etapa": 1,
                        "ativo": True,
                    },
                    {
                        "ordem": 2,
                        "pergunta": "Endereço(rua/quadra/avenida)",
                        "tipo_campo": "texto",
                        "etapa": 1,
                        "ativo": True,
                    },
                ],
            },
            {1: stage},
            type("JsonFile", (), {"name": "teste.json"})(),
        )

        q_phone.refresh_from_db()
        q_address.refresh_from_db()
        self.assertEqual(q_phone.order, 1)
        self.assertEqual(q_address.order, 2)
        self.assertEqual(
            FormAnswer.objects.get(trip=trip, client=client).question_id,
            q_phone.pk,
        )
