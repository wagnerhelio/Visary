from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class CepApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="admin.cep@test.com",
            email="admin.cep@test.com",
            password="SenhaForte123!",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_api_search_zip_accepts_zip_code_parameter(self):
        with patch("system.views.client_views.fetch_address_by_zip") as fetch_mock:
            fetch_mock.return_value = {
                "cep": "01001000",
                "street": "Praça da Sé",
                "district": "Sé",
                "city": "São Paulo",
                "uf": "SP",
                "complement": "",
            }

            response = self.client.get(reverse("system:api_search_zip"), {"zip_code": "01001-000"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["city"], "São Paulo")
        fetch_mock.assert_called_once_with("01001-000")

    def test_api_search_zip_accepts_legacy_cep_parameter(self):
        with patch("system.views.client_views.fetch_address_by_zip") as fetch_mock:
            fetch_mock.return_value = {
                "cep": "01001000",
                "street": "Praça da Sé",
                "district": "Sé",
                "city": "São Paulo",
                "uf": "SP",
                "complement": "",
            }

            response = self.client.get(reverse("system:api_search_zip"), {"cep": "01001-000"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["street"], "Praça da Sé")
        fetch_mock.assert_called_once_with("01001-000")
