"""
Views relacionadas ao painel inicial da consultoria.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from system.views.client_views import listar_clientes, obter_consultor_usuario


@login_required
def home(request):
    """
    Página inicial resumida do painel.
    """
    consultor = obter_consultor_usuario(request.user)

    clientes_qs = listar_clientes(request.user)
    clientes = clientes_qs[:5]
    total_clientes = clientes_qs.count()

    contexto = {
        "clientes": clientes,
        "total_clientes": total_clientes,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "home/home.html", contexto)

