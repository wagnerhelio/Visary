import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def shift_seed_file(path: Path, start_order: int, delta: int) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        return False

    changed = False
    for form_item in payload:
        if not isinstance(form_item, dict):
            continue
        questions = form_item.get("perguntas")
        if not isinstance(questions, list):
            continue

        for q in questions:
            if not isinstance(q, dict):
                continue
            order = q.get("ordem")
            if isinstance(order, int) and order >= start_order:
                q["ordem"] = order + delta
                changed = True

            rule = q.get("regra_exibicao")
            if isinstance(rule, dict):
                trigger = rule.get("pergunta_ordem")
                if isinstance(trigger, int) and trigger >= start_order:
                    rule["pergunta_ordem"] = trigger + delta
                    changed = True

    if changed:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return changed


def main() -> int:
    target = ROOT / "static" / "forms_ini" / "FORMULARIO_EUA_B1_B2.json"
    changed = shift_seed_file(target, start_order=48, delta=1)
    if changed:
        print(f"Shifted orders in: {target}")
        return 0
    print("No changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

