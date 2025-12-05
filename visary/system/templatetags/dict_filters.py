"""
Filtros customizados para trabalhar com dicionários e objetos em templates.
"""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Retorna o valor de um dicionário usando a chave fornecida."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def getattr_filter(obj, attr_name):
    """Retorna o valor de um atributo de um objeto usando o nome do atributo."""
    if obj is None:
        return None
    try:
        return getattr(obj, attr_name, None)
    except AttributeError:
        return None


@register.filter
def get_form_field(form, field_name):
    """Retorna um campo do formulário Django usando o nome do campo."""
    if form is None or not hasattr(form, 'fields'):
        return None
    try:
        # Tenta acessar o campo através do índice do formulário (form[nome])
        if field_name in form.fields:
            return form[field_name]
        return None
    except (KeyError, AttributeError):
        return None

