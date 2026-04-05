from django.contrib import messages
from django.shortcuts import redirect


def client_logout_view(request):
    if "client_id" in request.session:
        client_name = request.session.get("client_name", "Cliente")
        messages.success(request, f"Até logo, {client_name}!")
        request.session.flush()
    return redirect("login")
