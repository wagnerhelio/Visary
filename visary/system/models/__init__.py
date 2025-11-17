"""
Submódulos de modelos do app system.

Este pacote organiza entidades em domínios específicos
para facilitar a manutenção e leitura.
"""

from .permission_models import *  # noqa: F401,F403

__all__ = (
    "Modulo",
    "Perfil",
    "UsuarioConsultoria",
)

