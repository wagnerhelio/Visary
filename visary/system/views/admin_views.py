from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from system.forms import ConsultancyUserForm, ModuleForm, ProfileForm
from system.models import ConsultancyUser, Module, Profile
from system.views.client_views import get_user_consultant, user_can_manage_all


@login_required
def home_admin(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    context = {
        "total_users": ConsultancyUser.objects.count(),
        "total_profiles": Profile.objects.count(),
        "total_modules": Module.objects.count(),
        "active_users": ConsultancyUser.objects.filter(is_active=True).count(),
        "user_profile": consultant.profile.name if consultant else None,
    }
    return render(request, "admin/home_admin.html", context)


@login_required
def list_users(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    users = ConsultancyUser.objects.select_related("profile").order_by("name")
    name_filter = request.GET.get("name", "")
    email_filter = request.GET.get("email", "")
    profile_filter = request.GET.get("profile_obj", "")
    active_filter = request.GET.get("active", "")

    if name_filter:
        users = users.filter(name__icontains=name_filter)
    if email_filter:
        users = users.filter(email__icontains=email_filter)
    if profile_filter:
        users = users.filter(profile_id=profile_filter)
    if active_filter != "":
        users = users.filter(is_active=active_filter == "true")

    context = {
        "users_list": users,
        "profiles": Profile.objects.filter(is_active=True).order_by("name"),
        "user_profile": consultant.profile.name if consultant else None,
        "filters_dict": {"name": name_filter, "email": email_filter, "profile_obj": profile_filter, "active": active_filter},
    }
    return render(request, "admin/usuarios/list_users.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_user(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    if request.method == "POST":
        form = ConsultancyUserForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário criado com sucesso.")
            return redirect("system:list_users")
        messages.error(request, "Não foi possível criar o usuário. Verifique os campos.")
    else:
        form = ConsultancyUserForm()

    context = {"form": form, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/usuarios/create_user.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_user(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    user_obj = get_object_or_404(ConsultancyUser.objects.select_related("profile"), pk=pk)

    if request.method == "POST":
        form = ConsultancyUserForm(data=request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário atualizado com sucesso.")
            return redirect("system:list_users")
        messages.error(request, "Não foi possível atualizar o usuário. Verifique os campos.")
    else:
        form = ConsultancyUserForm(instance=user_obj)

    context = {"form": form, "user_obj": user_obj, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/usuarios/edit_user.html", context)


@login_required
@require_http_methods(["POST"])
def delete_user(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    user_obj = get_object_or_404(ConsultancyUser, pk=pk)
    user_name = user_obj.name
    user_obj.delete()
    messages.success(request, f"Usuário {user_name} excluído com sucesso.")
    return redirect("system:list_users")


@login_required
def list_profiles(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    profiles = Profile.objects.prefetch_related("modules", "users").order_by("name")
    name_filter = request.GET.get("name", "")
    active_filter = request.GET.get("active", "")

    if name_filter:
        profiles = profiles.filter(name__icontains=name_filter)
    if active_filter != "":
        profiles = profiles.filter(is_active=active_filter == "true")

    context = {
        "profiles": profiles,
        "user_profile": consultant.profile.name if consultant else None,
        "filters_dict": {"name": name_filter, "active": active_filter},
    }
    return render(request, "admin/perfis/list_profiles.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_profile(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    if request.method == "POST":
        form = ProfileForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil criado com sucesso.")
            return redirect("system:list_profiles")
        messages.error(request, "Não foi possível criar o perfil. Verifique os campos.")
    else:
        form = ProfileForm()

    context = {"form": form, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/perfis/create_profile.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_profile(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    profile = get_object_or_404(Profile.objects.prefetch_related("modules", "users"), pk=pk)

    if request.method == "POST":
        form = ProfileForm(data=request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Perfil atualizado com sucesso.")
            return redirect("system:list_profiles")
        messages.error(request, "Não foi possível atualizar o perfil. Verifique os campos.")
    else:
        form = ProfileForm(instance=profile)

    context = {"form": form, "profile_obj": profile, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/perfis/edit_profile.html", context)


@login_required
@require_http_methods(["POST"])
def delete_profile(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    profile = get_object_or_404(Profile, pk=pk)
    profile_name = profile.name

    if profile.users.exists():
        messages.error(
            request,
            f"Não é possível excluir o perfil {profile_name} pois existem usuários vinculados a ele.",
        )
        return redirect("system:list_profiles")

    profile.delete()
    messages.success(request, f"Perfil {profile_name} excluído com sucesso.")
    return redirect("system:list_profiles")


@login_required
def list_modules(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    modules = Module.objects.prefetch_related("profiles").order_by("order", "name")
    name_filter = request.GET.get("name", "")
    active_filter = request.GET.get("active", "")

    if name_filter:
        modules = modules.filter(name__icontains=name_filter)
    if active_filter != "":
        modules = modules.filter(is_active=active_filter == "true")

    context = {
        "modules": modules,
        "user_profile": consultant.profile.name if consultant else None,
        "filters_dict": {"name": name_filter, "active": active_filter},
    }
    return render(request, "admin/modulos/list_modules.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def create_module(request):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    if request.method == "POST":
        form = ModuleForm(data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Módulo criado com sucesso.")
            return redirect("system:list_modules")
        messages.error(request, "Não foi possível criar o módulo. Verifique os campos.")
    else:
        form = ModuleForm()

    context = {"form": form, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/modulos/create_module.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def edit_module(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    module = get_object_or_404(Module.objects.prefetch_related("profiles"), pk=pk)

    if request.method == "POST":
        form = ModuleForm(data=request.POST, instance=module)
        if form.is_valid():
            form.save()
            messages.success(request, "Módulo atualizado com sucesso.")
            return redirect("system:list_modules")
        messages.error(request, "Não foi possível atualizar o módulo. Verifique os campos.")
    else:
        form = ModuleForm(instance=module)

    context = {"form": form, "module_obj": module, "user_profile": consultant.profile.name if consultant else None}
    return render(request, "admin/modulos/edit_module.html", context)


@login_required
@require_http_methods(["POST"])
def delete_module(request, pk):
    consultant = get_user_consultant(request.user)
    if not user_can_manage_all(request.user, consultant):
        raise PermissionDenied

    module = get_object_or_404(Module, pk=pk)
    module_name = module.name

    if module.profiles.exists():
        messages.error(
            request,
            f"Não é possível excluir o módulo {module_name} pois existem perfis vinculados a ele.",
        )
        return redirect("system:list_modules")

    module.delete()
    messages.success(request, f"Módulo {module_name} excluído com sucesso.")
    return redirect("system:list_modules")
