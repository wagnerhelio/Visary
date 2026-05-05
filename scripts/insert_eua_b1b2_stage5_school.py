import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "static" / "forms_ini" / "FORMULARIO_EUA_B1_B2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise SystemExit("Invalid seed payload.")

    form_item = payload[0]
    questions = form_item.get("perguntas", [])
    if not isinstance(questions, list):
        raise SystemExit("Invalid perguntas.")

    insert_start = 57
    delta = 9

    for q in questions:
        if not isinstance(q, dict):
            continue
        order = q.get("ordem")
        if isinstance(order, int) and order >= insert_start:
            q["ordem"] = order + delta

        rule = q.get("regra_exibicao")
        if isinstance(rule, dict):
            trigger = rule.get("pergunta_ordem")
            if isinstance(trigger, int) and trigger >= insert_start:
                rule["pergunta_ordem"] = trigger + delta

    stage5_questions = [
        {
            "ordem": 57,
            "pergunta": "Nome da escola",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.1",
        },
        {
            "ordem": 58,
            "pergunta": "Curso que será realizado",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.2",
        },
        {
            "ordem": 59,
            "pergunta": "Endereço da escola",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.3",
        },
        {
            "ordem": 60,
            "pergunta": "Cidade da escola",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.4",
        },
        {
            "ordem": 61,
            "pergunta": "Estado da escola",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.5",
        },
        {
            "ordem": 62,
            "pergunta": "CEP da escola",
            "tipo_campo": "texto",
            "obrigatorio": False,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.6",
        },
        {
            "ordem": 63,
            "pergunta": "Você já possui o documento I-20 ou DS-2019?",
            "tipo_campo": "booleano",
            "obrigatorio": True,
            "ativo": True,
            "etapa": 5,
            "ref_id": "5.7",
        },
        {
            "ordem": 64,
            "pergunta": "Número da SEVIS",
            "tipo_campo": "texto",
            "obrigatorio": True,
            "ativo": True,
            "etapa": 5,
            "regra_exibicao": {
                "tipo": "mostrar_se",
                "pergunta_ordem": 63,
                "valor": ["sim"],
            },
            "ref_id": "5.8",
        },
    ]

    existing_orders = {q.get("ordem") for q in questions if isinstance(q, dict)}
    if any(q["ordem"] in existing_orders for q in stage5_questions):
        raise SystemExit("Order collision detected; aborting.")

    questions.extend(stage5_questions)
    form_item["perguntas"] = sorted(questions, key=lambda q: q.get("ordem", 0))

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inserted etapa 5 and shifted orders >= {insert_start} by +{delta}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

