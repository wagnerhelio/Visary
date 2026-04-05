from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models


SEGMENT_CHOICES = [
    ("travel_agency", "Agência de Viagem"),
    ("immigration_consulting", "Consultoria de Imigração"),
    ("law", "Advocacia"),
    ("education", "Educação"),
    ("other", "Outros"),
]


class Partner(models.Model):
    contact_name = models.CharField("Nome do Responsável", max_length=200)
    company_name = models.CharField("Nome da Empresa", max_length=200, blank=True, null=True)
    cpf = models.CharField("CPF", max_length=14, blank=True, null=True)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True, null=True)
    email = models.EmailField("E-mail", unique=True)
    password = models.CharField("Senha", max_length=128)
    phone = models.CharField("Telefone", max_length=20, blank=True, null=True)
    segment = models.CharField(
        "Segmento",
        max_length=50,
        choices=SEGMENT_CHOICES,
        default="other",
    )
    city = models.CharField("Cidade", max_length=100, blank=True, null=True)
    state = models.CharField("Estado", max_length=2, blank=True, null=True)
    is_active = models.BooleanField("Ativo", default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_partners",
        verbose_name="Criado por",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Parceiro"
        verbose_name_plural = "Parceiros"
        ordering = ("company_name", "contact_name")

    def __str__(self):
        if self.company_name:
            return f"{self.company_name} - {self.contact_name}"
        return self.contact_name

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        if not self.password:
            return False
        try:
            if check_password(raw_password, self.password):
                return True
        except ValueError:
            pass
        if self.password == raw_password:
            self.set_password(raw_password)
            self.save(update_fields=["password", "updated_at"])
            return True
        return False
