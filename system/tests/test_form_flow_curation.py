import json
from html import unescape
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

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
        call_command(
            "seed_visa_forms",
            file="FORMULARIO_EUA_B1_B2.json",
            stdout=StringIO(),
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
                order__in=[88, 91, 93, 102, 105],
                stage__order=1,
            ).exists()
        )
