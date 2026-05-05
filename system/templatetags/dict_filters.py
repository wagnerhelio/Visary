import json

from django import template


register = template.Library()


@register.filter
def get_form_field(form, field_name):
    if form is None:
        return None
    return form[field_name] if field_name in form.fields else None


@register.filter
def getattr_filter(obj, attr_name):
    if obj is None or not attr_name:
        return None
    return getattr(obj, attr_name, None)


@register.filter
def get_item(value, key):
    if value is None:
        return None
    try:
        return value.get(key)
    except AttributeError:
        return None


@register.filter
def json_attr(value):
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False)
