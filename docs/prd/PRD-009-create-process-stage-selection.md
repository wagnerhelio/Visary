# PRD-009: Etapas selecionaveis ao criar processo
## Resumo
Corrigir a tela de criacao de processo para exibir as etapas do checklist quando a viagem ja possui tipo de visto, mesmo sem registros especificos em `TripProcessStatus`.

## Problema atual
A tela de criar processo nao mostra os campos de marcacao das etapas. O template usa nomes de contexto antigos (`stages_disponiveis`, `stages_com_datas`) enquanto a view envia `available_stages` e `stages_with_dates`. Alem disso, o form e a API buscam etapas apenas em `TripProcessStatus`, deixando a tela vazia quando o tipo de visto possui `ProcessStatus` ativos mas a viagem ainda nao tem vinculos especificos.

## Objetivo
Permitir que o usuario veja todas as etapas ativas do tipo de visto da viagem, marque quais entram no processo, remova uma etapa desmarcando-a antes de criar, ou mantenha todas marcadas por padrao.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: documentacao oficial Django 4.1 sobre `JsonResponse(safe=False)` e widgets `CheckboxSelectMultiple` confirmou o uso atual de listas JSON e checkboxes multiplos.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
No escopo: fallback de etapas por `ProcessStatus.visa_type`, renderizacao inicial do checklist, API de etapas por viagem, criacao do processo respeitando as etapas marcadas, e correcao dos nomes de contexto na tela de edicao.
Fora do escopo: redesenho visual completo da tela, remodelagem do fluxo de status de processo, alteracao de migrations.

## Arquivos impactados
- `system/forms/process_forms.py`
- `system/views/process_views.py`
- `templates/process/create_process.html`
- `templates/process/edit_process.html`
- `system/tests/test_process_stage_selection.py`

## Riscos e edge cases
- Viagem sem tipo de visto deve continuar sem etapas disponiveis.
- `TripProcessStatus` especifico da viagem deve continuar prevalecendo quando existir.
- Etapas globais com `visa_type` nulo devem ser consideradas como fallback complementar.
- POST com etapa invalida nao deve criar etapa fora do conjunto permitido pelo form.

## Regras e restricoes
- SDD/TDD: teste vermelho antes da correcao.
- MTV: view orquestra; selecao reutilizavel de status fica fora do template.
- Sem nova dependencia.
- CSRF mantido em formularios POST.

## Criterios de aceite
- [x] Ao abrir `processos/criar/?client_id=<id>&trip_id=<id>` para uma viagem com status ativos no tipo de visto, a tela deve exibir checkboxes `selected_stages`.
- [x] Ao consultar `api/status-processo/?trip_id=<id>`, a API deve retornar as etapas ativas do tipo de visto quando nao houver `TripProcessStatus`.
- [x] Ao criar processo com apenas uma etapa marcada, o processo deve conter somente essa etapa.
- [x] Ao criar processo sem selecao explicita, o processo deve conter todas as etapas disponiveis.
- [x] Quando houver `TripProcessStatus` ativo para a viagem, essa configuracao deve prevalecer.

## Plano
- [x] 1. Testes de view/API/form para etapa disponivel por fallback.
- [x] 2. Seletor reutilizavel de etapas por viagem.
- [x] 3. Ajustar `ProcessForm`, view e API para usar o seletor.
- [x] 4. Corrigir variaveis de contexto nos templates de criar/editar processo.
- [x] 5. Validar com testes, check, collectstatic e Playwright/headless.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_process_stage_selection --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Criado teste de regressao para renderizacao de etapas no cadastro de processo, API de etapas, criacao com selecao parcial, criacao com todas as etapas e precedencia de `TripProcessStatus`.
- Adicionado seletor `get_available_statuses_for_trip()` para centralizar a obtencao de etapas ativas por viagem, com fallback para `ProcessStatus` do tipo de visto e status globais.
- Corrigido `ProcessForm` para manter `CheckboxSelectMultiple` sincronizado com as choices depois de trocar o widget.
- Ajustadas view/API/criacao/edicao de processo para usar o seletor reutilizavel.
- Corrigidos nomes de contexto antigos nos templates de criar/editar processo.
- Corrigidos detalhes de CSS/JS da tela de criar processo: classe do checklist e dados do combobox de cliente.
- Corrigidos nomes de campos coletados no JS da tela de edicao para bater com os campos `stage_*` esperados pela view.

## Desvios do plano
- Nenhuma dependencia adicionada.
- A validacao visual exigiu execucao elevada do Playwright porque o sandbox do Windows bloqueou o subprocesso do Chromium com `WinError 5`.
