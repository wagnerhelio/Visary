"""
Modelos relacionados a formulários dinâmicos de visto.
"""

from django.db import models

from consultancy.models.travel_models import TipoVisto


class FormularioVisto(models.Model):
    """Formulário dinâmico vinculado a um tipo de visto."""

    tipo_visto = models.OneToOneField(
        TipoVisto,
        on_delete=models.CASCADE,
        related_name="formulario",
        verbose_name="Tipo de Visto",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Formulário de Visto"
        verbose_name_plural = "Formulários de Visto"
        ordering = ("tipo_visto__nome",)

    def __str__(self):
        return f"Formulário - {self.tipo_visto.nome}"


class PerguntaFormulario(models.Model):
    """Pergunta/campo de um formulário de visto."""

    TIPO_CAMPO_CHOICES = [
        ("texto", "Texto"),
        ("data", "Data"),
        ("numero", "Número"),
        ("booleano", "Sim/Não"),
        ("selecao", "Seleção"),
    ]

    formulario = models.ForeignKey(
        FormularioVisto,
        on_delete=models.CASCADE,
        related_name="perguntas",
        verbose_name="Formulário",
    )
    pergunta = models.CharField("Pergunta", max_length=500)
    tipo_campo = models.CharField(
        "Tipo de Campo",
        max_length=20,
        choices=TIPO_CAMPO_CHOICES,
        default="texto",
    )
    obrigatorio = models.BooleanField("Obrigatório", default=False)
    ordem = models.PositiveIntegerField("Ordem", default=0)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Pergunta do Formulário"
        verbose_name_plural = "Perguntas do Formulário"
        ordering = ("formulario", "ordem", "pergunta")
        unique_together = [("formulario", "ordem")]

    def __str__(self):
        return f"{self.pergunta} ({self.get_tipo_campo_display()})"


class OpcaoSelecao(models.Model):
    """Opção de seleção para perguntas do tipo 'Seleção'."""

    pergunta = models.ForeignKey(
        PerguntaFormulario,
        on_delete=models.CASCADE,
        related_name="opcoes",
        verbose_name="Pergunta",
    )
    texto = models.CharField("Texto da Opção", max_length=200)
    ordem = models.PositiveIntegerField("Ordem", default=0)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Opção de Seleção"
        verbose_name_plural = "Opções de Seleção"
        ordering = ("pergunta", "ordem", "texto")
        unique_together = [("pergunta", "ordem")]

    def __str__(self):
        return f"{self.texto} ({self.pergunta.pergunta})"


class RespostaFormulario(models.Model):
    """Resposta de um cliente a um formulário de visto."""

    viagem = models.ForeignKey(
        "consultancy.Viagem",
        on_delete=models.CASCADE,
        related_name="respostas_formulario",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "consultancy.ClienteConsultoria",
        on_delete=models.CASCADE,
        related_name="respostas_formulario",
        verbose_name="Cliente",
    )
    pergunta = models.ForeignKey(
        PerguntaFormulario,
        on_delete=models.CASCADE,
        related_name="respostas",
        verbose_name="Pergunta",
    )
    resposta_texto = models.TextField("Resposta (Texto)", blank=True)
    resposta_data = models.DateField("Resposta (Data)", null=True, blank=True)
    resposta_numero = models.DecimalField(
        "Resposta (Número)",
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
    )
    resposta_booleano = models.BooleanField("Resposta (Sim/Não)", null=True, blank=True)
    resposta_selecao = models.ForeignKey(
        OpcaoSelecao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="respostas",
        verbose_name="Resposta (Seleção)",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Resposta do Formulário"
        verbose_name_plural = "Respostas do Formulário"
        ordering = ("viagem", "cliente", "pergunta__ordem")
        unique_together = [("viagem", "cliente", "pergunta")]

    def __str__(self):
        return f"{self.cliente.nome} - {self.pergunta.pergunta}"

    def get_resposta_display(self):
        """Retorna a resposta formatada de acordo com o tipo de campo."""
        if self.pergunta.tipo_campo == "texto":
            return self.resposta_texto
        elif self.pergunta.tipo_campo == "data":
            return self.resposta_data.strftime("%d/%m/%Y") if self.resposta_data else ""
        elif self.pergunta.tipo_campo == "numero":
            return str(self.resposta_numero) if self.resposta_numero is not None else ""
        elif self.pergunta.tipo_campo == "booleano":
            return "Sim" if self.resposta_booleano else "Não" if self.resposta_booleano is False else ""
        elif self.pergunta.tipo_campo == "selecao":
            return self.resposta_selecao.texto if self.resposta_selecao else ""
        return ""

