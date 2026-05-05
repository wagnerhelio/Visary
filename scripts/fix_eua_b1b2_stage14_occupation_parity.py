import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _shift_orders(questions: list[dict], start_order: int, delta: int) -> None:
    for q in questions:
        order = q.get("ordem")
        if isinstance(order, int) and order >= start_order:
            q["ordem"] = order + delta

        rule = q.get("regra_exibicao")
        if isinstance(rule, dict):
            trigger = rule.get("pergunta_ordem")
            if isinstance(trigger, int) and trigger >= start_order:
                rule["pergunta_ordem"] = trigger + delta


def main() -> int:
    path = ROOT / "static" / "forms_ini" / "FORMULARIO_EUA_B1_B2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise SystemExit("Invalid seed payload.")

    form_item = payload[0]
    questions = form_item.get("perguntas", [])
    if not isinstance(questions, list):
        raise SystemExit("Invalid perguntas.")

    # Legacy (visary-front) stage 14 has an explicit "Bairro" field.
    insert_order = 122
    _shift_orders(questions, start_order=insert_order, delta=1)

    stage14_by_ref = {q.get("ref_id"): q for q in questions if isinstance(q, dict) and q.get("etapa") == 14}

    # Labels + required parity with legacy TSX
    updates = {
        "14.1": ("Ocupação atual do solicitante", True, "texto"),
        "14.2": ("Nome da empresa ou escola", True, "texto"),
        "14.3": ("Endereço", True, "texto"),
        "14.4": ("Cidade", True, "texto"),
        "14.5": ("Estado", True, "texto"),
        "14.6": ("CEP", False, "texto"),
        "14.7": ("Telefone", True, "texto"),
        "14.8": ("País", True, "texto"),
        "14.9": ("Data de admissão no trabalho ou início dos estudos", True, "data"),
        "14.10": ("Renda mensal (em reais)", True, "numero"),
        "14.11": ("Descreva brevemente suas funções", True, "texto"),
    }

    for ref_id, (label, required, field_type) in updates.items():
        q = stage14_by_ref.get(ref_id)
        if not q:
            raise SystemExit(f"Missing expected ref_id {ref_id} in stage 14.")
        q["pergunta"] = label
        q["obrigatorio"] = bool(required)
        q["tipo_campo"] = field_type

    bairro_question = {
        "ordem": insert_order,
        "pergunta": "Bairro",
        "tipo_campo": "texto",
        "obrigatorio": True,
        "ativo": True,
        "etapa": 14,
        "ref_id": "14.12",
    }

    existing_orders = {q.get("ordem") for q in questions if isinstance(q, dict)}
    if bairro_question["ordem"] in existing_orders:
        raise SystemExit("Order collision detected; aborting.")

    questions.append(bairro_question)
    form_item["perguntas"] = sorted(questions, key=lambda q: q.get("ordem", 0))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Stage 14 parity updated; inserted Bairro at ordem {insert_order}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

