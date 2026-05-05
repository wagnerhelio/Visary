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

    insert_order = 95
    for q in questions:
        order = q.get("ordem")
        if isinstance(order, int) and order >= insert_order:
            q["ordem"] = order + 1

        rule = q.get("regra_exibicao")
        if isinstance(rule, dict):
            trigger = rule.get("pergunta_ordem")
            if isinstance(trigger, int) and trigger >= insert_order:
                rule["pergunta_ordem"] = trigger + 1

    stage8_question = {
        "ordem": insert_order,
        "pergunta": "Caso haja acompanhantes que já tenham vistos, adicionar o nome completo e relação com você",
        "tipo_campo": "texto",
        "obrigatorio": False,
        "ativo": True,
        "etapa": 8,
        "ref_id": "8.1",
    }

    existing_orders = {q.get("ordem") for q in questions if isinstance(q, dict)}
    if stage8_question["ordem"] in existing_orders:
        raise SystemExit("Order collision detected; aborting.")

    questions.append(stage8_question)
    form_item["perguntas"] = sorted(questions, key=lambda q: q.get("ordem", 0))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inserted etapa 8 at ordem {insert_order} and shifted >= {insert_order} by +1: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

