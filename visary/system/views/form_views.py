   
                                                    
   

from contextlib import suppress

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import (
    FormularioVistoForm,
    OpcaoSelecaoForm,
    PerguntaFormularioForm,
)
from system.models import FormularioVisto, OpcaoSelecao, PaisDestino, PerguntaFormulario, Viagem
from system.views.client_views import listar_clientes, obter_consultor_usuario, usuario_pode_gerenciar_todos


def _ler_filtros_formularios(request):
    return {
        "cliente": request.GET.get("cliente", "").strip(),
        "pais": request.GET.get("pais", "").strip(),
        "tipo_visto": request.GET.get("tipo_visto", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }


def _filtro_formulario_cliente_ok(cliente_info, viagem, filtros):
    if filtros["cliente"] and str(cliente_info["cliente"].pk) != filtros["cliente"]:
        return False
    if filtros["pais"] and str(viagem.pais_destino_id) != filtros["pais"]:
        return False
    if filtros["tipo_visto"] and str(cliente_info["tipo_visto"].pk) != filtros["tipo_visto"]:
        return False
    if filtros["status"] == "pendente" and cliente_info["completo"]:
        return False
    if filtros["status"] == "completo" and not cliente_info["completo"]:
        return False
    return True


def _ordenar_clientes_por_grupo_familiar(clientes):
    return sorted(
        clientes,
        key=lambda cliente: (
            cliente.cliente_principal_id or cliente.pk,
            1 if cliente.cliente_principal_id else 0,
            cliente.pk,
        ),
    )


def _aplicar_filtros_formularios_respostas(formularios_respostas, filtros):
    filtrados = []
    for item in formularios_respostas:
        clientes_filtrados = [
            cliente_info
            for cliente_info in item["clientes"]
            if _filtro_formulario_cliente_ok(cliente_info, item["viagem"], filtros)
        ]
        if clientes_filtrados:
            novo_item = dict(item)
            novo_item["clientes"] = clientes_filtrados
            filtrados.append(novo_item)
    return filtrados


def _opcoes_filtro_formularios(formularios_respostas):
    clientes_map = {}
    paises_map = {}
    tipos_map = {}
    for item in formularios_respostas:
        viagem = item["viagem"]
        paises_map.setdefault(viagem.pais_destino.pk, viagem.pais_destino)
        for cliente_info in item["clientes"]:
            cliente = cliente_info["cliente"]
            tipo_visto = cliente_info["tipo_visto"]
            clientes_map.setdefault(cliente.pk, cliente)
            tipos_map.setdefault(tipo_visto.pk, tipo_visto)
    return {
        "clientes_filtro": sorted(clientes_map.values(), key=lambda c: c.nome.lower()),
        "paises_filtro": sorted(paises_map.values(), key=lambda p: p.nome.lower()),
        "tipos_visto_filtro": sorted(tipos_map.values(), key=lambda t: t.nome.lower()),
    }


def _aplicar_filtros_tipos_formulario(formularios, request):
    filtros = {
        "busca": request.GET.get("busca", "").strip(),
        "pais": request.GET.get("pais", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }

    if filtros["busca"]:
        formularios = formularios.filter(tipo_visto__nome__icontains=filtros["busca"])
    if filtros["pais"]:
        formularios = formularios.filter(tipo_visto__pais_destino_id=filtros["pais"])
    if filtros["status"] == "ativo":
        formularios = formularios.filter(ativo=True)
    elif filtros["status"] == "inativo":
        formularios = formularios.filter(ativo=False)

    return formularios, filtros


@login_required
def home_formularios(request):
    from system.models import ClienteViagem, RespostaFormulario

    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    clientes_usuario = listar_clientes(request.user)
    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
                                            
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
                                                      
    def _obter_tipo_visto_cliente(viagem, cliente):
                                                                                                                
        with suppress(ClienteViagem.DoesNotExist):
            cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
                viagem=viagem, cliente=cliente
            )
            if cliente_viagem.tipo_visto:
                return cliente_viagem.tipo_visto
        return viagem.tipo_visto
    
                                                          
    def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
                                                                                   
        if not tipo_visto or not hasattr(tipo_visto, 'pk') or not tipo_visto.pk:
            return None
        try:
            if apenas_ativo:
                return FormularioVisto.objects.select_related('tipo_visto').get(
                    tipo_visto_id=tipo_visto.pk,
                    ativo=True
                )
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
        except FormularioVisto.DoesNotExist:
            return None
    
                                           
    formularios_respostas = []
    total_clientes_com_formulario = 0
    
    for viagem in viagens[:10]:                              
                                                          
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids)
        
        if not clientes_viagem.exists():
            continue
        
        clientes_por_formulario = {}
        
        clientes_ordenados = _ordenar_clientes_por_grupo_familiar(clientes_viagem)
        
        for cliente in clientes_ordenados:
            tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
            
            if not tipo_visto_cliente:
                continue
            
                                                             
            formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
            
            if not formulario:
                continue
            
                                                         
            chave = f"{viagem.pk}_{formulario.pk}"
            
            if chave not in clientes_por_formulario:
                clientes_por_formulario[chave] = {
                    "viagem": viagem,
                    "formulario": formulario,
                    "clientes": [],
                }
            
                                                                  
            total_perguntas = formulario.perguntas.filter(ativo=True).count()
            total_respostas = RespostaFormulario.objects.filter(
                viagem=viagem,
                cliente=cliente
            ).count()
            
            clientes_por_formulario[chave]["clientes"].append({
                "cliente": cliente,
                "tipo_visto": tipo_visto_cliente,
                "total_perguntas": total_perguntas,
                "total_respostas": total_respostas,
                "completo": total_respostas == total_perguntas if total_perguntas > 0 else False,
            })
            total_clientes_com_formulario += 1
        
        
        formularios_respostas.extend(clientes_por_formulario.values())
    
    formularios_pendentes = []
    formularios_preenchidos = []
    for item in formularios_respostas:
        for cli in item["clientes"]:
            entry = {
                "viagem": item["viagem"],
                "cliente_info": {
                    "cliente": cli["cliente"],
                    "tipo_visto": cli["tipo_visto"],
                    "total_perguntas": cli["total_perguntas"],
                    "total_respostas": cli["total_respostas"],
                    "completo": cli["completo"],
                },
            }
            if cli["completo"]:
                formularios_preenchidos.append(entry)
            else:
                formularios_pendentes.append(entry)

    filtros_aplicados = _ler_filtros_formularios(request)
    formularios_respostas = _aplicar_filtros_formularios_respostas(formularios_respostas, filtros_aplicados)
    formularios_pendentes = [
        item
        for item in formularios_pendentes
        if _filtro_formulario_cliente_ok(item["cliente_info"], item["viagem"], filtros_aplicados)
    ]
    formularios_preenchidos = [
        item
        for item in formularios_preenchidos
        if _filtro_formulario_cliente_ok(item["cliente_info"], item["viagem"], filtros_aplicados)
    ]
    opcoes_filtro = _opcoes_filtro_formularios(formularios_respostas)

    total_formularios_kpi = len(formularios_pendentes) + len(formularios_preenchidos)
    total_pendentes_kpi = len(formularios_pendentes)
    total_completos_kpi = len(formularios_preenchidos)

    contexto = {
        "total_formularios": total_clientes_com_formulario,
        "formularios_respostas": formularios_respostas,
        "formularios_pendentes": formularios_pendentes,
        "formularios_preenchidos": formularios_preenchidos,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        **opcoes_filtro,
        "total_formularios_kpi": total_formularios_kpi,
        "total_pendentes_kpi": total_pendentes_kpi,
        "total_completos_kpi": total_completos_kpi,
    }

    return render(request, "forms/home_formularios.html", contexto)


