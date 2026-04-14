# PRD-012: Campos do dependente no cadastro de cliente

## Resumo
Corrigir a etapa "Adicionar Membros" do cadastro de cliente para renderizar os campos do dependente com os nomes técnicos esperados pelo formulário Django.

## Problema atual
Ao tentar avançar na etapa de dependente, o backend recebe POST sem campos obrigatórios como `first_name`, `last_name`, `cpf`, `birth_date`, `nationality` e `phone`. O template da etapa usa campos crus da seed (`nome`, `sobrenome`, `telefone`, etc.) e variáveis inexistentes (`stage_dep`, `stage_field_obj`), impedindo a renderização correta dos inputs.

## Objetivo
Garantir que a tela de dependente exiba os dados pessoais, endereço e passaporte do membro usando o mapeamento oficial da view para os campos do `ConsultancyClientForm`.

## Contexto consultado
- Context7: indisponível neste ambiente; a correção é local ao template/contexto Django existente.
- Web: não consultada; o bug foi reproduzido por inspeção do código e logs locais, sem dependência externa.

## Dependências adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: contexto da view, template da etapa de dependentes, JavaScript local de CEP/passaporte do dependente e testes de renderização.
- Fora do escopo: redesign completo do cadastro, alteração de modelo, alteração de seed e persistência de rascunho.

## Arquivos impactados
- `system/views/client_views.py`
- `templates/client/register_client.html`
- `system/tests/test_dependent_register_fields.py`

## Riscos e edge cases
- Campos opcionais de endereço e passaporte podem ser omitidos por configuração de etapa.
- O dependente herda assessor e endereço do titular em alguns fluxos; a correção não pode quebrar essa automação.
- Seeds antigas podem usar nomes em inglês; o mapeamento deve preservar fallback para nomes já compatíveis.

## Regras e restrições (SDD, TDD, MTV, Design Patterns aplicáveis)
- TDD com teste de view antes da implementação.
- View continua preparando contexto; template apenas renderiza.
- Sem credenciais, sem alteração de CSRF, sem JS inline novo fora do padrão já existente da tela.

## Critérios de aceite (escritos como assertions testáveis)
- [x] Ao acessar a etapa "Adicionar Membros", o formulário do dependente deve conter `name="first_name"`, `name="last_name"`, `name="cpf"`, `name="birth_date"`, `name="nationality"` e `name="phone"` (verificável por teste de view).
- [x] O template não deve depender de `stage_dep` ou `stage_field_obj` para renderizar campos do dependente (verificável por teste e inspeção).
- [x] O CEP do dependente deve preencher `street`, `district`, `city` e `state` quando a busca retornar sucesso (verificável por inspeção/Playwright).
- [x] A seleção de tipo de passaporte do dependente deve operar sobre `passport_type` e `passport_type_other` (verificável por inspeção/Playwright).

## Plano (ordenado por dependência)
- [x] 1. Teste red para renderização dos campos do dependente.
- [x] 2. Contexto da view com campos dependentes mapeados.
- [x] 3. Template usando os nomes mapeados e variáveis corretas.
- [x] 4. Ajuste do JS da etapa de dependente para os nomes do formulário.
- [x] 5. Validação completa.

## Comandos de validação
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_dependent_register_fields --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`
- Playwright/headless na etapa 4 do cadastro.

## Implementado
- Adicionado teste de regressão para a etapa "Adicionar Membros" renderizar campos mapeados do dependente.
- Adicionado `dependent_display_fields` no contexto da view, usando o mapeamento `CLIENT_STEP_FIELD_MAP`.
- Mantido alias `dependent_stages` no contexto para o template ativo.
- Corrigido template ativo para renderizar campos por `form_field_name` e usar `dep_stage`/`stage_field`.
- Corrigidos seletores JS do dependente para `password`, `confirm_password`, `street`, `district`, `city`, `state`, `passport_type` e `passport_type_other`.
- Corrigidos data attributes do endereço do cliente titular usados no preenchimento do dependente.
- Screenshot de validação: `docs/prd/PRD-012-dependent-register-fields.png`.

## Desvios do plano
- Context7 e busca web não foram usados porque o problema era uma divergência local de nomes entre seed, view e template, sem dependência de documentação externa.
- Foi necessário executar Playwright fora do sandbox, pois o Chromium headless falhou no sandbox com `PermissionError: [WinError 5] Acesso negado`.

## Evidências de validação
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_dependent_register_fields --verbosity 2`: OK, 1 teste.
- `.\.venv\Scripts\python.exe manage.py check`: OK, sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`: OK, 0 arquivos copiados, 186 inalterados na última execução.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`: OK, 55 testes.
- Playwright/headless em `http://localhost:8000/clientes/cadastrar/?stage_id=4`: campos `first_name`, `last_name`, `cpf`, `birth_date`, `nationality`, `phone`, `zip_code` e `passport_number` presentes e visíveis; sem overflow horizontal; sem erros de console.
