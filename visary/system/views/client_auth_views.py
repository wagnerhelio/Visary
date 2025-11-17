"""
Views de autenticação para clientes.
"""

from django.contrib import messages
from django.shortcuts import redirect


def cliente_logout_view(request):
    """View de logout para clientes."""
    if "cliente_id" in request.session:
        cliente_nome = request.session.get("cliente_nome", "Cliente")
        messages.success(request, f"Até logo, {cliente_nome}!")
        request.session.flush()
    return redirect("login")  # Redireciona para o login unificado

