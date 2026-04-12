from django.db import models

from .travel_models import VisaType


FIELD_TYPE_CHOICES = [
    ("text", "Texto"),
    ("date", "Data"),
    ("number", "Número"),
    ("boolean", "Sim/Não"),
    ("select", "Seleção"),
]


class VisaForm(models.Model):
    visa_type = models.OneToOneField(
        VisaType,
        on_delete=models.CASCADE,
        related_name="form",
        verbose_name="Tipo de Visto",
    )
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Formulário de Visto"
        verbose_name_plural = "Formulários de Visto"
        ordering = ("visa_type__name",)

    def __str__(self):
        return f"Formulário - {self.visa_type.name}"


class VisaFormStage(models.Model):
    form = models.ForeignKey(
        VisaForm,
        on_delete=models.CASCADE,
        related_name="stages",
        verbose_name="Formulário",
    )
    name = models.CharField("Nome da etapa", max_length=120)
    order = models.PositiveIntegerField("Ordem", default=0)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Etapa do Formulário"
        verbose_name_plural = "Etapas do Formulário"
        ordering = ("form", "order", "name")
        unique_together = [("form", "order")]

    def __str__(self):
        return f"{self.form} - {self.name}"


class FormQuestion(models.Model):
    form = models.ForeignKey(
        VisaForm,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Formulário",
    )
    stage = models.ForeignKey(
        VisaFormStage,
        on_delete=models.SET_NULL,
        related_name="questions",
        verbose_name="Etapa",
        null=True,
        blank=True,
    )
    question = models.CharField("Pergunta", max_length=500)
    display_rule = models.JSONField("Regra de Exibição", null=True, blank=True)
    field_type = models.CharField(
        "Tipo de Campo",
        max_length=20,
        choices=FIELD_TYPE_CHOICES,
        default="text",
    )
    is_required = models.BooleanField("Obrigatório", default=False)
    order = models.PositiveIntegerField("Ordem", default=0)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Pergunta do Formulário"
        verbose_name_plural = "Perguntas do Formulário"
        ordering = ("form", "order", "question")
        unique_together = [("form", "order")]

    def __str__(self):
        return f"{self.question} ({self.get_field_type_display()})"


class SelectOption(models.Model):
    question = models.ForeignKey(
        FormQuestion,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Pergunta",
    )
    text = models.CharField("Texto da Opção", max_length=200)
    order = models.PositiveIntegerField("Ordem", default=0)
    is_active = models.BooleanField("Ativo", default=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Opção de Seleção"
        verbose_name_plural = "Opções de Seleção"
        ordering = ("question", "order", "text")
        unique_together = [("question", "order")]

    def __str__(self):
        return f"{self.text} ({self.question.question})"


class FormAnswer(models.Model):
    trip = models.ForeignKey(
        "system.Trip",
        on_delete=models.CASCADE,
        related_name="form_answers",
        verbose_name="Viagem",
    )
    client = models.ForeignKey(
        "system.ConsultancyClient",
        on_delete=models.CASCADE,
        related_name="form_answers",
        verbose_name="Cliente",
    )
    question = models.ForeignKey(
        FormQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="Pergunta",
    )
    answer_text = models.TextField("Resposta (Texto)", blank=True)
    answer_date = models.DateField("Resposta (Data)", null=True, blank=True)
    answer_number = models.DecimalField(
        "Resposta (Número)",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    answer_boolean = models.BooleanField("Resposta (Sim/Não)", null=True, blank=True)
    answer_select = models.ForeignKey(
        SelectOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answers",
        verbose_name="Resposta (Seleção)",
    )
    created_at = models.DateTimeField("Criado em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Resposta do Formulário"
        verbose_name_plural = "Respostas do Formulário"
        ordering = ("trip", "client", "question__order")
        unique_together = [("trip", "client", "question")]

    def __str__(self):
        return f"{self.client.full_name} - {self.question.question}"

    def get_answer_display(self):
        field_type = self.question.field_type
        if field_type == "text":
            return self.answer_text
        if field_type == "date":
            return self.answer_date.strftime("%d/%m/%Y") if self.answer_date else ""
        if field_type == "number":
            return str(self.answer_number) if self.answer_number is not None else ""
        if field_type == "boolean":
            if self.answer_boolean is True:
                return "Sim"
            if self.answer_boolean is False:
                return "Não"
            return ""
        if field_type == "select":
            if self.answer_select:
                return self.answer_select.text
            return self.answer_text or ""
        return ""
