import logging

from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from system.models import ClienteViagem, Financeiro, StatusFinanceiro, StatusProcesso, Viagem, ViagemStatusProcesso

logger = logging.getLogger("visary.financial")


def _criar_registros_financeiros_para_viagem(viagem: Viagem) -> None:
    from system.models import ClienteViagem

    if viagem.valor_assessoria <= 0:
        return

    with transaction.atomic():
        registros_existentes = Financeiro.objects.filter(viagem=viagem)
        clientes_com_registro = set(
            registros_existentes.exclude(cliente=None).values_list("cliente_id", flat=True)
        )
        clientes_viagem = ClienteViagem.objects.filter(viagem=viagem).select_related("cliente")

        if clientes_viagem.exists():
            registros_existentes.filter(cliente=None).delete()

            cv_principal = clientes_viagem.filter(papel="principal").first()
            if cv_principal:
                if cv_principal.cliente_id not in clientes_com_registro:
                    Financeiro.objects.create(
                        viagem=viagem,
                        cliente=cv_principal.cliente,
                        assessor_responsavel=viagem.assessor_responsavel,
                        valor=viagem.valor_assessoria,
                        status=StatusFinanceiro.PENDENTE,
                        criado_por=viagem.criado_por,
                    )
                    logger.info(
                        "Registro financeiro criado para principal '%s' (pk=%s), viagem pk=%s, valor=%s",
                        cv_principal.cliente.nome_completo, cv_principal.cliente_id, viagem.pk, viagem.valor_assessoria,
                    )
                return

            primeiro_cv = clientes_viagem.first()
            if primeiro_cv and primeiro_cv.cliente_id not in clientes_com_registro:
                Financeiro.objects.create(
                    viagem=viagem,
                    cliente=primeiro_cv.cliente,
                    assessor_responsavel=viagem.assessor_responsavel,
                    valor=viagem.valor_assessoria,
                    status=StatusFinanceiro.PENDENTE,
                    criado_por=viagem.criado_por,
                )
                logger.info(
                    "Registro financeiro criado para primeiro cliente '%s' (pk=%s), viagem pk=%s",
                    primeiro_cv.cliente.nome_completo, primeiro_cv.cliente_id, viagem.pk,
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
            logger.info(
                "Registro financeiro sem cliente criado para viagem pk=%s",
                viagem.pk,
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


@receiver(post_save, sender=ClienteViagem)
def auto_promover_primeiro_principal(sender, instance: ClienteViagem, created: bool, **kwargs) -> None:
    """Se a viagem não tem principal, promove este cliente automaticamente."""
    if not created:
        return
    viagem = instance.viagem
    if not ClienteViagem.objects.filter(viagem=viagem, papel="principal").exists():
        instance.papel = "principal"
        instance.cliente_principal_viagem = None
        instance.save(update_fields=["papel", "cliente_principal_viagem", "atualizado_em"])


@receiver(post_delete, sender=ClienteViagem)
def auto_promover_ao_remover_principal(sender, instance: ClienteViagem, **kwargs) -> None:
    """Se o principal foi removido, promove o primeiro dependente."""
    if instance.papel != "principal":
        return
    viagem_id = instance.viagem_id
    proximo = ClienteViagem.objects.filter(viagem_id=viagem_id, papel="dependente").first()
    if proximo:
        proximo.papel = "principal"
        proximo.cliente_principal_viagem = None
        proximo.save(update_fields=["papel", "cliente_principal_viagem", "atualizado_em"])


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
