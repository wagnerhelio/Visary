   
                                          
   

from django.conf import settings
from django.db import models

from .permission_models import UsuarioConsultoria


class StatusProcesso(models.Model):
                                          

    tipo_visto = models.ForeignKey(
        "system.TipoVisto",
        on_delete=models.SET_NULL,
        related_name="status_processos",
        verbose_name="Tipo de Visto",
        help_text="Tipo de visto ao qual este status está vinculado (opcional - deixe em branco para usar em todos os tipos)",
        null=True,
        blank=True,
    )
    nome = models.CharField("Nome do Status", max_length=100)
    prazo_padrao_dias = models.PositiveIntegerField(
        "Prazo Padrão (dias)",
        default=0,
        help_text="Prazo padrão em dias para este status",
    )
    ordem = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Ordem de exibição do status",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("ordem", "nome")
        verbose_name = "Status de Processo"
        verbose_name_plural = "Status de Processos"

    def __str__(self) -> str:
        if self.tipo_visto:
            return f"{self.tipo_visto.nome} - {self.nome}"
        return self.nome


class Processo(models.Model):
                                                             

    viagem = models.ForeignKey(
        "system.Viagem",
        on_delete=models.CASCADE,
        related_name="processos",
        verbose_name="Viagem",
    )
    cliente = models.ForeignKey(
        "system.ClienteConsultoria",
        on_delete=models.CASCADE,
        related_name="processos",
        verbose_name="Cliente",
    )
    observacoes = models.TextField("Observações", blank=True)
    assessor_responsavel = models.ForeignKey(
        UsuarioConsultoria,
        on_delete=models.PROTECT,
        related_name="processos_assessorados",
        verbose_name="Assessor responsável",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="processos_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("-criado_em",)
        verbose_name = "Processo"
        verbose_name_plural = "Processos"
        unique_together = [("viagem", "cliente")]

    def __str__(self) -> str:
        return f"{self.cliente.nome} - {self.viagem}"

    @property
    def etapas_concluidas(self):
                                                    
        return self.etapas.filter(concluida=True).count()

    @property
    def total_etapas(self):
                                                    
        return self.etapas.count()

    @property
    def progresso_percentual(self):
        
        if self.total_etapas == 0:
            return 0
        if self.etapas.filter(status__nome__iexact="Processo finalizado", concluida=True).exists():
            return 100
        if self.etapas.filter(status__nome__iexact="Processo cancelado", concluida=True).exists():
            return 100
        return int((self.etapas_concluidas / self.total_etapas) * 100)


class ViagemStatusProcesso(models.Model):
                                                                                             

    viagem = models.ForeignKey(
        "system.Viagem",
        on_delete=models.CASCADE,
        related_name="status_disponiveis",
        verbose_name="Viagem",
    )
    status = models.ForeignKey(
        StatusProcesso,
        on_delete=models.CASCADE,
        related_name="viagens_relacionadas",
        verbose_name="Status (Etapa)",
    )
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        unique_together = ("viagem", "status")
        ordering = ("status__ordem", "status__nome")
        verbose_name = "Etapa de Viagem"
        verbose_name_plural = "Etapas de Viagem"

    def __str__(self) -> str:
        return f"{self.viagem} - {self.status}"


class EtapaProcesso(models.Model):
                                            

    processo = models.ForeignKey(
        Processo,
        on_delete=models.CASCADE,
        related_name="etapas",
        verbose_name="Processo",
    )
    status = models.ForeignKey(
        StatusProcesso,
        on_delete=models.PROTECT,
        related_name="etapas_processo",
        verbose_name="Status (Etapa)",
    )
    concluida = models.BooleanField("Concluída", default=False)
    prazo_dias = models.PositiveIntegerField(
        "Prazo (dias)",
        default=0,
        help_text="Prazo em dias para conclusão desta etapa",
    )
    data_conclusao = models.DateField(
        "Data de Conclusão",
        null=True,
        blank=True,
        help_text="Data em que a etapa foi concluída",
    )
    observacoes = models.TextField("Observações", blank=True)
    ordem = models.PositiveIntegerField(
        "Ordem",
        default=0,
        help_text="Ordem de exibição da etapa",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        ordering = ("ordem", "status__nome")
        verbose_name = "Etapa do Processo"
        verbose_name_plural = "Etapas do Processo"
        unique_together = [("processo", "status")]

    def __str__(self) -> str:
        status_texto = "✓" if self.concluida else "○"
        return f"{status_texto} {self.status.nome} - {self.processo}"

    def calcular_data_finalizacao(self):
                                                                                            
        if not self.prazo_dias or self.prazo_dias == 0:
            return None
        from datetime import timedelta
        data_base = self.processo.cliente.criado_em.date()
        return data_base + timedelta(days=self.prazo_dias)

