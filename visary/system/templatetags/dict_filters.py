"""
Filtros customizados para trabalhar com dicionários em templates.
"""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Retorna o valor de um dicionário usando a chave fornecida."""
    if dictionary is None:
        return None
    return dictionary.get(key)