@login_required
def listar_formularios(request):
    from system.models import ClienteViagem, RespostaFormulario
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    viagens = Viagem.objects.select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
                                                      
    def _obter_tipo_visto_cliente(viagem, cliente):
                                                                                                                
        with suppress(ClienteViagem.DoesNotExist):
            cliente_viagem = ClienteViagem.objects.select_related('tipo_visto__formulario').get(
                viagem=viagem, cliente=cliente
            )
            if cliente_viagem.tipo_visto:
                return cliente_viagem.tipo_visto
        return viagem.tipo_visto
    
                                                          
    def _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True):
                                                                                   
        if not tipo_visto or not hasattr(tipo_visto, 'pk') or not tipo_visto.pk:
            return None
        try:
            if apenas_ativo:
                return FormularioVisto.objects.select_related('tipo_visto').get(
                    tipo_visto_id=tipo_visto.pk,
                    ativo=True
                )
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
        except FormularioVisto.DoesNotExist:
            return None
    
                                           
    formularios_respostas = []
    
    for viagem in viagens:
                                                          
        clientes_viagem = viagem.clientes.all()
        
        if not clientes_viagem.exists():
            continue
        
        clientes_por_formulario = {}
        
        clientes_ordenados = _ordenar_clientes_por_grupo_familiar(clientes_viagem)
        
        for cliente in clientes_ordenados:
            tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
            
            if not tipo_visto_cliente:
                continue
            
                                                             
            formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=True)
            
            if not formulario:
                continue
            
                                                         
            chave = f"{viagem.pk}_{formulario.pk}"
            
            if chave not in clientes_por_formulario:
                clientes_por_formulario[chave] = {
                    "viagem": viagem,
                    "formulario": formulario,
                    "clientes": [],
                }
            
                                                                  
            total_perguntas = formulario.perguntas.filter(ativo=True).count()
            total_respostas = RespostaFormulario.objects.filter(
                viagem=viagem,
                cliente=cliente
            ).count()
            
            clientes_por_formulario[chave]["clientes"].append({
                "cliente": cliente,
                "tipo_visto": tipo_visto_cliente,
                "total_perguntas": total_perguntas,
                "total_respostas": total_respostas,
                "completo": total_respostas == total_perguntas if total_perguntas > 0 else False,
            })
        
                                
        formularios_respostas.extend(clientes_por_formulario.values())

    filtros_aplicados = _ler_filtros_formularios(request)
    formularios_respostas = _aplicar_filtros_formularios_respostas(formularios_respostas, filtros_aplicados)
    opcoes_filtro = _opcoes_filtro_formularios(formularios_respostas)
    total_formularios_kpi = sum(len(item["clientes"]) for item in formularios_respostas)
    total_pendentes_kpi = sum(
        1
        for item in formularios_respostas
        for cliente in item["clientes"]
        if not cliente["completo"]
    )
    total_completos_kpi = total_formularios_kpi - total_pendentes_kpi
    
    contexto = {
        "formularios_respostas": formularios_respostas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        **opcoes_filtro,
        "total_formularios_kpi": total_formularios_kpi,
        "total_pendentes_kpi": total_pendentes_kpi,
        "total_completos_kpi": total_completos_kpi,
    }

    return render(request, "forms/listar_formularios.html", contexto)


