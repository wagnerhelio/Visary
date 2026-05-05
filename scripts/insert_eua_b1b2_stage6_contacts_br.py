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

    insert_start = 65
    delta = 16

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

    stage6_questions = []
    labels = [
        ("Nome", "texto"),
        ("Sobrenome", "texto"),
        ("Endereco", "texto"),
        ("Cidade", "texto"),
        ("Estado/Província", "texto"),
        ("CEP", "texto"),
        ("Telefone", "texto"),
        ("E-mail", "texto"),
    ]

    order = insert_start
    ref_idx = 1
    for contact_no in (1, 2):
        for label, field_type in labels:
            stage6_questions.append(
                {
                    "ordem": order,
                    "pergunta": label,
                    "tipo_campo": field_type,
                    "obrigatorio": True,
                    "ativo": True,
                    "etapa": 6,
                    "ref_id": f"6.{ref_idx}",
                }
            )
            order += 1
            ref_idx += 1

    existing_orders = {q.get("ordem") for q in questions if isinstance(q, dict)}
    if any(q["ordem"] in existing_orders for q in stage6_questions):
        raise SystemExit("Order collision detected; aborting.")

    questions.extend(stage6_questions)
    form_item["perguntas"] = sorted(questions, key=lambda q: q.get("ordem", 0))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inserted etapa 6 and shifted orders >= {insert_start} by +{delta}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

