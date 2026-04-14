# PRD-013: Validação completa do dependente no cadastro de cliente

## Resumo
Corrigir a etapa de dependente dentro do cadastro de cliente para exigir todos os campos obrigatórios configurados nas etapas do dependente e exibir o nome correto na lista temporária.

## Problema atual
O dependente pode ser adicionado com passaporte e outros campos obrigatórios ausentes porque a configuração do formulário torna obrigatórios apenas os campos da primeira etapa e força campos das demais etapas como opcionais. Além disso, o resumo de dependentes temporários usa `dep.name`, mas os dados salvos na sessão usam `first_name` e `last_name`, exibindo "Sem nome".

## Objetivo
Bloquear a adição/finalização do vínculo do dependente quando qualquer campo obrigatório configurado nas etapas do cadastro estiver vazio, e exibir o nome completo do dependente temporário.

## Contexto consultado
- Context7: indisponível neste ambiente; a alteração é local ao fluxo Django existente.
- Web: não consultada; a causa foi identificada por inspeção local do formulário, view e seed `ETAPAS_CADASTRO_CLIENTE.json`.

## Dependências adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: validação server-side de campos configurados do dependente, resumo no template, teste de regressão.
- Fora do escopo: redesign da tela, alteração de modelos/migrações, alteração de OCR e alteração de seed.

## Arquivos impactados
- `system/views/client_views.py`
- `templates/client/register_client.html`
- `system/tests/test_dependent_register_fields.py`
- `docs/prd/PRD-013-dependent-required-fields-summary.md`

## Riscos e edge cases
- `use_primary_data` deve continuar dispensando senha/confirmar senha do dependente.
- Campos opcionais da seed, como endereço e `passport_type_other`, não devem virar obrigatórios indevidamente.
- Campos com regra condicional devem manter a validação própria do form, como `passport_type_other` obrigatório apenas quando o tipo é `other`.
- Dependentes já temporários precisam continuar editáveis/removíveis.

## Regras e restrições (SDD, TDD, MTV, Design Patterns aplicáveis)
- TDD com teste red antes da implementação.
- Validação server-side obrigatória.
- View prepara regras do formulário; template apenas exibe dados.

## Critérios de aceite (escritos como assertions testáveis)
- [x] Ao tentar adicionar dependente sem passaporte obrigatório, a resposta deve permanecer na etapa e não adicionar `temp_dependents`.
- [x] Ao renderizar dependente temporário, a lista deve exibir `first_name last_name` em vez de "Sem nome".
- [x] `use_primary_data` deve continuar permitindo dependente sem senha própria.
- [x] A suíte completa deve permanecer verde.

## Plano (ordenado por dependência)
- [x] 1. Teste red para bloqueio de passaporte obrigatório.
- [x] 2. Teste red para resumo do dependente com nome completo.
- [x] 3. Ajustar `_configure_dependent_form_fields` para respeitar `is_required` em todas as etapas.
- [x] 4. Ajustar template do resumo temporário.
- [x] 5. Validar com testes, check, collectstatic e Playwright/headless.

## Comandos de validação
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_dependent_register_fields --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`
- Playwright/headless na etapa 4 do cadastro.

## Implementado
- `_configure_dependent_form_fields` passou a aplicar `is_required` de todos os campos das etapas do dependente, não apenas da primeira etapa.
- O caminho de recuperação de assessor no POST do dependente passou a reconfigurar o formulário com todas as etapas.
- O resumo de dependentes temporários passou a exibir `first_name last_name`, com fallback para `name` e depois "Sem nome".
- Foram adicionados testes para bloquear dependente sem passaporte obrigatório, manter renderização de campos mapeados, exibir nome completo no resumo e preservar `use_primary_data` sem senha própria.
- Screenshot de validação: `docs/prd/PRD-013-dependent-required-fields-summary.png`.

## Desvios do plano
- Context7 e busca web não foram usados porque a causa era local ao mapeamento/required do formulário Django.
- Playwright foi executado fora do sandbox por limitação do Chromium neste ambiente.

## Evidências de validação
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_dependent_register_fields --verbosity 2`: OK, 4 testes.
- `.\.venv\Scripts\python.exe manage.py check`: OK, sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`: OK, 7 arquivos copiados e 179 inalterados.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`: OK, 58 testes.
- Playwright/headless em `http://localhost:8000/clientes/cadastrar/?stage_id=4`: dependente sem passaporte gerou 7 listas de erro, `passport_number` exibiu erro obrigatório, "Maria Silva" não foi adicionado ao resumo temporário e não houve erro de console.