@login_required
def home_tipos_formulario(request):
    consultor = obter_consultor_usuario(request.user)
    if not usuario_pode_gerenciar_todos(request.user, consultor):
        raise PermissionDenied
    pode_gerenciar_todos = True

    formularios = FormularioVisto.objects.select_related("tipo_visto", "tipo_visto__pais_destino").all().order_by(
        "tipo_visto__nome"
    )
    formularios, filtros_aplicados = _aplicar_filtros_tipos_formulario(formularios, request)
    total_formularios = formularios.count()

    contexto = {
        "formularios": formularios[:10],
        "total_formularios": total_formularios,
        "perfil_usuario": consultor.perfil.nome if consultor else "Administrador",
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        "paises": PaisDestino.objects.filter(ativo=True).order_by("nome"),
    }

    return render(request, "forms/home_tipos_formulario.html", contexto)


@login_required
def criar_formulario(request):
                                                         
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = FormularioVistoForm(data=request.POST)
        if form.is_valid():
            formulario = form.save()
            messages.success(
                request,
                f"Formulário para {formulario.tipo_visto.nome} criado com sucesso.",
            )
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível criar o formulário. Verifique os campos.")
    else:
        form = FormularioVistoForm()

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_formulario.html", contexto)


@login_required
def listar_tipos_formulario(request):
                                                      
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    formularios = (
        FormularioVisto.objects.select_related("tipo_visto", "tipo_visto__pais_destino")
        .prefetch_related("perguntas")
        .all()
        .order_by("tipo_visto__nome")
    )
    formularios, filtros_aplicados = _aplicar_filtros_tipos_formulario(formularios, request)

    contexto = {
        "formularios": formularios,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        "paises": PaisDestino.objects.filter(ativo=True).order_by("nome"),
    }

    return render(request, "forms/listar_tipos_formulario.html", contexto)


