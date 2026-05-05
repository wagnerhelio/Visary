from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import ClientRegistrationStep, ClientStepField

User = get_user_model()


class ClientRegisterDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin.draft@test.com",
            email="admin.draft@test.com",
            password="SenhaForte123!",
        )
        cls.step = ClientRegistrationStep.objects.create(
            name="Dados Pessoais",
            order=1,
            is_active=True,
            boolean_field="step_personal_data",
        )
        ClientStepField.objects.create(
            step=cls.step,
            field_name="first_name",
            field_type="text",
            order=1,
            is_required=True,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_register_client_template_exposes_local_draft_markup(self):
        response = self.client.get(reverse("system:register_client"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-client-draft-form')
        self.assertContains(response, 'visary-client-register-draft-v1-')
        self.assertContains(response, 'data-client-draft-note')
        self.assertContains(response, 'system/js/client_register_draft.js')

    def test_home_clients_emits_clear_draft_marker_when_session_flag_exists(self):
        session = self.client.session
        session["clear_client_register_draft"] = True
        session.save()

        response = self.client.get(reverse("system:home_clients"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-clear-client-register-draft')
        self.assertNotIn("clear_client_register_draft", self.client.session)

    def test_register_client_get_does_not_render_required_errors_before_submit(self):
        passport_step = ClientRegistrationStep.objects.create(
            name="Dados do Passaporte",
            order=2,
            is_active=True,
            boolean_field="step_passport",
        )
        ClientStepField.objects.create(
            step=passport_step,
            field_name="numero_passaporte",
            field_type="text",
            order=1,
            is_required=True,
            is_active=True,
        )

        session = self.client.session
        session["passport_ocr_client"] = {
            # intentionally incomplete: should not trigger required errors on GET
            "passport_number": "",
        }
        session.save()

        response = self.client.get(f"{reverse('system:register_client')}?stage_id={passport_step.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-can-restore-draft="true"')
        self.assertNotContains(response, "Este campo é obrigatório.")
