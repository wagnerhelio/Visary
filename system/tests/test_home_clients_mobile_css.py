from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import ConsultancyClient, ConsultancyUser, Profile

User = get_user_model()


class HomeClientsMobileCssTests(TestCase):
    def setUp(self):
        self.profile = Profile.objects.create(
            name="Atendente Mobile",
            can_create=True,
            can_view=True,
            can_update=True,
            can_delete=False,
            is_active=True,
        )
        self.consultant = ConsultancyUser.objects.create(
            name="Raquel Mobile",
            email="raquel.mobile@visary.test",
            profile=self.profile,
            password="!",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=self.consultant.email,
            email=self.consultant.email,
            password="senha-segura-123",
        )
        ConsultancyClient.objects.create(
            assigned_advisor=self.consultant,
            first_name="Raiany",
            last_name="Medeiros Souza",
            cpf="444.444.444-44",
            birth_date=date(1990, 1, 1),
            nationality="Brasileira",
            phone="(11) 99999-9999",
            email="raiany.mobile@example.test",
            password="!",
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_home_clients_loads_mobile_stylesheet(self):
        response = self.client.get(reverse("system:home_clients"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "system/css/home_clients_mobile.css")