@login_required
def editar_formulario(request, pk: int):
                                                  
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(
        FormularioVisto.objects.select_related("tipo_visto"), pk=pk
    )
    perguntas = (
        formulario.perguntas.all()
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )

    if request.method == "POST":
        form = FormularioVistoForm(data=request.POST, instance=formulario)
        if form.is_valid():
            form.save()
            messages.success(request, "Formulário atualizado com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível atualizar o formulário.")
    else:
        form = FormularioVistoForm(instance=formulario)

    contexto = {
        "form": form,
        "formulario": formulario,
        "perguntas": perguntas,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_formulario.html", contexto)


@login_required
def excluir_formulario(request, pk: int):
                                        
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(FormularioVisto, pk=pk)
    tipo_visto_nome = formulario.tipo_visto.nome
    formulario.delete()

    messages.success(request, f"Formulário de {tipo_visto_nome} excluído com sucesso.")
    return redirect("system:listar_tipos_formulario")


@login_required
def criar_pergunta(request, formulario_id: int):
                                               
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    formulario = get_object_or_404(FormularioVisto, pk=formulario_id)

    if request.method == "POST":
        form = PerguntaFormularioForm(data=request.POST, formulario=formulario)
        if form.is_valid():
            pergunta = form.save()
            messages.success(request, f"Pergunta '{pergunta.pergunta}' adicionada com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível criar a pergunta. Verifique os campos.")
    else:
        form = PerguntaFormularioForm(formulario=formulario)

    contexto = {
        "form": form,
        "formulario": formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_pergunta.html", contexto)


@login_required
def editar_pergunta(request, pk: int):
                                    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(
        PerguntaFormulario.objects.select_related("formulario"), pk=pk
    )
    formulario = pergunta.formulario
    opcoes = pergunta.opcoes.all().order_by("ordem", "texto") if pergunta.tipo_campo == "selecao" else []

    if request.method == "POST":
        form = PerguntaFormularioForm(data=request.POST, instance=pergunta, formulario=formulario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Pergunta '{pergunta.pergunta}' atualizada com sucesso.")
            return redirect("system:editar_formulario", pk=formulario.pk)
        messages.error(request, "Não foi possível atualizar a pergunta.")
    else:
        form = PerguntaFormularioForm(instance=pergunta, formulario=formulario)

    contexto = {
        "form": form,
        "pergunta": pergunta,
        "formulario": formulario,
        "opcoes": opcoes,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_pergunta.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_pergunta(request, pk: int):
                              
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(PerguntaFormulario.objects.select_related("formulario"), pk=pk)
    formulario = pergunta.formulario
    pergunta_texto = pergunta.pergunta
    pergunta.delete()

    messages.success(request, f"Pergunta '{pergunta_texto}' excluída com sucesso.")
    return redirect("system:editar_formulario", pk=formulario.pk)


@login_required
def criar_opcao_selecao(request, pergunta_id: int):
                                                        
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    pergunta = get_object_or_404(
        PerguntaFormulario.objects.select_related("formulario"), pk=pergunta_id
    )
    
                                               
    if pergunta.tipo_campo != "selecao":
        messages.error(request, "Apenas perguntas do tipo 'Seleção' podem ter opções.")
        return redirect("system:editar_pergunta", pk=pergunta.pk)

    if request.method == "POST":
        form = OpcaoSelecaoForm(data=request.POST, pergunta=pergunta)
        if form.is_valid():
            opcao = form.save()
            messages.success(request, f"Opção '{opcao.texto}' adicionada com sucesso.")
            return redirect("system:editar_pergunta", pk=pergunta.pk)
        messages.error(request, "Não foi possível criar a opção. Verifique os campos.")
    else:
        form = OpcaoSelecaoForm(pergunta=pergunta)

    contexto = {
        "form": form,
        "pergunta": pergunta,
        "formulario": pergunta.formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/criar_opcao_selecao.html", contexto)


@login_required
def selecionar_viagem_cliente_formulario(request):
                                                                         
    from system.models import ClienteConsultoria
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
                                            
    if pode_gerenciar_todos:
        clientes_ids = list(ClienteConsultoria.objects.values_list("pk", flat=True))
    else:
                                                      
        clientes_usuario = listar_clientes(request.user)
        clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
                                                               
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids,
        tipo_visto__formulario__isnull=False,
        tipo_visto__formulario__ativo=True
    ).select_related(
        "pais_destino",
        "tipo_visto",
        "tipo_visto__formulario",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")
    
                                                          
    if request.method == "POST":
        viagem_id = request.POST.get("viagem_id")
        cliente_id = request.POST.get("cliente_id")
        
        if not viagem_id or not cliente_id:
            messages.error(request, "Por favor, selecione uma viagem e um cliente.")
            return redirect("system:selecionar_viagem_cliente_formulario")
        
        try:
            viagem = Viagem.objects.get(pk=viagem_id)
            cliente = ClienteConsultoria.objects.get(pk=cliente_id)
            
                                 
            if not pode_gerenciar_todos and int(cliente_id) not in clientes_ids:
                raise PermissionDenied("Você não tem permissão para acessar este cliente.")
            
            if cliente not in viagem.clientes.all():
                messages.error(request, "Este cliente não está vinculado a esta viagem.")
                return redirect("system:selecionar_viagem_cliente_formulario")
            
                                                 
            return redirect("system:editar_formulario_cliente", viagem_id=viagem_id, cliente_id=cliente_id)
        except (Viagem.DoesNotExist, ClienteConsultoria.DoesNotExist, ValueError):
            messages.error(request, "Viagem ou cliente não encontrado.")
            return redirect("system:selecionar_viagem_cliente_formulario")
    
                                    
    viagens_com_clientes = []
    for viagem in viagens:
        clientes_viagem = viagem.clientes.filter(pk__in=clientes_ids).select_related("cliente_principal")
        if clientes_viagem.exists():
            viagens_com_clientes.append({
                "viagem": viagem,
                "clientes": clientes_viagem,
            })
    
    contexto = {
        "viagens_com_clientes": viagens_com_clientes,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "forms/selecionar_viagem_cliente_formulario.html", contexto)


@login_required
def editar_opcao_selecao(request, pk: int):
                                            
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    opcao = get_object_or_404(
        OpcaoSelecao.objects.select_related("pergunta__formulario"), pk=pk
    )
    pergunta = opcao.pergunta

    if request.method == "POST":
        form = OpcaoSelecaoForm(data=request.POST, instance=opcao, pergunta=pergunta)
        if form.is_valid():
            form.save()
            messages.success(request, f"Opção '{opcao.texto}' atualizada com sucesso.")
            return redirect("system:editar_pergunta", pk=pergunta.pk)
        messages.error(request, "Não foi possível atualizar a opção.")
    else:
        form = OpcaoSelecaoForm(instance=opcao, pergunta=pergunta)

    contexto = {
        "form": form,
        "opcao": opcao,
        "pergunta": pergunta,
        "formulario": pergunta.formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "forms/editar_opcao_selecao.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_opcao_selecao(request, pk: int):
                                      
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)

    if not pode_gerenciar_todos:
        raise PermissionDenied

    opcao = get_object_or_404(
        OpcaoSelecao.objects.select_related("pergunta__formulario"), pk=pk
    )
    pergunta = opcao.pergunta
    opcao_texto = opcao.texto
    opcao.delete()

    messages.success(request, f"Opção '{opcao_texto}' excluída com sucesso.")
    return redirect("system:editar_pergunta", pk=pergunta.pk)

