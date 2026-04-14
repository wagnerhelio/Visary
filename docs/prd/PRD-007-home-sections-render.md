# PRD-007: Renderizar secoes de viagens e processos
## Resumo
Corrigir as telas "Minhas Viagens", "Meus Processos" e o painel principal para usar os nomes de contexto que as views realmente enviam.

## Problema atual
As views possuem dados no contexto, mas alguns templates usam variaveis antigas ou inexistentes:
- `templates/travel/home_trips.html` testa `viagens`, mas a view envia `trips`.
- `templates/process/home_processes.html` testa `process_objs`, mas a view envia `processes`.
- Alguns filtros/datalists usam `clientes`, `paises`, `tipos_visto` enquanto as views enviam `clients`, `countries`, `visa_types`.
- `templates/home/home.html` ainda usa `clients_com_status` e `processos` em condicionais.

## Objetivo
Renderizar listas existentes de viagens, processos e painel quando as views possuem dados no contexto.

## Contexto consultado
  - Context7: nao disponivel neste ambiente.
  - Web: nao consultada; a falha e local de contrato entre views e templates.

## Dependencias adicionadas
  - nenhuma.

## Escopo / Fora do escopo
Escopo: templates de home de viagens, processos e painel principal; testes de regressao.

Fora do escopo: redesign visual, novas regras de permissao, mudancas em model ou banco.

## Arquivos impactados
  - `templates/travel/home_trips.html`
  - `templates/process/home_processes.html`
  - `templates/home/home.html`
  - `system/tests/test_scoped_vs_global_listings.py`
  - `docs/prd/PRD-007-home-sections-render.md`

## Riscos e edge cases
  - Filtros devem continuar usando os dados enviados pela view.
  - Listagens globais completas nao devem ser alteradas.
  - O painel principal deve preservar as secoes vazias quando realmente nao houver dados.

## Regras e restricoes
  - TDD com regressao antes da correcao.
  - Sem dependencia nova.
  - Sem alteracao de permissao.

## Criterios de aceite
  - [x] "Minhas Viagens" renderiza a secao de tabela quando `trips` possui dados.
  - [x] "Meus Processos" renderiza a secao de tabela quando `processes` possui dados.
  - [x] O painel principal usa `clients_with_status` e `processes` nas condicionais.
  - [x] Filtros/datalists usam os nomes enviados pelas views.

## Plano
  - [x] 1. Adicionar testes de renderizacao HTML para home de viagens, processos e painel.
  - [x] 2. Corrigir variaveis de contexto nos templates.
  - [x] 3. Rodar testes focados, check, collectstatic, suite completa e Playwright.

## Comandos de validacao
  - `.\.venv\Scripts\python.exe manage.py test system.tests.test_scoped_vs_global_listings --verbosity 2`
  - `.\.venv\Scripts\python.exe manage.py check`
  - `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
  - `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- `templates/travel/home_trips.html`: troca de `viagens` para `trips`, `paises` para `countries`, `tipos_visto` para `visa_types` e `clientes` para `clients`; adicionada ancora `#sec-viagens`.
- `templates/process/home_processes.html`: troca de `process_objs` para `processes`, `applied_filters_dict` para `applied_filters` e `clientes` para `clients`; adicionada ancora `#sec-processos`.
- `templates/home/home.html`: troca de `clients_com_status` para `clients_with_status` no painel principal.
- `system/tests/test_scoped_vs_global_listings.py`: regressao para renderizacao das homes de clientes, viagens, processos e painel principal.

Evidencias:
- Red: os testes de renderizacao das homes de viagens, processos e painel falharam antes da correcao.
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_scoped_vs_global_listings --verbosity 2` => 9 testes OK.
- `.\.venv\Scripts\python.exe manage.py check` => sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` => 0 copiados, 183 inalterados, sem erro.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` => 39 testes OK.
- Playwright: `/`, `/viagens/` e `/processos/` renderizaram `#sec-clientes`, `#sec-viagens` e `#sec-processos`; `app_console_errors []`; `request_failures []`.
- Screenshots: `docs/prd/PRD-007-dashboard.png`, `docs/prd/PRD-007-home-trips.png`, `docs/prd/PRD-007-home-processes.png`.

## Desvios do plano
Nenhum.
