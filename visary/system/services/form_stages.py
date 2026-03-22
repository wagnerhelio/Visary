def build_stage_items(formulario):
    etapas = list(formulario.etapas.filter(ativo=True).order_by("ordem", "nome"))
    items = [{"token": f"etapa:{etapa.pk}", "etapa": etapa, "nome": etapa.nome} for etapa in etapas]
    if formulario.perguntas.filter(ativo=True, etapa__isnull=True).exists():
        items.append({"token": "etapa:none", "etapa": None, "nome": "Outras perguntas"})
    return items


def resolve_stage_token(stage_items, token):
    if not stage_items:
        return None
    if token:
        for item in stage_items:
            if item["token"] == token:
                return item
    return stage_items[0]


def filter_questions_by_stage(perguntas, stage_item):
    if not stage_item:
        return perguntas.none()
    etapa = stage_item["etapa"]
    if etapa is None:
        return perguntas.filter(etapa__isnull=True)
    return perguntas.filter(etapa=etapa)
