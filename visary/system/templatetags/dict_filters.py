   
                                                                           
   

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
                                                                    
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def getattr_filter(obj, attr_name):
                                                                                
    if obj is None:
        return None
    try:
        return getattr(obj, attr_name, None)
    except AttributeError:
        return None


@register.filter
def get_form_field(form, field_name):
                                                                       
    if form is None or not hasattr(form, 'fields'):
        return None
    try:
                                                                            
        if field_name in form.fields:
            return form[field_name]
        return None
    except (KeyError, AttributeError):
        return None

