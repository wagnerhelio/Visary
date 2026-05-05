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

    insert_start = 81
    delta = 14
    _shift_orders(questions, start_order=insert_start, delta=delta)

    # Etapa 7 - Custeio da viagem (CusteioViagem/index.tsx)
    # Pergunta 1 controla o bloco (outra_pessoa vs empresa); se "Eu mesmo(a)", o legado pula etapa.
    stage7 = [
        {
            "ordem": 81,
            "pergunta": "Responsavel pelo custeio da viagem",
            "tipo_campo": "selecao",
            "obrigatorio": True,
            "ativo": True,
            "etapa": 7,
            "ref_id": "7.1",
            "opcoes": [
                {"valor": "eu", "rotulo": "Eu mesmo(a)"},
                {"valor": "outra_pessoa", "rotulo": "Outra pessoa"},
                {"valor": "empresa", "rotulo": "Empresa / Organização"},
            ],
        },
        # outra_pessoa block
        {"ordem": 82, "pergunta": "Nome", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.2",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"}},
        {"ordem": 83, "pergunta": "sobrenome", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.3",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"}},
        {"ordem": 84, "pergunta": "Email", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.4",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"}},
        {"ordem": 85, "pergunta": "Telefone", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.5",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"}},
        {"ordem": 86, "pergunta": "Relação com você", "tipo_campo": "selecao", "obrigatorio": False, "ativo": True, "etapa": 7, "ref_id": "7.6",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"},
         "opcoes": [
             {"valor": "pais", "rotulo": "Pai ou mãe"},
             {"valor": "conjuge", "rotulo": "Cônjuge"},
             {"valor": "filho", "rotulo": "Filho(a)"},
             {"valor": "outro", "rotulo": "Outro tipo de parentesco"},
             {"valor": "amigo", "rotulo": "Amigo"},
         ]},
        {"ordem": 87, "pergunta": "Endereço completo", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.7",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "outra_pessoa"}},
        # empresa block
        {"ordem": 88, "pergunta": "Nome da empresa/organização", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.8",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 89, "pergunta": "Telefone", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.9",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 90, "pergunta": "CEP", "tipo_campo": "texto", "obrigatorio": False, "ativo": True, "etapa": 7, "ref_id": "7.10",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 91, "pergunta": "Endereço", "tipo_campo": "texto", "obrigatorio": True, "ativo": True, "etapa": 7, "ref_id": "7.11",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 92, "pergunta": "Cidade", "tipo_campo": "texto", "obrigatorio": False, "ativo": True, "etapa": 7, "ref_id": "7.12",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 93, "pergunta": "Estado", "tipo_campo": "texto", "obrigatorio": False, "ativo": True, "etapa": 7, "ref_id": "7.13",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
        {"ordem": 94, "pergunta": "Você faz parte do quadro de colaboradores?", "tipo_campo": "booleano", "obrigatorio": False, "ativo": True, "etapa": 7, "ref_id": "7.14",
         "regra_exibicao": {"pergunta_ordem": 81, "operador": "equals", "valor": "empresa"}},
    ]

    existing_orders = {q.get("ordem") for q in questions if isinstance(q, dict)}
    if any(q["ordem"] in existing_orders for q in stage7):
        raise SystemExit("Order collision detected; aborting.")

    questions.extend(stage7)
    form_item["perguntas"] = sorted(questions, key=lambda q: q.get("ordem", 0))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Inserted etapa 7 and shifted orders >= {insert_start} by +{delta}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

