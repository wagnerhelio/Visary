# PRD-019: Paridade total legado × seeds (perguntas e pulos)

## Resumo do que será implementado
Garantir que todos os formulários dinâmicos em `static/forms_ini/*.json` tenham:

- a **mesma sequência de etapas** do legado;
- as **mesmas perguntas** (texto/ordem/etapa/tipo/obrigatoriedade) do legado;
- o **mesmo comportamento condicional** do legado (inclui “pulo de tela” e blocos opcionais), reimplementado via `display_rule` + “etapa aplicável” no Django.

## Tipo de demanda
Refatoração com correção minuciosa e curadoria de seeds.

## Problema atual
- Existem divergências entre o legado e os seeds atuais: perguntas ausentes, perguntas em etapa errada, regras condicionais incompletas e etapas exibidas quando deveriam ser puladas.
- O legado implementa “pulos” via wizard (React). O novo precisa reproduzir o mesmo comportamento usando `display_rule` e filtragem de etapas aplicáveis.

## Objetivo
Paridade funcional e de conteúdo: “o usuário responde as mesmas coisas, na mesma ordem, com as mesmas telas pulando quando aplicável”.

## Context Ledger
### Arquivos lidos integralmente
- `docs/prd/PRD-017-curadoria-formularios-legado.md`
- `docs/prd/PRD-018-form-flow-prefill-and-visual-state.md`
- `static/forms_ini/*.json`
- `system/management/commands/seed_visa_forms.py`
- `system/services/form_responses.py`
- `system/services/form_stages.py`
- `system/views/client_area_views.py`
- `system/views/travel_views.py`
- todos os `index.tsx` em `visary-front/src/pages/Processos/Formularios/**`

### Limitações encontradas
- Extração do legado é estática (análise de TSX). A validação visual deve confirmar o runtime após as correções.

## Critérios de aceite
- [ ] Para cada formulário em `static/forms_ini`, o relatório automático legado×seed não tem divergências **não justificadas**.
- [ ] Etapas “puladas” no legado não aparecem no novo quando os gatilhos são negativos.
- [ ] `manage.py seed_visa_forms` executa sem erros.
- [ ] `manage.py test system.tests` passa (0 falhas, 0 erros).

## Plano
- [ ] Implementar extrator/diff automático legado×seed por formulário/etapa
- [ ] Gerar relatório de divergências (markdown) versionado em `docs/prd/`
- [ ] Corrigir seeds e regras até o relatório ficar zerado
- [ ] Rodar suite de testes e checks

