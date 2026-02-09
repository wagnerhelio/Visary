from django import template

from system.views.client_views import obter_consultor_usuario, usuario_pode_gerenciar_todos

register = template.Library()


@register.simple_tag
def can_edit_cliente(user, cliente):
    if not user or not cliente:
        return False
    consultor = obter_consultor_usuario(user)
    if usuario_pode_gerenciar_todos(user, consultor):
        return True
    if consultor and getattr(cliente, "assessor_responsavel_id", None) == consultor.pk:
        return True
    criado_por_id = getattr(cliente, "criado_por_id", None)
    return criado_por_id is not None and criado_por_id == getattr(user, "id", None)
