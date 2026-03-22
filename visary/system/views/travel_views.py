   
                                        
   

from contextlib import suppress
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from decimal import Decimal, InvalidOperation

from django.utils.dateparse import parse_date

from system.forms import PaisDestinoForm, TipoVistoForm, ViagemForm
from system.models import ClienteConsultoria, ClienteViagem, FormularioVisto, OpcaoSelecao, Partner, PaisDestino, Processo, RespostaFormulario, TipoVisto, Viagem
from system.models.financial_models import Financeiro
from system.models import UsuarioConsultoria
from system.views.client_views import listar_clientes, obter_consultor_usuario, usuario_pode_gerenciar_todos
from system.services.form_stages import build_stage_items, filter_questions_by_stage, resolve_stage_token
from system.services.form_prefill import prefill_form_answers


def _limpar_flags_viagens_cadastradas(request):
                                                               
    if request.method == "GET":
        keys_to_clean = [key for key in request.session.keys() if key.startswith('viagem_cadastrada_')]
        for key in keys_to_clean:
            request.session.pop(key, None)
        request.session.modified = True


def _obter_viagens_com_formularios_nao_preenchidos(viagens):
                                                                 
    viagens_com_formulario = []
    for viagem in viagens:
        if formulario := _obter_formulario_por_tipo_visto(viagem.tipo_visto, apenas_ativo=True):
            total_clientes = viagem.clientes.count()
            if total_clientes > 0:
                clientes_com_resposta = RespostaFormulario.objects.filter(
                    viagem=viagem
                ).values_list("cliente_id", flat=True).distinct().count()
                clientes_sem_resposta = total_clientes - clientes_com_resposta
                if clientes_sem_resposta > 0:
                    viagens_com_formulario.append({
                        "viagem": viagem,
                        "total_clientes": total_clientes,
                        "clientes_sem_resposta": clientes_sem_resposta,
                    })
    return viagens_com_formulario


def _filtrar_mensagens_para_template(request):
                                                                                       
    storage = messages.get_messages(request)
    filtered_messages = []
    viagem_message_shown = False
    seen_texts = set()
    
    for message in storage:
        message_text = str(message)
                                                     
        if "Viagem cadastrada" in message_text:
            if not viagem_message_shown:
                viagem_message_shown = True
                filtered_messages.append(message)
        elif message_text not in seen_texts:
                                                   
            seen_texts.add(message_text)
            filtered_messages.append(message)
    
    return filtered_messages


@login_required
def home_viagens(request):
                                                            
    _limpar_flags_viagens_cadastradas(request)
    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
                                                                                                                              
    clientes_usuario = listar_clientes(request.user)
    clientes_ids = list(clientes_usuario.values_list("pk", flat=True))
    
                                                              
    viagens = Viagem.objects.filter(
        clientes__pk__in=clientes_ids
    ).select_related(
        "pais_destino",
        "tipo_visto__formulario",
        "assessor_responsavel",
    ).prefetch_related("clientes").distinct().order_by("-data_prevista_viagem")

    filtros_aplicados = {}
    viagens = _aplicar_filtros_viagens(viagens, request, filtros_aplicados, incluir_assessor=False)
    
                     
                                                                  
    viagens_limitadas = viagens[:10]
    
                                                                                    
    viagens_com_formulario = _obter_viagens_com_formularios_nao_preenchidos(viagens_limitadas)
    kpis = _montar_kpis_viagens(viagens)
    
                                       
    mensagens_filtradas = _filtrar_mensagens_para_template(request)
    
                                                                
    paises = PaisDestino.objects.filter(ativo=True).order_by("nome")
    tipos_visto = TipoVisto.objects.filter(ativo=True).select_related("pais_destino").order_by("pais_destino__nome", "nome")

    contexto = {
        "total_viagens": viagens.count(),
        "viagens": viagens_limitadas,
        "viagens_formularios_nao_preenchidos": viagens_com_formulario,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "mensagens_filtradas": mensagens_filtradas,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "consultor": consultor,
        "assessores": UsuarioConsultoria.objects.filter(ativo=True).order_by("nome"),
        "paises": paises,
        "tipos_visto": tipos_visto,
        "clientes": clientes_usuario.order_by("nome"),
        "filtros_aplicados": filtros_aplicados,
        "parceiros": Partner.objects.filter(ativo=True).order_by("nome_empresa", "nome_responsavel"),
        **kpis,
    }

    return render(request, "travel/home_viagens.html", contexto)


@login_required
def home_paises_destino(request):
    consultor = obter_consultor_usuario(request.user)
    if not usuario_pode_gerenciar_todos(request.user, consultor):
        raise PermissionDenied
    pode_gerenciar_todos = True
    
    paises = PaisDestino.objects.all().order_by("nome")
    paises, filtros_aplicados = _aplicar_filtros_paises_destino(paises, request)
    total_paises = paises.count()
    
    contexto = {
        "paises": paises[:10],
        "total_paises": total_paises,
        "perfil_usuario": consultor.perfil.nome if consultor else "Administrador",
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
    }
    
    return render(request, "travel/home_paises_destino.html", contexto)


@login_required
def home_tipos_visto(request):
    consultor = obter_consultor_usuario(request.user)
    if not usuario_pode_gerenciar_todos(request.user, consultor):
        raise PermissionDenied
    pode_gerenciar_todos = True
    
    tipos_visto = TipoVisto.objects.select_related("pais_destino").order_by("pais_destino__nome", "nome")
    tipos_visto, filtros_aplicados = _aplicar_filtros_tipos_visto(tipos_visto, request)
    total_tipos = tipos_visto.count()
    
    contexto = {
        "tipos_visto": tipos_visto[:10],
        "total_tipos": total_tipos,
        "perfil_usuario": consultor.perfil.nome if consultor else "Administrador",
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        "paises": PaisDestino.objects.filter(ativo=True).order_by("nome"),
    }
    
    return render(request, "travel/home_tipos_visto.html", contexto)


