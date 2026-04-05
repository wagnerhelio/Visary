def build_stage_items(visa_form):
    stages = list(visa_form.stages.filter(is_active=True).order_by("order", "name"))
    items = [{"token": f"stage:{stage.pk}", "stage": stage, "name": stage.name} for stage in stages]
    if visa_form.questions.filter(is_active=True, stage__isnull=True).exists():
        items.append({"token": "stage:none", "stage": None, "name": "Outras perguntas"})
    return items


def resolve_stage_token(stage_items, token):
    if not stage_items:
        return None
    if token:
        for item in stage_items:
            if item["token"] == token:
                return item
    return stage_items[0]


def filter_questions_by_stage(questions, stage_item):
    if not stage_item:
        return questions.none()
    stage = stage_item["stage"]
    if stage is None:
        return questions.filter(stage__isnull=True)
    return questions.filter(stage=stage)
