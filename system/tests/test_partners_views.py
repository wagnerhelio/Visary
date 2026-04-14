from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from system.models import Partner

User = get_user_model()


class PartnersViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin.partners@test.com",
            email="admin.partners@test.com",
            password="SenhaForte123!",
        )
        cls.partner = Partner.objects.create(
            contact_name="Parceiro Teste",
            company_name="Empresa Parceira",
            email="parceiro.view@test.com",
            password="!",
            segment="travel_agency",
            created_by=cls.user,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_home_partners_uses_model_segment_choices(self):
        response = self.client.get(reverse("system:home_partners"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["segmentos"]),
            list(Partner._meta.get_field("segment").choices),
        )
        self.assertContains(response, "Agência de Viagem")

    def test_list_partners_uses_model_segment_choices(self):
        response = self.client.get(reverse("system:list_partners"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["segmentos"]),
            list(Partner._meta.get_field("segment").choices),
        )
        self.assertContains(response, "Agência de Viagem")
