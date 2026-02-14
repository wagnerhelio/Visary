"""
Views relacionadas ao painel inicial da consultoria.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from consultancy.models import FormularioVisto, PaisDestino, Partner, Processo, TipoVisto, Viagem
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

    # Contadores de KPIs para o Painel Principal
    total_viagens = Viagem.objects.count()
    total_processos = Processo.objects.count()
    total_paises = PaisDestino.objects.count()
    total_tipos = TipoVisto.objects.count()
    total_partners = Partner.objects.count()
    total_tipos_formularios = FormularioVisto.objects.count()
    
    # Total de formulários preenchidos (contar RespostaFormulario únicos)
    from consultancy.models import RespostaFormulario
    total_formularios = RespostaFormulario.objects.values('viagem', 'cliente').distinct().count()

    contexto = {
        "clientes": clientes,
        "total_clientes": total_clientes,
        "total_viagens": total_viagens,
        "total_processos": total_processos,
        "total_paises": total_paises,
        "total_tipos": total_tipos,
        "total_partners": total_partners,
        "total_tipos_formularios": total_tipos_formularios,
        "total_formularios": total_formularios,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "home/home.html", contexto)

