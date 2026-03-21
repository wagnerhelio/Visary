from django.db import models
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from system.models import Financeiro, StatusFinanceiro, StatusProcesso, Viagem, ViagemStatusProcesso


def _criar_registros_financeiros_para_viagem(viagem: Viagem) -> None:
    if viagem.valor_assessoria <= 0:
        return

    registros_existentes = Financeiro.objects.filter(viagem=viagem)
    clientes_com_registro = set(
        registros_existentes.exclude(cliente=None).values_list("cliente_id", flat=True)
    )
    clientes = viagem.clientes.select_related("cliente_principal").all()

    if clientes.exists():
        registros_existentes.filter(cliente=None).delete()
        cliente_principal = None
        dependentes = []

        for cliente in clientes:
            if cliente.is_principal:
                cliente_principal = cliente
            else:
                dependentes.append(cliente)

        if cliente_principal:
            if cliente_principal.pk not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=cliente_principal,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status=StatusFinanceiro.PENDENTE,
                    criado_por=viagem.criado_por,
                )
            return

        if dependentes:
            primeiro_dependente = dependentes[0]
            principal_do_grupo = primeiro_dependente.cliente_principal
            destino = principal_do_grupo or primeiro_dependente
            if destino.pk not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=destino,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status=StatusFinanceiro.PENDENTE,
                    criado_por=viagem.criado_por,
                )
            return

        primeiro_cliente = clientes.first()
        if primeiro_cliente and primeiro_cliente.pk not in clientes_com_registro:
            Financeiro.objects.create(
                viagem=viagem,
                cliente=primeiro_cliente,
                assessor_responsavel=viagem.assessor_responsavel,
                valor=viagem.valor_assessoria,
                status=StatusFinanceiro.PENDENTE,
                criado_por=viagem.criado_por,
            )
        return

    if not registros_existentes.filter(cliente=None).exists():
        Financeiro.objects.create(
            viagem=viagem,
            cliente=None,
            assessor_responsavel=viagem.assessor_responsavel,
            valor=viagem.valor_assessoria,
            status=StatusFinanceiro.PENDENTE,
            criado_por=viagem.criado_por,
        )


def _sincronizar_status_viagem(viagem: Viagem) -> None:
    filtro = models.Q(tipo_visto__isnull=True)
    if viagem.tipo_visto_id:
        filtro |= models.Q(tipo_visto=viagem.tipo_visto)

    status_ids = set(StatusProcesso.objects.filter(filtro, ativo=True).values_list("id", flat=True))
    existentes = set(
        ViagemStatusProcesso.objects.filter(viagem=viagem).values_list("status_id", flat=True)
    )

    novos = status_ids - existentes
    remover = existentes - status_ids

    for status_id in novos:
        ViagemStatusProcesso.objects.create(viagem=viagem, status_id=status_id)

    if remover:
        ViagemStatusProcesso.objects.filter(viagem=viagem, status_id__in=remover).delete()


@receiver(post_save, sender=Viagem)
def criar_registro_financeiro(sender, instance: Viagem, created: bool, **kwargs) -> None:
    if created and instance.clientes.exists():
        _criar_registros_financeiros_para_viagem(instance)


@receiver(m2m_changed, sender=Viagem.clientes.through)
def criar_registro_financeiro_ao_adicionar_cliente(sender, instance: Viagem, action: str, **kwargs) -> None:
    if action == "post_add" and instance.pk:
        _criar_registros_financeiros_para_viagem(instance)


@receiver(post_save, sender=Viagem)
def sincronizar_status_viagem_post_save(sender, instance: Viagem, **kwargs) -> None:
    _sincronizar_status_viagem(instance)


@receiver(post_save, sender=StatusProcesso)
def sincronizar_status_viagem_status(sender, instance: StatusProcesso, **kwargs) -> None:
    viagens = Viagem.objects.all()
    if instance.tipo_visto_id:
        viagens = viagens.filter(tipo_visto=instance.tipo_visto)
    for viagem in viagens:
        _sincronizar_status_viagem(viagem)
