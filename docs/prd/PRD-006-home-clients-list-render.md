# PRD-006: Renderizar lista em Meus Clientes
## Resumo
Corrigir a tela "Meus Clientes" para renderizar a tabela quando a view envia clientes no contexto.

## Problema atual
A view `home_clients` envia `clients_with_status`, mas o template `templates/client/home_clients.html` condiciona a exibicao da tabela por `clients_com_status`, variavel inexistente. O cliente esta cadastrado e vinculado, mas a lista nao aparece.

## Objetivo
Exibir os clientes vinculados na tela "Meus Clientes" quando `clients_with_status` tiver itens.

## Contexto consultado
  - Context7: nao disponivel neste ambiente.
  - Web: nao consultada; a falha e local de template/contexto.

## Dependencias adicionadas
  - nenhuma.

## Escopo / Fora do escopo
Escopo: template de "Meus Clientes" e teste de regressao.

Fora do escopo: redesign da tela, filtros, permissoes e alteracoes de cadastro.

## Arquivos impactados
  - `templates/client/home_clients.html`
  - `system/tests/test_scoped_vs_global_listings.py`
  - `docs/prd/PRD-006-home-clients-list-render.md`

## Riscos e edge cases
  - A lista deve continuar respeitando o filtro da view.
  - A tela "Listar Clientes" nao deve ser alterada.

## Regras e restricoes
  - TDD com teste de regressao antes da correcao.
  - Sem dependencia nova.
  - Sem alteracao de regra de permissao.

## Criterios de aceite
  - [x] Com cliente vinculado no contexto, o HTML de "Meus Clientes" deve conter o nome do cliente.
  - [x] A view continua filtrando clientes por assessor quando o usuario nao gerencia tudo.

## Plano
  - [x] 1. Adicionar teste de renderizacao HTML da tela "Meus Clientes".
  - [x] 2. Corrigir a variavel condicional do template.
  - [x] 3. Rodar teste focado, check, collectstatic e suite completa.

## Comandos de validacao
  - `.\.venv\Scripts\python.exe manage.py test system.tests.test_scoped_vs_global_listings --verbosity 2`
  - `.\.venv\Scripts\python.exe manage.py check`
  - `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
  - `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- `templates/client/home_clients.html`: condicional da tabela corrigida de `clients_com_status` para `clients_with_status`.
- `system/tests/test_scoped_vs_global_listings.py`: teste de regressao para garantir que a secao `#sec-clientes` renderiza quando ha clientes vinculados.

Evidencias:
- Red: `test_home_clientes_renderiza_lista_de_clientes_vinculados` falhou antes da correcao porque `#sec-clientes` nao estava no HTML.
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_scoped_vs_global_listings --verbosity 2` => 6 testes OK.
- `.\.venv\Scripts\python.exe manage.py check` => sem issues.
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` => 0 copiados, 183 inalterados, sem erro.
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2` => 36 testes OK.
- Playwright em `/clientes/` => `section_count 1`, `client_count 1`, `app_console_errors []`, `request_failures []`.
- Screenshot: `docs/prd/PRD-006-home-clients-playwright.png`.

## Desvios do plano
Nenhum.
