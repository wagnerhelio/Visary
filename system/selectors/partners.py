from system.models import Partner


def active_partners_ordered():
    return Partner.objects.filter(is_active=True).order_by("company_name", "contact_name")
