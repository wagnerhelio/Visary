# PRD-005: Criar viagem com cliente principal e tipos de visto
## Resumo
Corrigir o fluxo de criacao de viagem iniciado apos o cadastro de um cliente unico.

## Problema atual
- A URL de criacao de viagem recebe `?clientes=<id>`, mas a view considera apenas `clients`, deixando o cliente fora da selecao pre-preenchida.
- O combobox de cliente monta objetos com `nome`, mas o JS acessa `name`, exibindo `undefined`.
- O endpoint `api/tipos-visto/` le apenas `country`, enquanto templates chamam com `pais`, causando 400 e erro de `data.forEach`.
- Um cliente unico deve entrar como cliente principal da viagem.

## Objetivo
Ao chegar em `viagens/criar/?clientes=<id>`, o cliente informado deve aparecer como principal, sem `undefined`, e a escolha de pais deve carregar tipos de visto sem erro 400.

## Contexto consultado
  - Context7: nao disponivel neste ambiente.
  - Web: nao consultada; a mudanca e local ao contrato entre view, template e endpoint do proprio projeto.

## Dependencias adicionadas
  - nenhuma.

## Escopo / Fora do escopo
Escopo: view de criacao de viagem, API de tipos de visto, JS do template de criacao/edicao de viagem e testes de regressao.

Fora do escopo: redesenho completo do formulario de viagem, regras de viagem com varios grupos familiares e alteracoes de modelo.

## Arquivos impactados
  - `system/views/travel_views.py`
  - `templates/travel/create_trip.html`
  - `templates/travel/edit_trip.html`
  - `system/tests/test_travel_views.py`

## Riscos e edge cases
  - Links legados podem usar `clients`, `clientes`, `country`, `pais_id` ou `pais`; a correcao deve preservar compatibilidade.
  - Se houver dependentes, apenas um membro deve ser principal na viagem.
  - O frontend deve lidar com erro JSON sem chamar `forEach` em objeto de erro.

## Regras e restricoes
  - Views finas e validacao server-side preservadas.
  - Sem dependencia nova.
  - Sem credenciais ou desabilitacao de CSRF.
  - TDD aplicado nos contratos de view/API afetados.

## Criterios de aceite
  - [x] GET em `api/tipos-visto/?pais=<id>` retorna lista de vistos ativa do pais.
  - [x] GET em `api/tipos-visto/?pais_id=<id>` continua aceito.
  - [x] GET em `viagens/criar/?clientes=<id>` popula `preselected_clients` e `trip_members` com o cliente como principal.
  - [x] O template da criacao nao referencia `c.name` para objetos criados com `nome`.
  - [x] POST de viagem com um unico cliente cria `TripClient.role == "primary"`.
  - [x] A tela nao emite erro app-side ao trocar pais para carregar tipo de visto.

## Plano
  - [x] 1. Escrever testes de regressao para API e criacao de viagem.
  - [x] 2. Normalizar aliases de query string na view.
  - [x] 3. Corrigir papel do cliente principal no `TripClient`.
  - [x] 4. Corrigir JS do combobox e fetch dos tipos de visto.
  - [x] 5. Validar com testes, collectstatic e Playwright.

## Comandos de validacao
  - `.\.venv\Scripts\python.exe manage.py test system.tests.test_travel_views --verbosity 2`
  - `.\.venv\Scripts\python.exe manage.py check`
  - `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
  - `.\.venv\Scripts\python.exe manage.py test --verbosity 2`
  - Playwright em `viagens/criar/?clientes=<id>`

## Implementado
- `system/views/travel_views.py`: aceita `clientes` e `clients` na criacao de viagem, aceita `country`, `pais_id` e `pais` na API de tipos de visto, e define o primeiro cliente principal como `TripClient.role == "primary"`.
- `templates/travel/create_trip.html`: nomes dos inputs alterados para `clients`, fetch de vistos usa `pais_id`, retorno da API e tratado antes de `forEach`, e o combobox usa `nome`/`data-nome` de forma consistente.
- `templates/travel/edit_trip.html`: fetch de tipos de visto usa `pais_id` e valida resposta array.
- `system/tests/test_travel_views.py`: regressao para API, preseleção por `clientes` e persistencia do papel principal.

Evidencias:
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_travel_views --verbosity 2` => 4 testes OK.
- `.\.venv\Scripts\python.exe manage.py check` => sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` => 0 copiados, 183 inalterados, sem erro.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` => 35 testes OK.
- Playwright em `viagens/criar/?clientes=1` => `has_undefined False`, `hidden_client_count 1`, `visa_options_after_country_change 3`, `app_console_errors []`, `request_failures []`.
- Screenshot: `docs/prd/PRD-005-create-trip-playwright.png`.

## Desvios do plano
- `findstatic css/base.css` retornou "No matching file found" porque o projeto atual nao possui `static/css/base.css`; ha apenas CSS namespaced em `static/system/css/...`. A validacao de estaticos foi feita por `collectstatic` e Playwright sem requests falhando.
