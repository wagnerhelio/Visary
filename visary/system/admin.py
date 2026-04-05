from django.contrib import admin

from system.models import ConsultancyClient, Module, Profile, ConsultancyUser


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    ordering = ("order", "name")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
        "can_create",
        "can_view",
        "can_update",
        "can_delete",
        "updated_at",
    )
    list_filter = ("is_active", "can_create", "can_view", "can_update", "can_delete")
    search_fields = ("name", "description")
    filter_horizontal = ("modules",)
    ordering = ("name",)


@admin.register(ConsultancyUser)
class ConsultancyUserAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "profile", "is_active", "updated_at")
    list_filter = ("is_active", "profile")
    search_fields = ("name", "email")
    autocomplete_fields = ("profile",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ConsultancyClient)
class ConsultancyClientAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "assigned_advisor",
        "phone",
        "created_at",
    )
    search_fields = ("first_name", "last_name", "email", "phone")
    list_filter = ("assigned_advisor", "created_at")
    readonly_fields = ("created_at", "updated_at")