def _aplicar_filtros_paises_destino(paises, request):
    filtros = {
        "busca": request.GET.get("busca", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "codigo_iso": request.GET.get("codigo_iso", "").strip(),
    }

    if filtros["busca"]:
        paises = paises.filter(nome__icontains=filtros["busca"])
    if filtros["status"] == "ativo":
        paises = paises.filter(ativo=True)
    elif filtros["status"] == "inativo":
        paises = paises.filter(ativo=False)
    if filtros["codigo_iso"]:
        paises = paises.filter(codigo_iso__icontains=filtros["codigo_iso"])

    return paises, filtros


def _aplicar_filtros_tipos_visto(tipos_visto, request):
    filtros = {
        "busca": request.GET.get("busca", "").strip(),
        "pais": request.GET.get("pais", "").strip(),
        "status": request.GET.get("status", "").strip(),
    }

    if filtros["busca"]:
        tipos_visto = tipos_visto.filter(nome__icontains=filtros["busca"])
    if filtros["pais"]:
        with suppress(ValueError, TypeError):
            tipos_visto = tipos_visto.filter(pais_destino_id=int(filtros["pais"]))
    if filtros["status"] == "ativo":
        tipos_visto = tipos_visto.filter(ativo=True)
    elif filtros["status"] == "inativo":
        tipos_visto = tipos_visto.filter(ativo=False)

    return tipos_visto, filtros


@login_required
def criar_pais_destino(request):
                                                         
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = PaisDestinoForm(data=request.POST, user=request.user)
        if form.is_valid():
            pais = form.save(commit=False)
            pais.criado_por = request.user
            pais.save()
            messages.success(request, f"País {form.cleaned_data['nome']} cadastrado com sucesso.")
            return redirect("system:home_paises_destino")
        messages.error(request, "Não foi possível cadastrar o país. Verifique os campos.")
    else:
        form = PaisDestinoForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/criar_pais_destino.html", contexto)


@login_required
def criar_tipo_visto(request):
                                                       
    consultor = obter_consultor_usuario(request.user)

    if request.method == "POST":
        form = TipoVistoForm(data=request.POST, user=request.user)
        if form.is_valid():
            tipo_visto = form.save(commit=False)
            tipo_visto.criado_por = request.user
            tipo_visto.save()
            messages.success(request, f"Tipo de visto {form.cleaned_data['nome']} cadastrado com sucesso.")
            return redirect("system:home_tipos_visto")
        messages.error(request, "Não foi possível cadastrar o tipo de visto. Verifique os campos.")
    else:
        form = TipoVistoForm(user=request.user)

    contexto = {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }

    return render(request, "travel/criar_tipo_visto.html", contexto)


def _processar_tipos_visto_individuals(viagem, clientes_selecionados, membros_viagem_separada_ids, request):
                                                                      
                                                                                                 
    membros_com_visto_diferente = []
    
    for cliente in clientes_selecionados:
        if cliente.pk in membros_viagem_separada_ids:
            continue
        
        tipo_visto_cliente = viagem.tipo_visto                                   
                                                                         
        if tipo_visto_id := (
            request.POST.get(f"tipo_visto_dependente_{cliente.pk}") or
            request.POST.get(f"tipo_visto_cliente_{cliente.pk}")
        ):
            with suppress(ValueError, TypeError):
                if tipo_visto_obj := TipoVisto.objects.filter(pk=int(tipo_visto_id)).first():
                    tipo_visto_cliente = tipo_visto_obj
        
                                                                                           
                                                                    
        if tipo_visto_cliente.pk != viagem.tipo_visto.pk:
            membros_com_visto_diferente.append(cliente.pk)
        else:
                                                                       
            ClienteViagem.objects.update_or_create(
                viagem=viagem,
                cliente=cliente,
                defaults={"tipo_visto": tipo_visto_cliente}
            )
    
    return membros_com_visto_diferente


def _processar_viagens_separadas(viagem, membros_viagem_separada_ids, request):
                                                                                               
    if not membros_viagem_separada_ids:
        return []
    
    viagens_criadas = []
    
                                                             
    ClienteViagem.objects.filter(viagem=viagem, cliente_id__in=membros_viagem_separada_ids).delete()
    viagem.clientes.remove(*membros_viagem_separada_ids)
    
    for cliente_id in membros_viagem_separada_ids:
        with suppress(ValueError, TypeError):
            cliente_membro = ClienteConsultoria.objects.get(pk=cliente_id)
            
                                                    
            pais_destino_id = request.POST.get(f"pais_destino_dependente_{cliente_id}")
            tipo_visto_id = request.POST.get(f"tipo_visto_dependente_{cliente_id}")
            data_viagem = request.POST.get(f"data_viagem_dependente_{cliente_id}")
            data_retorno = request.POST.get(f"data_retorno_dependente_{cliente_id}")
            
                                                                           
            pais_destino = viagem.pais_destino
            if pais_destino_id:
                with suppress(ValueError, TypeError):
                    if pais_obj := PaisDestino.objects.filter(pk=int(pais_destino_id)).first():
                        pais_destino = pais_obj
            
            tipo_visto = viagem.tipo_visto
            if tipo_visto_id:
                with suppress(ValueError, TypeError):
                    if tipo_visto_obj := TipoVisto.objects.filter(pk=int(tipo_visto_id)).first():
                        tipo_visto = tipo_visto_obj
            
            data_prevista_viagem = viagem.data_prevista_viagem
            if data_viagem:
                from django.utils.dateparse import parse_date
                if parsed_date := parse_date(data_viagem):
                    data_prevista_viagem = parsed_date
            
            data_prevista_retorno = viagem.data_prevista_retorno
            if data_retorno:
                from django.utils.dateparse import parse_date
                if parsed_date := parse_date(data_retorno):
                    data_prevista_retorno = parsed_date
            
            viagem_separada = Viagem.objects.create(
                assessor_responsavel=viagem.assessor_responsavel,
                pais_destino=pais_destino,
                tipo_visto=tipo_visto,
                data_prevista_viagem=data_prevista_viagem,
                data_prevista_retorno=data_prevista_retorno,
                valor_assessoria=Decimal('0.00'),                                
                observacoes=f"Viagem separada para {cliente_membro.nome} (membro de {viagem})",
                criado_por=viagem.criado_por,
            )
            ClienteViagem.objects.create(
                viagem=viagem_separada,
                cliente=cliente_membro,
                tipo_visto=viagem_separada.tipo_visto
            )
            viagens_criadas.append(viagem_separada)
    
    return viagens_criadas


def _organizar_membros_viagem(clientes_ids_list):
                                                                             
    clientes_objs = ClienteConsultoria.objects.filter(
        pk__in=clientes_ids_list
    ).select_related('cliente_principal', 'assessor_responsavel').order_by('nome')
    
    cliente_principal = None
    dependentes = []
    
    for cliente in clientes_objs:
        if cliente.is_principal:
            cliente_principal = cliente
        else:
            dependentes.append(cliente)
    
    membros_data = []
    if cliente_principal:
        membros_data.append({
            'cliente': cliente_principal,
            'tipo': 'principal',
            'tipo_visto': None,
        })
    
    membros_data.extend({
        'cliente': dependente,
        'tipo': 'dependente',
        'cliente_principal': dependente.cliente_principal,
        'tipo_visto': None,
    } for dependente in dependentes)
    
    return membros_data


def _limpar_flags_cadastro_cliente(request):
                                                                        
                                 
    keys_to_remove = [key for key in request.session.keys() if key.startswith('cadastro_finalizado_')]
    for key in keys_to_remove:
        request.session.pop(key, None)
    
                                                                             
                                                         
    if not (stored_messages := request.session.get('_messages')):
        request.session.modified = True
        return
    
                                                                                       
    filtered_messages = []
    seen_message_texts = set()
    
    for msg in stored_messages:
                                                                                           
        if isinstance(msg, dict):
            message_text = str(msg.get('message', ''))
        else:
                                                    
            message_text = str(msg)
        
                                                                                        
        message_lower = message_text.lower()
        if any(phrase in message_lower for phrase in [
            "cadastro finalizado com sucesso",
            "cadastro finalizado",
            "cliente 'teste_principal'"
        ]):
            continue
        
                                                      
        if message_text not in seen_message_texts:
            seen_message_texts.add(message_text)
            filtered_messages.append(msg)
    
                                                   
    if filtered_messages:
        request.session['_messages'] = filtered_messages
    else:
        request.session.pop('_messages', None)
    
    request.session.modified = True


def _limpar_mensagens_cadastro_finalizado_storage(request):
                                                                            
                                                                     
    if stored_messages := request.session.get('_messages'):
        filtered_session_messages = []
        for msg in stored_messages:
            if isinstance(msg, dict):
                message_text = str(msg.get('message', ''))
            else:
                message_text = str(msg)
            message_lower = message_text.lower()
                                                               
            phrases_to_remove = [
                "cadastro finalizado com sucesso",
                "cadastro finalizado",
                "cliente 'teste_principal'"
            ]
            if all(phrase not in message_lower for phrase in phrases_to_remove):
                filtered_session_messages.append(msg)
        
        if filtered_session_messages:
            request.session['_messages'] = filtered_session_messages
        else:
            request.session.pop('_messages', None)
        request.session.modified = True
    
                                                                     
    storage = messages.get_messages(request)
    filtered_messages_list = []
    seen_texts = set()
    
    for message in storage:
        message_text = str(message)
        message_lower = message_text.lower()
                                                         
        if any(phrase in message_lower for phrase in [
            "cadastro finalizado com sucesso",
            "cadastro finalizado",
            "cliente 'teste_principal'"
        ]):
            continue
                                                      
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered_messages_list.append(message)
    
                                               
    storage.used = True
    
                                                
    for message in filtered_messages_list:
        messages.add_message(request, message.level, message.message, extra_tags=message.extra_tags)


def _preparar_formulario_com_clientes(request, form, clientes_ids_str):
                                                             
    if not clientes_ids_str:
        return form
    
    clientes_ids_list, _ = _preparar_clientes_pre_selecionados(clientes_ids_str)
    if clientes_ids_list:
        clientes = ClienteConsultoria.objects.filter(pk__in=clientes_ids_list)
        if clientes.exists():
            form.fields["clientes"].initial = [c.pk for c in clientes]
    
    return form


def _obter_clientes_e_membros_viagem(request):
                                                              
    if request.method == "GET" and (clientes_ids := request.GET.get("clientes", "")):
        return _preparar_clientes_pre_selecionados(clientes_ids)
    return [], []


def _processar_post_criar_viagem(request, form):
                                                             
    if not form.is_valid():
        messages.error(request, "Não foi possível cadastrar a viagem. Verifique os campos.")
        return None
    
                              
    acao = request.POST.get("acao", "salvar")
    
                                                
    keys_to_remove = [key for key in request.session.keys() if key.startswith('viagem_cadastrada_')]
    for key in keys_to_remove:
        request.session.pop(key, None)
    request.session.modified = True
    
    viagem = form.save()
    
                                                                                              
                                                     
    clientes_selecionados = form.cleaned_data.get("clientes", [])
    membros_com_visto_diferente = _processar_tipos_visto_individuals(viagem, clientes_selecionados, [], request)
    
                                                                                            
    viagens_separadas = _processar_viagens_separadas(viagem, membros_com_visto_diferente, request)
    
                                                                                     
    if stored_messages := request.session.get('_messages'):
        filtered = [msg for msg in stored_messages if "Viagem cadastrada" not in str(msg.get('message', '') if isinstance(msg, dict) else msg)]
        request.session['_messages'] = filtered or None
        if not filtered:
            request.session.pop('_messages', None)
        request.session.modified = True
    
                                                                         
    storage = messages.get_messages(request)
    storage.used = True
    
                                                             
    total_viagens = 1 + len(viagens_separadas) if viagens_separadas else 1
    
                                                                                                         
                                                                   
    if acao == "salvar_e_criar_processo":
                                                                
                                                                       
        todas_viagens_ids = [viagem.pk]
        if viagens_separadas:
            todas_viagens_ids.extend([v.pk for v in viagens_separadas])
        
                                                                              
        todos_clientes_ids = set(viagem.clientes.all().values_list('pk', flat=True))
        for viagem_sep in viagens_separadas:
            todos_clientes_ids.update(viagem_sep.clientes.all().values_list('pk', flat=True))
        
        if todos_clientes_ids:
            for cliente_obj in ClienteConsultoria.objects.filter(pk__in=list(todos_clientes_ids)):
                if cliente_obj.is_principal:
                    todos_clientes_ids.update(
                        ClienteConsultoria.objects.filter(cliente_principal=cliente_obj).values_list('pk', flat=True)
                    )
                elif cliente_obj.cliente_principal_id:
                    todos_clientes_ids.add(cliente_obj.cliente_principal_id)
                    todos_clientes_ids.update(
                        ClienteConsultoria.objects.filter(cliente_principal_id=cliente_obj.cliente_principal_id).values_list('pk', flat=True)
                    )
        
                                                                     
        if len(todos_clientes_ids) == 1:
            cliente_id = list(todos_clientes_ids)[0]
                                                     
            cliente_obj = ClienteConsultoria.objects.get(pk=cliente_id)
            viagem_cliente = None
            if cliente_obj in viagem.clientes.all():
                viagem_cliente = viagem
            else:
                for viagem_sep in viagens_separadas:
                    if cliente_obj in viagem_sep.clientes.all():
                        viagem_cliente = viagem_sep
                        break
            
            if viagem_cliente:
                return redirect(f"{reverse('system:criar_processo')}?cliente_id={cliente_id}&viagem_id={viagem_cliente.pk}")
        
                                                                                
                                                               
        return redirect(f"{reverse('system:criar_processo')}?viagem_id={viagem.pk}")
    
                                                                      
    if total_viagens > 1:
        messages.success(request, f"{total_viagens} viagens cadastradas com sucesso.")
    else:
        messages.success(request, "Viagem cadastrada com sucesso.")
    
    return redirect("system:home_viagens")


def _preparar_clientes_pre_selecionados(clientes_ids_str):
                                                                        
    clientes_ids_list = []
    with suppress(ValueError, TypeError):
        clientes_ids_list = [int(id.strip()) for id in clientes_ids_str.split(",") if id.strip()]
    
    if not clientes_ids_list:
        return [], []
    
    membros_viagem = _organizar_membros_viagem(clientes_ids_list)
    return list(clientes_ids_list), membros_viagem


def _preparar_contexto_criar_viagem(form, consultor, clientes_pre_selecionados, membros_viagem):
                                                             
    tipos_visto_disponiveis = TipoVisto.objects.filter(ativo=True).select_related("pais_destino").order_by("pais_destino__nome", "nome")
    
    return {
        "form": form,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "clientes_pre_selecionados": clientes_pre_selecionados,
        "membros_viagem": membros_viagem,
        "tipos_visto_disponiveis": tipos_visto_disponiveis,
    }


@login_required
def criar_viagem(request):
                                                
    consultor = obter_consultor_usuario(request.user)
    
                                                                                        
    if request.method == "GET" and request.GET.get("clientes"):
        _limpar_flags_cadastro_cliente(request)
        request.session.save()
        _limpar_flags_cadastro_cliente(request)
        _limpar_mensagens_cadastro_finalizado_storage(request)

    if request.method == "POST":
        form = ViagemForm(data=request.POST, user=request.user)
        if redirect_response := _processar_post_criar_viagem(request, form):
            return redirect_response
    else:
        form = ViagemForm(user=request.user)
        if clientes_ids := request.GET.get("clientes", ""):
            form = _preparar_formulario_com_clientes(request, form, clientes_ids)

                                                         
    clientes_pre_selecionados, membros_viagem = _obter_clientes_e_membros_viagem(request)
    
                                                                                      
                                                             
    if request.method == "GET" and request.GET.get("clientes"):
        for _ in range(3):                                  
            _limpar_flags_cadastro_cliente(request)
            _limpar_mensagens_cadastro_finalizado_storage(request)
                                                                        
            if stored_messages := request.session.get('_messages'):
                phrases_to_remove = ["cadastro finalizado com sucesso", "cadastro finalizado", "cliente 'teste_principal'"]
                filtered = [
                    msg for msg in stored_messages
                    if all(phrase not in str(msg.get('message', '') if isinstance(msg, dict) else msg).lower()
                          for phrase in phrases_to_remove)
                ]
                if filtered:
                    request.session['_messages'] = filtered
                else:
                    request.session.pop('_messages', None)
                request.session.modified = True
            request.session.save()
    
    contexto = _preparar_contexto_criar_viagem(form, consultor, clientes_pre_selecionados, membros_viagem)
    return render(request, "travel/criar_viagem.html", contexto)


@login_required
def listar_paises_destino(request):
                                           
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    paises = PaisDestino.objects.all().order_by("nome")
    paises, filtros_aplicados = _aplicar_filtros_paises_destino(paises, request)
    
    contexto = {
        "paises": paises,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
    }
    
    return render(request, "travel/listar_paises_destino.html", contexto)


def _limpar_mensagens_duplicadas_sessao(request):
                                                
    if not (stored_messages := request.session.get('_messages')):
        return
    
    filtered = []
    seen_texts = set()
    for msg in stored_messages:
        message_text = str(msg.get('message', '') if isinstance(msg, dict) else msg)
        if message_text not in seen_texts:
            seen_texts.add(message_text)
            filtered.append(msg)
    
    if filtered:
        request.session['_messages'] = filtered
    else:
        request.session.pop('_messages', None)
    request.session.modified = True
    
                                          
    storage = messages.get_messages(request)
    storage.used = True


@login_required
def editar_pais_destino(request, pk: int):
                                                           
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    pais = get_object_or_404(PaisDestino, pk=pk)
    
    if request.method == "POST":
                                                        
        _limpar_mensagens_duplicadas_sessao(request)
        
        form = PaisDestinoForm(data=request.POST, instance=pais)
        if form.is_valid():
            pais_atualizado = form.save()
            messages.success(request, f"País {pais_atualizado.nome} atualizado com sucesso.")
            return redirect("system:listar_paises_destino")
        else:
                                        
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{form.fields[field].label}: {error}")
    else:
        form = PaisDestinoForm(instance=pais)
    
    contexto = {
        "form": form,
        "pais": pais,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_pais_destino.html", contexto)


@login_required
def visualizar_pais_destino(request, pk: int):
                                                            
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    pais = get_object_or_404(
        PaisDestino.objects.select_related("criado_por"),
        pk=pk
    )
    
                                      
    tipos_visto = TipoVisto.objects.filter(
        pais_destino=pais
    ).select_related("pais_destino").prefetch_related("formulario").order_by("nome")
    
                               
    viagens = Viagem.objects.filter(
        pais_destino=pais
    ).select_related(
        "tipo_visto",
        "assessor_responsavel",
        "pais_destino"
    ).prefetch_related("clientes").order_by("-data_prevista_viagem")
    
    contexto = {
        "pais": pais,
        "tipos_visto": tipos_visto,
        "viagens": viagens,
        "total_tipos_visto": tipos_visto.count(),
        "total_viagens": viagens.count(),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "pode_editar": pode_gerenciar_todos,
    }
    
    return render(request, "travel/visualizar_pais_destino.html", contexto)


@login_required
def verificar_exclusao_pais_destino(request, pk: int):
                                                                            
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    pais = get_object_or_404(PaisDestino, pk=pk)
    
                                 
    viagens = Viagem.objects.filter(pais_destino=pais).select_related(
        "tipo_visto",
        "assessor_responsavel"
    ).prefetch_related("clientes").order_by("-data_prevista_viagem")
    
    tipos_visto = TipoVisto.objects.filter(pais_destino=pais).select_related(
        "pais_destino"
    ).order_by("nome")
    
                                                         
    from system.models import ClienteViagem
    clientes_viagem = ClienteViagem.objects.filter(
        viagem__pais_destino=pais
    ).select_related("cliente", "viagem", "tipo_visto").order_by("-viagem__data_prevista_viagem")
    
    contexto = {
        "pais": pais,
        "viagens": viagens,
        "tipos_visto": tipos_visto,
        "clientes_viagem": clientes_viagem,
        "total_viagens": viagens.count(),
        "total_tipos_visto": tipos_visto.count(),
        "total_clientes_viagem": clientes_viagem.count(),
        "pode_excluir": viagens.count() == 0,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/verificar_exclusao_pais_destino.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_pais_destino(request, pk: int):
                                    
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
                                                         
    _limpar_mensagens_duplicadas_sessao(request)
    
    pais = get_object_or_404(PaisDestino, pk=pk)
    
                                        
    viagens = Viagem.objects.filter(pais_destino=pais)
    if viagens.exists():
        messages.error(
            request,
            f"Não é possível excluir o país {pais.nome} pois existem {viagens.count()} viagem(ns) vinculada(s). "
            f"Exclua as viagens primeiro."
        )
        return redirect("system:verificar_exclusao_pais_destino", pk=pk)
    
    nome_pais = pais.nome
    pais.delete()
    
    messages.success(request, f"País {nome_pais} excluído com sucesso.")
    return redirect("system:listar_paises_destino")


@login_required
def listar_tipos_visto(request):
                                        
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    tipos_visto = TipoVisto.objects.select_related("pais_destino").order_by("pais_destino__nome", "nome")
    tipos_visto, filtros_aplicados = _aplicar_filtros_tipos_visto(tipos_visto, request)
    
    contexto = {
        "tipos_visto": tipos_visto,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "filtros_aplicados": filtros_aplicados,
        "paises": PaisDestino.objects.filter(ativo=True).order_by("nome"),
    }
    
    return render(request, "travel/listar_tipos_visto.html", contexto)


@login_required
def visualizar_tipo_visto(request, pk: int):
                                                          
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    tipo_visto = get_object_or_404(
        TipoVisto.objects.select_related(
            "pais_destino",
            "criado_por"
        ),
        pk=pk
    )
    
                                              
    from system.models import FormularioVisto
    formulario = None
    try:
        formulario = FormularioVisto.objects.select_related("tipo_visto").prefetch_related(
            "perguntas"
        ).get(tipo_visto=tipo_visto)
    except FormularioVisto.DoesNotExist:
        messages.info(request, "Nenhum formulário disponível para este tipo de visto.")
    
                               
    viagens = Viagem.objects.filter(
        tipo_visto=tipo_visto
    ).select_related(
        "pais_destino",
        "assessor_responsavel",
        "tipo_visto"
    ).prefetch_related("clientes").order_by("-data_prevista_viagem")
    
    contexto = {
        "tipo_visto": tipo_visto,
        "formulario": formulario,
        "viagens": viagens,
        "total_viagens": viagens.count(),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "pode_editar": pode_gerenciar_todos,
    }
    
    return render(request, "travel/visualizar_tipo_visto.html", contexto)


@login_required
def editar_tipo_visto(request, pk: int):
                                                         
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    tipo_visto = get_object_or_404(TipoVisto.objects.select_related("pais_destino"), pk=pk)
    
    if request.method == "POST":
        form = TipoVistoForm(data=request.POST, instance=tipo_visto)
        if form.is_valid():
            form.save()
            messages.success(request, f"Tipo de visto {form.cleaned_data['nome']} atualizado com sucesso.")
            return redirect("system:listar_tipos_visto")
        messages.error(request, "Não foi possível atualizar o tipo de visto. Verifique os campos.")
    else:
        form = TipoVistoForm(instance=tipo_visto)
                                                                           
        if tipo_visto.pais_destino:
            form.fields["pais_destino"].initial = tipo_visto.pais_destino.pk
    
    contexto = {
        "form": form,
        "tipo_visto": tipo_visto,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_tipo_visto.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_tipo_visto(request, pk: int):
                                  
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    if not pode_gerenciar_todos:
        raise PermissionDenied
    
    tipo_visto = get_object_or_404(TipoVisto, pk=pk)
    nome_tipo = tipo_visto.nome
    tipo_visto.delete()
    
    messages.success(request, f"Tipo de visto {nome_tipo} excluído com sucesso.")
    return redirect("system:listar_tipos_visto")


def _aplicar_filtros_viagens(viagens, request, filtros_aplicados, incluir_assessor=True):
                                                               
                                     
    if incluir_assessor and (assessor_id := request.GET.get("assessor")):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(assessor_responsavel_id=int(assessor_id))
            filtros_aplicados["assessor"] = int(assessor_id)
    
                                
    if pais_id := request.GET.get("pais"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(pais_destino_id=int(pais_id))
            filtros_aplicados["pais"] = int(pais_id)
    
                              
    if tipo_visto_id := request.GET.get("tipo_visto"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(tipo_visto_id=int(tipo_visto_id))
            filtros_aplicados["tipo_visto"] = int(tipo_visto_id)
    
                                                
    if data_viagem_inicio := request.GET.get("data_viagem_inicio"):
        with suppress(ValueError, TypeError):
            data_inicio = datetime.strptime(data_viagem_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_viagem__gte=data_inicio)
            filtros_aplicados["data_viagem_inicio"] = data_viagem_inicio
    if data_viagem_fim := request.GET.get("data_viagem_fim"):
        with suppress(ValueError, TypeError):
            data_fim = datetime.strptime(data_viagem_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_viagem__lte=data_fim)
            filtros_aplicados["data_viagem_fim"] = data_viagem_fim
    
                                                 
    if data_retorno_inicio := request.GET.get("data_retorno_inicio"):
        with suppress(ValueError, TypeError):
            data_inicio = datetime.strptime(data_retorno_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_retorno__gte=data_inicio)
            filtros_aplicados["data_retorno_inicio"] = data_retorno_inicio
    if data_retorno_fim := request.GET.get("data_retorno_fim"):
        with suppress(ValueError, TypeError):
            data_fim = datetime.strptime(data_retorno_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(data_prevista_retorno__lte=data_fim)
            filtros_aplicados["data_retorno_fim"] = data_retorno_fim
    
                                         
    if valor_min := request.GET.get("valor_min"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(valor_assessoria__gte=float(valor_min))
            filtros_aplicados["valor_min"] = valor_min
    if valor_max := request.GET.get("valor_max"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(valor_assessoria__lte=float(valor_max))
            filtros_aplicados["valor_max"] = valor_max
    
                                  
    if cliente_id := request.GET.get("cliente"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(clientes__id=int(cliente_id)).distinct()
            filtros_aplicados["cliente"] = int(cliente_id)
    
                                                          
    if parceiro_id := request.GET.get("parceiro"):
        with suppress(ValueError, TypeError):
            viagens = viagens.filter(clientes__parceiro_indicador_id=int(parceiro_id)).distinct()
            filtros_aplicados["parceiro"] = int(parceiro_id)
    
                                        
    if data_criacao_inicio := request.GET.get("data_criacao_inicio"):
        with suppress(ValueError, TypeError):
            data_inicio = datetime.strptime(data_criacao_inicio, "%Y-%m-%d").date()
            viagens = viagens.filter(criado_em__date__gte=data_inicio)
            filtros_aplicados["data_criacao_inicio"] = data_criacao_inicio
    if data_criacao_fim := request.GET.get("data_criacao_fim"):
        with suppress(ValueError, TypeError):
            data_fim = datetime.strptime(data_criacao_fim, "%Y-%m-%d").date()
            viagens = viagens.filter(criado_em__date__lte=data_fim)
            filtros_aplicados["data_criacao_fim"] = data_criacao_fim
    
    return viagens


def _montar_kpis_viagens(viagens):
    viagens_ids = list(viagens.values_list("pk", flat=True).distinct())
    base = Viagem.objects.filter(pk__in=viagens_ids)
    hoje = date.today()
    proximidade_fim = hoje + timedelta(days=30)

    total_viagens = base.count()
    total_viagens_concluidas = base.filter(data_prevista_retorno__lt=hoje).count()
    total_viagens_proximas = base.filter(
        data_prevista_viagem__gte=hoje,
        data_prevista_viagem__lte=proximidade_fim,
    ).count()

    qtd_por_tipo_visto = list(
        base.values("tipo_visto__nome").annotate(total=Count("pk")).order_by("-total", "tipo_visto__nome")
    )
    qtd_por_pais = list(
        base.values("pais_destino__nome").annotate(total=Count("pk")).order_by("-total", "pais_destino__nome")
    )

    return {
        "total_viagens_kpi": total_viagens,
        "total_viagens_concluidas": total_viagens_concluidas,
        "total_viagens_proximas": total_viagens_proximas,
        "quantidade_por_tipo_visto": qtd_por_tipo_visto,
        "quantidade_por_pais": qtd_por_pais,
    }


def _preparar_info_viagens(viagens, pode_gerenciar_todos, consultor):
                                                                              
    viagens_com_info = []
    for viagem in viagens:
                                                         
        formulario = _obter_formulario_por_tipo_visto(viagem.tipo_visto, apenas_ativo=True)
        tem_formulario = formulario is not None
        total_clientes = viagem.clientes.count()
        clientes_com_resposta = 0
        
        if formulario and total_clientes > 0:
            clientes_com_resposta = RespostaFormulario.objects.filter(
                viagem=viagem
            ).values_list("cliente_id", flat=True).distinct().count()
        
                                                      
        total_processos = Processo.objects.filter(viagem=viagem).count()
        clientes_sem_processo = total_clientes - total_processos if total_clientes > 0 else 0
        
        parceiros_vinculados = {cliente.parceiro_indicador for cliente in viagem.clientes.all() if cliente.parceiro_indicador}
        pode_editar_excluir = pode_gerenciar_todos or (consultor and viagem.assessor_responsavel_id == consultor.pk)
        
        viagens_com_info.append({
            "viagem": viagem,
            "tem_formulario": tem_formulario,
            "total_clientes": total_clientes,
            "clientes_com_resposta": clientes_com_resposta,
            "clientes_sem_resposta": total_clientes - clientes_com_resposta if tem_formulario else 0,
            "total_processos": total_processos,
            "clientes_sem_processo": clientes_sem_processo,
            "pode_editar_excluir": pode_editar_excluir,
            "parceiros_vinculados": list(parceiros_vinculados),
        })
    
    return viagens_com_info


def _build_pergunta_estado(perguntas, post_dict, respostas_existentes):
    estado = {}
    for p in perguntas:
        if p.tipo_campo == "booleano":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if val == "sim":
                estado[p.ordem] = "sim"
            elif val == "nao":
                estado[p.ordem] = "nao"
            elif p.pk in respostas_existentes:
                r = respostas_existentes[p.pk]
                if r.resposta_booleano is True:
                    estado[p.ordem] = "sim"
                elif r.resposta_booleano is False:
                    estado[p.ordem] = "nao"
        elif p.tipo_campo == "selecao":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if val:
                try:
                    opcao_id = int(val)
                    opcao = OpcaoSelecao.objects.filter(pk=opcao_id, pergunta=p).first()
                    estado[p.ordem] = opcao.texto if opcao else val
                except ValueError:
                    estado[p.ordem] = val
            elif p.pk in respostas_existentes:
                r = respostas_existentes[p.pk]
                if r.resposta_selecao_id:
                    estado[p.ordem] = r.resposta_selecao.texto
        elif p.tipo_campo == "numero":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            estado[p.ordem] = val
        elif p.tipo_campo == "data":
            val = post_dict.get(f"pergunta_{p.pk}", "")
            estado[p.ordem] = val
        else:
            val = post_dict.get(f"pergunta_{p.pk}", "")
            if not val and p.pk in respostas_existentes:
                val = respostas_existentes[p.pk].resposta_texto or ""
            estado[p.ordem] = val
    return estado


def _pergunta_e_visivel(pergunta, estado):
    regra = pergunta.regra_exibicao
    if not regra:
        return True
    tipo = regra.get("tipo")
    if tipo != "mostrar_se":
        return True
    pergunta_ordem = regra.get("pergunta_ordem")
    valores_esperados = regra.get("valor")
    if pergunta_ordem is None or valores_esperados is None:
        return True
    if isinstance(valores_esperados, list):
        return estado.get(pergunta_ordem) in valores_esperados
    return estado.get(pergunta_ordem) == valores_esperados


def _processar_respostas_formulario(request, viagem, cliente, perguntas, respostas_existentes=None):
                                                                 
    respostas_salvas = 0
    erros = []
    respostas_existentes = respostas_existentes or {}
    estado = _build_pergunta_estado(perguntas, request.POST, respostas_existentes)
    
    for pergunta in perguntas:
        campo_name = f"pergunta_{pergunta.pk}"
        valor = request.POST.get(campo_name)
        
        if pergunta.obrigatorio and not valor and _pergunta_e_visivel(pergunta, estado):
            erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
            continue

        
        if pergunta.obrigatorio and not valor:
            erros.append(f"A pergunta '{pergunta.pergunta}' é obrigatória.")
            continue
        
        resposta, _ = RespostaFormulario.objects.get_or_create(
            viagem=viagem,
            cliente=cliente,
            pergunta=pergunta,
            defaults={},
        )
        
        if pergunta.tipo_campo == "numero" and valor:
            try:
                Decimal(valor)
            except (InvalidOperation, ValueError):
                erros.append(f"Valor inválido para a pergunta '{pergunta.pergunta}'.")
                continue
        elif pergunta.tipo_campo == "selecao" and valor:
            try:
                opcao_id = int(valor)
                OpcaoSelecao.objects.get(pk=opcao_id, pergunta=pergunta)
            except (ValueError, OpcaoSelecao.DoesNotExist):
                erros.append(f"Opção inválida para a pergunta '{pergunta.pergunta}'.")
                continue
        
        _atualizar_resposta_formulario(resposta, pergunta, valor)
        resposta.save()
        respostas_salvas += 1
    
    return respostas_salvas, erros


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
        else:
            return FormularioVisto.objects.select_related('tipo_visto').get(
                tipo_visto_id=tipo_visto.pk
            )
    except FormularioVisto.DoesNotExist:
        return None


def _obter_dados_formulario(viagem, cliente, stage_token=None):
    tipo_visto = _obter_tipo_visto_cliente(viagem, cliente)
    
    if not tipo_visto:
        return None, None, None, None, None, None
    
    formulario = _obter_formulario_por_tipo_visto(tipo_visto, apenas_ativo=True)
    
    if not formulario:
        return None, None, None, None, None, None
    
    perguntas = (
        formulario.perguntas.filter(ativo=True)
        .prefetch_related("opcoes")
        .order_by("ordem", "pergunta")
    )
    
    respostas_list = RespostaFormulario.objects.filter(
        viagem=viagem, cliente=cliente
    ).select_related("resposta_selecao")
    
    respostas_existentes = {r.pergunta_id: r for r in respostas_list}

    prefill_form_answers(viagem, cliente, perguntas, respostas_existentes)

    stage_items = build_stage_items(formulario)
    current_stage = resolve_stage_token(stage_items, stage_token)
    stage_perguntas = filter_questions_by_stage(perguntas, current_stage)

    return formulario, perguntas, respostas_existentes, stage_items, current_stage, list(stage_perguntas)


def _atualizar_resposta_formulario(resposta, pergunta, valor):
                                                                                   
                                     
    resposta.resposta_texto = ""
    resposta.resposta_data = None
    resposta.resposta_numero = None
    resposta.resposta_booleano = None
    resposta.resposta_selecao = None
    
                                                  
    if pergunta.tipo_campo == "texto":
        resposta.resposta_texto = valor or ""
    elif pergunta.tipo_campo == "data":
        resposta.resposta_data = parse_date(valor) if valor else None
    elif pergunta.tipo_campo == "numero":
        resposta.resposta_numero = Decimal(valor) if valor else None
    elif pergunta.tipo_campo == "booleano":
        resposta.resposta_booleano = valor == "sim" if valor else None
    elif pergunta.tipo_campo == "selecao" and valor:
        opcao_id = int(valor)
        resposta.resposta_selecao = OpcaoSelecao.objects.get(pk=opcao_id, pergunta=pergunta)


@login_required
def listar_viagens(request):
                                             
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
                                                       
    viagens = Viagem.objects.select_related(
        "pais_destino",
        "tipo_visto__formulario",
        "assessor_responsavel",
    ).prefetch_related("clientes", "clientes__parceiro_indicador").order_by("-data_prevista_viagem")
    
                     
    filtros_aplicados = {}
    viagens = _aplicar_filtros_viagens(viagens, request, filtros_aplicados)
    kpis = _montar_kpis_viagens(viagens)
    
                                      
    viagens_com_info = _preparar_info_viagens(viagens, pode_gerenciar_todos, consultor)
    
                                   
    assessores = UsuarioConsultoria.objects.filter(ativo=True).order_by("nome")
    paises = PaisDestino.objects.filter(ativo=True).order_by("nome")
    tipos_visto = TipoVisto.objects.filter(ativo=True).select_related("pais_destino").order_by("pais_destino__nome", "nome")
    clientes = ClienteConsultoria.objects.order_by("nome")
    parceiros = Partner.objects.filter(ativo=True).order_by("nome_empresa", "nome_responsavel")
    
    contexto = {
        "viagens_com_info": viagens_com_info,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "eh_administrador": pode_gerenciar_todos,
        "assessores": assessores,
        "paises": paises,
        "tipos_visto": tipos_visto,
        "clientes": clientes,
        "parceiros": parceiros,
        "filtros_aplicados": filtros_aplicados,
        **kpis,
    }
    
    return render(request, "travel/listar_viagens.html", contexto)


@login_required
def visualizar_viagem(request, pk: int):
                                                                                   
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related(
            "pais_destino",
            "tipo_visto",
            "tipo_visto__formulario",
            "assessor_responsavel",
        ).prefetch_related("clientes", "clientes__cliente_principal"),
        pk=pk
    )
    
                                                          
                                                             
    
                                                                                   
    clientes = viagem.clientes.all().select_related("cliente_principal", "assessor_responsavel").order_by("cliente_principal", "nome")
    
                                 
    processos = Processo.objects.filter(
        viagem=viagem
    ).select_related(
        "cliente",
        "assessor_responsavel",
    ).prefetch_related("etapas", "etapas__status").order_by("-criado_em")
    
                                                     
    clientes_com_info = []
    for cliente in clientes:
        tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
        formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=False)
        
        tem_resposta = False
        total_perguntas = 0
        total_respostas = 0
        
        if formulario and formulario.ativo:
            perguntas = formulario.perguntas.filter(ativo=True)
            total_perguntas = perguntas.count()
            if total_perguntas > 0:
                respostas = RespostaFormulario.objects.filter(
                    viagem=viagem,
                    cliente=cliente
                )
                total_respostas = respostas.count()
                tem_resposta = total_respostas > 0
        
        clientes_com_info.append({
            "cliente": cliente,
            "tipo_visto": tipo_visto_cliente,
            "formulario": formulario,
            "tem_resposta": tem_resposta,
            "total_perguntas": total_perguntas,
            "total_respostas": total_respostas,
            "completo": tem_resposta and total_respostas == total_perguntas if total_perguntas > 0 else False,
        })
    
                                            
    registros_financeiros = Financeiro.objects.filter(
        viagem=viagem
    ).select_related(
        "cliente",
        "assessor_responsavel",
    ).order_by("-criado_em")
    
    pode_editar = pode_gerenciar_todos or (consultor and viagem.assessor_responsavel_id == consultor.pk)
    
    contexto = {
        "viagem": viagem,
        "clientes_com_info": clientes_com_info,
        "processos": processos,
        "registros_financeiros": registros_financeiros,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "pode_editar": pode_editar,
    }
    
    return render(request, "travel/visualizar_viagem.html", contexto)


@login_required
def editar_viagem(request, pk: int):
                                                  
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("pais_destino", "tipo_visto", "assessor_responsavel"),
        pk=pk
    )
    
                                                                                            
    if not pode_gerenciar_todos and (not consultor or viagem.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para editar esta viagem.")
    
    if request.method == "POST":
        form = ViagemForm(data=request.POST, user=request.user, instance=viagem)
        if form.is_valid():
            form.save()
            messages.success(request, "Viagem atualizada com sucesso.")
            return redirect("system:listar_viagens")
        messages.error(request, "Não foi possível atualizar a viagem. Verifique os campos.")
    else:
        form = ViagemForm(user=request.user, instance=viagem)
    
    contexto = {
        "form": form,
        "viagem": viagem,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
    }
    
    return render(request, "travel/editar_viagem.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_viagem(request, pk: int):
                            
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("assessor_responsavel"),
        pk=pk
    )
    
                                                                                             
    if not pode_gerenciar_todos and (not consultor or viagem.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para excluir esta viagem.")
    
    pais_destino = viagem.pais_destino.nome
    data_viagem = viagem.data_prevista_viagem.strftime("%d/%m/%Y")
    viagem.delete()
    
    messages.success(request, f"Viagem para {pais_destino} ({data_viagem}) excluída com sucesso.")
    return redirect("system:listar_viagens")


@login_required
@require_GET
def api_tipos_visto(request):
                                                           
    pais_id = request.GET.get("pais", "").strip()

    if not pais_id:
        return JsonResponse({"error": "Informe um país."}, status=400)

    with suppress(ValueError, TypeError):
        tipos_visto = TipoVisto.objects.filter(
            pais_destino_id=int(pais_id),
            ativo=True
        ).order_by("nome")

        data = [{"id": tipo.id, "nome": tipo.nome} for tipo in tipos_visto]
        return JsonResponse(data, safe=False)
    return JsonResponse({"error": "País inválido."}, status=400)


@login_required
def listar_formularios_viagem(request, viagem_id: int):
                                                                     
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("pais_destino", "tipo_visto__formulario", "assessor_responsavel"),
        pk=viagem_id
    )
    
                                                                        
                                                             
    
                                                                                                       
    clientes_com_info = []
    for cliente in viagem.clientes.all():
                                                  
        tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)
        
                                                         
        formulario = _obter_formulario_por_tipo_visto(tipo_visto_cliente, apenas_ativo=False)
        
        tem_resposta = False
        total_perguntas = 0
        total_respostas = 0
        
        if formulario and formulario.ativo:
            perguntas = formulario.perguntas.filter(ativo=True)
            total_perguntas = perguntas.count()
            if total_perguntas > 0:
                respostas = RespostaFormulario.objects.filter(
                    viagem=viagem,
                    cliente=cliente
                )
                total_respostas = respostas.count()
                tem_resposta = total_respostas > 0
        
        clientes_com_info.append({
            "cliente": cliente,
            "tipo_visto": tipo_visto_cliente,
            "formulario": formulario,
            "tem_resposta": tem_resposta,
            "total_perguntas": total_perguntas,
            "total_respostas": total_respostas,
            "completo": tem_resposta and total_respostas == total_perguntas if total_perguntas > 0 else False,
        })
    
    contexto = {
        "viagem": viagem,
        "clientes_com_info": clientes_com_info,
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
    }
    
    return render(request, "travel/listar_formularios_viagem.html", contexto)


@login_required
def editar_formulario_cliente(request, viagem_id: int, cliente_id: int):
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario"),
        pk=viagem_id
    )
    
    if not pode_gerenciar_todos and (not consultor or viagem.assessor_responsavel_id != consultor.pk):
        raise PermissionDenied("Você não tem permissão para acessar esta viagem.")
    
    cliente = get_object_or_404(ClienteConsultoria, pk=cliente_id)
    
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")
    
    stage_token = request.GET.get("etapa")
    formulario, all_perguntas, respostas_existentes, stage_items, current_stage, perguntas = _obter_dados_formulario(viagem, cliente, stage_token)
    
    if not formulario:
        messages.warning(
            request,
            "Este tipo de visto não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
    
    if request.method == "POST":
        respostas_salvas, erros = _processar_respostas_formulario(request, viagem, cliente, perguntas, respostas_existentes)
        
        if erros:
            for erro in erros:
                messages.error(request, erro)
        else:
            messages.success(
                request,
                f"Etapa '{current_stage['nome'] if current_stage else 'Atual'}' salva com sucesso!",
            )
            next_action = request.POST.get("next_action")
            if next_action == "next" and current_stage:
                next_stage = None
                for i, item in enumerate(stage_items):
                    if item["token"] == current_stage["token"] and i + 1 < len(stage_items):
                        next_stage = stage_items[i + 1]
                        break
                if next_stage:
                    return redirect(f"{reverse('system:editar_formulario_cliente', args=[viagem_id, cliente_id])}?etapa={next_stage['token'].replace(':', '%3A')}")
                return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
            elif next_action == "finish":
                return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
            else:
                stage_param = f"?etapa={current_stage['token'].replace(':', '%3A')}" if current_stage else ""
                return redirect(f"{reverse('system:editar_formulario_cliente', args=[viagem_id, cliente_id])}{stage_param}")
    
    tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)

    stage_index = 0
    if current_stage and stage_items:
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"]:
                stage_index = i
                break

    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None
    
    contexto = {
        "viagem": viagem,
        "cliente": cliente,
        "tipo_visto_cliente": tipo_visto_cliente,
        "formulario": formulario,
        "perguntas": perguntas,
        "all_perguntas": all_perguntas,
        "respostas_existentes": respostas_existentes,
        "respostas_ids": list(respostas_existentes.keys()),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
    }
    
    return render(request, "travel/editar_formulario_cliente.html", contexto)


@login_required
def visualizar_formulario_cliente(request, viagem_id: int, cliente_id: int):
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("tipo_visto__formulario", "pais_destino", "assessor_responsavel"),
        pk=viagem_id
    )
    
    cliente = get_object_or_404(ClienteConsultoria, pk=cliente_id)
    
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")
    
    stage_token = request.GET.get("etapa")
    formulario, all_perguntas, respostas_existentes, stage_items, current_stage, perguntas = _obter_dados_formulario(viagem, cliente, stage_token)
    
    if not formulario:
        messages.warning(
            request,
            "Este tipo de visto não possui um formulário cadastrado ou o formulário está inativo.",
        )
        return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)
    
    tipo_visto_cliente = _obter_tipo_visto_cliente(viagem, cliente)

    stage_index = 0
    if current_stage and stage_items:
        for i, item in enumerate(stage_items):
            if item["token"] == current_stage["token"]:
                stage_index = i
                break

    next_stage = stage_items[stage_index + 1] if stage_index + 1 < len(stage_items) else None
    prev_stage = stage_items[stage_index - 1] if stage_index > 0 else None
    
    contexto = {
        "viagem": viagem,
        "cliente": cliente,
        "tipo_visto_cliente": tipo_visto_cliente,
        "formulario": formulario,
        "perguntas": perguntas,
        "all_perguntas": all_perguntas,
        "respostas_existentes": respostas_existentes,
        "respostas_ids": list(respostas_existentes.keys()),
        "perfil_usuario": consultor.perfil.nome if consultor else None,
        "pode_gerenciar_todos": pode_gerenciar_todos,
        "stage_items": stage_items,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "prev_stage": prev_stage,
        "stage_index": stage_index,
    }
    
    return render(request, "travel/visualizar_formulario_cliente.html", contexto)


@login_required
@require_http_methods(["POST"])
def excluir_respostas_formulario(request, viagem_id: int, cliente_id: int):
                                                                              
    consultor = obter_consultor_usuario(request.user)
    pode_gerenciar_todos = usuario_pode_gerenciar_todos(request.user, consultor)
    
    viagem = get_object_or_404(
        Viagem.objects.select_related("assessor_responsavel"),
        pk=viagem_id
    )
    
                                                                                
    if not pode_gerenciar_todos:
        raise PermissionDenied("Apenas administradores podem excluir respostas de formulários.")
    
    from system.models import ClienteConsultoria
    cliente = get_object_or_404(ClienteConsultoria, pk=cliente_id)
    
                                                    
    if cliente not in viagem.clientes.all():
        raise PermissionDenied("Este cliente não está vinculado a esta viagem.")
    
                                                            
    respostas_deletadas = RespostaFormulario.objects.filter(
        viagem=viagem,
        cliente=cliente
    ).delete()[0]
    
    messages.success(
        request,
        f"Todas as respostas do formulário do cliente {cliente.nome} foram excluídas com sucesso. ({respostas_deletadas} resposta(s) removida(s))"
    )
    
    return redirect("system:listar_formularios_viagem", viagem_id=viagem_id)

