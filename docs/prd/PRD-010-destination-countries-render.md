# PRD-010: Listagem de paises de destino
## Resumo
Corrigir a tela de Paises de Destino para exibir corretamente os paises cadastrados e manter os filtros funcionais.

## Problema atual
O banco local possui paises cadastrados, mas a tela de Paises de Destino e/ou sua listagem aparece vazia para o usuario. Foi identificado um desalinhamento entre o template e a view no filtro de codigo ISO: o template envia `codigo_iso`, enquanto a view le apenas `iso_code`.

## Objetivo
Garantir que a home e a listagem de Paises de Destino renderizem os paises cadastrados e que o filtro por codigo ISO funcione com os nomes usados pelo template.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: documentacao oficial Django sobre templates/contexto consultada para confirmar que variaveis ausentes no template nao disparam erro e podem resultar em UI vazia.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
No escopo: views/templates/testes de Paises de Destino.
Fora do escopo: redesenho visual completo, seed de novos paises, alteracao de modelo ou migrations.

## Arquivos impactados
- `system/views/travel_views.py`
- `templates/travel/home_destination_countries.html`
- `templates/travel/list_destination_countries.html`
- `system/tests/test_destination_countries_views.py`

## Riscos e edge cases
- Filtro antigo `iso_code` pode estar sendo usado em links manuais; deve continuar aceito.
- Filtro novo `codigo_iso` deve refletir corretamente no valor exibido no input.
- Usuarios sem permissao de gestao nao devem ganhar acesso indevido.

## Regras e restricoes
- SDD/TDD: teste vermelho antes da correcao.
- MTV: manter regra de filtro na view.
- Sem dependencia nova.
- Sem alteracao destrutiva no banco.

## Criterios de aceite
- [x] Ao abrir `paises-destino/`, a tela deve renderizar paises cadastrados.
- [x] Ao abrir `paises-destino/listar/`, a tabela deve renderizar paises cadastrados.
- [x] Ao filtrar por `codigo_iso=CAN`, a tela deve retornar Canada.
- [x] Ao filtrar pelo parametro legado `iso_code=CAN`, a tela tambem deve retornar Canada.

## Plano
- [x] 1. Criar testes de regressao para home/listagem/filtro ISO.
- [x] 2. Ajustar `_apply_country_filters` para aceitar `codigo_iso` e `iso_code`.
- [x] 3. Ajustar templates para usar nome de campo consistente.
- [x] 4. Validar com testes, check, collectstatic e Playwright/headless.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_destination_countries_views --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Criado `system/tests/test_destination_countries_views.py` cobrindo home, listagem e filtros ISO.
- Ajustado `_apply_country_filters()` para aceitar `iso_code` e o alias legado/de template `codigo_iso`.
- Atualizados `home_destination_countries.html` e `list_destination_countries.html` para enviar `iso_code`.
- Validado no banco local que existem 3 paises: Australia, Canada e Estados Unidos.
- Validado via Playwright que home/listagem exibem os paises no navegador.

## Desvios do plano
- A validacao visual exigiu execucao elevada do Playwright porque o Chromium precisa iniciar subprocesso fora das restricoes do sandbox.
