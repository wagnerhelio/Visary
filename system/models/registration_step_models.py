from django.db import models


FIELD_TYPE_CHOICES = [
    ("text", "Texto"),
    ("date", "Data"),
    ("number", "Número"),
    ("boolean", "Sim/Não"),
    ("select", "Seleção"),
]


class ClientRegistrationStep(models.Model):
    name = models.CharField("Nome da Etapa", max_length=100)
    description = models.TextField("Descrição", blank=True)
    order = models.PositiveIntegerField("Ordem", default=0)
    is_active = models.BooleanField("Ativo", default=True)
    boolean_field = models.CharField(
        "Campo Booleano",
        max_length=50,
        blank=True,
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "Etapa de Cadastro"
        verbose_name_plural = "Etapas de Cadastro"

    def __str__(self):
        return f"{self.order}. {self.name}"


class ClientStepField(models.Model):
    step = models.ForeignKey(
        ClientRegistrationStep,
        on_delete=models.CASCADE,
        related_name="fields",
        verbose_name="Etapa",
    )
    field_name = models.CharField("Nome do Campo", max_length=100)
    field_type = models.CharField(
        "Tipo de Campo",
        max_length=20,
        choices=FIELD_TYPE_CHOICES,
        default="text",
    )
    order = models.PositiveIntegerField("Ordem", default=0)
    is_required = models.BooleanField("Obrigatório", default=True)
    is_active = models.BooleanField("Ativo", default=True)
    display_rule = models.JSONField("Regra de Exibição", null=True, blank=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("step", "order", "field_name")
        verbose_name = "Campo da Etapa"
        verbose_name_plural = "Campos das Etapas"
        unique_together = [("step", "field_name")]

    def __str__(self):
        return f"{self.step.name} - {self.field_name}"
