import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEEDS_DIR = ROOT / "static" / "forms_ini"


def _add_ref_ids_for_form(form_item: dict) -> bool:
    changed = False
    counters: dict[int, int] = defaultdict(int)

    for q in form_item.get("perguntas", []):
        stage = q.get("etapa")
        try:
            stage_int = int(stage) if stage is not None else None
        except (TypeError, ValueError):
            stage_int = None

        if stage_int is None:
            continue

        counters[stage_int] += 1
        if q.get("ref_id"):
            continue

        q["ref_id"] = f"{stage_int}.{counters[stage_int]}"
        changed = True

    return changed


def main() -> int:
    if not SEEDS_DIR.exists():
        raise SystemExit(f"Seeds dir not found: {SEEDS_DIR}")

    seed_files = sorted(SEEDS_DIR.glob("*.json"))
    changed_files: list[Path] = []

    for path in seed_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            continue

        changed = False
        for form_item in payload:
            if isinstance(form_item, dict):
                changed = _add_ref_ids_for_form(form_item) or changed

        if changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed_files.append(path)

    if changed_files:
        print("Updated ref_id in seeds:")
        for p in changed_files:
            print(f"- {p.relative_to(ROOT)}")
    else:
        print("No seed changes required (all questions already have ref_id).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

