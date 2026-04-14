# PRD-002: Ajuste mobile do painel de atendimento
## Resumo
Corrigir a visualizacao da tela "Painel de Atendimento" em celulares, evitando quebra horizontal de filtros, indicadores e tabelas.

## Problema atual
Em viewport estreita, os filtros, cards de indicadores e tabelas do painel ultrapassam a largura util da tela, deixando conteudo cortado e leitura ruim.

## Objetivo
Garantir que a tela principal do painel seja utilizavel em celular, com controles ocupando a largura disponivel e tabelas convertidas para blocos legiveis em telas pequenas.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: MDN CSS Overflow, referencia sobre overflow e controle de conteudo que excede o box.

## Dependencias adicionadas
- playwright==1.58.0 — validacao visual mobile automatizada.

## Escopo / Fora do escopo
- Escopo: template `templates/home/home.html` e CSS estatico especifico para responsividade mobile do painel.
- Fora do escopo: reescrita completa dos estilos globais inline existentes em `base.html` e `home.html`, alteracoes de regras de negocio ou consultas do dashboard.

## Arquivos impactados
- `templates/home/home.html`
- `static/system/css/home_dashboard_mobile.css`
- `requirements.txt`

## Riscos e edge cases
- Tabelas com colunas diferentes precisam preservar a informacao ao virar blocos no mobile.
- Valores financeiros longos nao podem estourar o card.
- O dropdown de busca de cliente precisa continuar alinhado ao input no mobile.

## Regras e restricoes
- Texto visivel ao usuario final em pt-BR.
- CSS/JS especifico de tela deve ficar em arquivo estatico namespaced.
- Alteracao sem nova dependencia.

## Criterios de aceite
- [x] Em viewport mobile, o painel nao deve gerar overflow horizontal no documento.
- [x] Filtros devem ocupar a largura disponivel sem cortar textos.
- [x] Indicadores devem caber na tela, com valores financeiros quebrando linha quando necessario.
- [x] Tabelas devem ser legiveis em celular sem depender de scroll horizontal.
- [x] `collectstatic --noinput` deve rodar sem erro.

## Plano
- [x] 1. Identificar template e estilos da tela.
- [x] 2. Adicionar CSS mobile namespaced.
- [x] 3. Linkar CSS no template.
- [x] 4. Validar template e arquivos estaticos.
- [x] 5. Atualizar este PRD com evidencias.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py findstatic system/css/home_dashboard_mobile.css`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Adicionado `static/system/css/home_dashboard_mobile.css` com regras mobile para largura geral, filtros, cards de indicadores e tabelas em formato de blocos.
- Linkado o CSS no bloco de estilos de `templates/home/home.html`.
- Adicionado `playwright==1.58.0` ao `requirements.txt` para suportar validacao visual.
- Evidencias:
  - `collectstatic --noinput`: 1 arquivo copiado, 181 inalterados na rodada final.
  - Playwright mobile 390x844: `documentScrollWidth=390`, `viewportWidth=390`, `cssLoaded=True`, `rowDisplay='block'`, `emptyBefore='none'`.
  - Screenshot: `docs/prd/PRD-002-mobile-check.png`.

## Desvios do plano
- A validacao visual exigiu instalar Playwright, que nao estava na `.venv`.
- `.\.venv\Scripts\playwright.exe install chromium` foi bloqueado por politica do Windows; a instalacao funcionou via `.\.venv\Scripts\python.exe -m playwright install chromium`.
- `findstatic css/base.css` nao encontrou arquivo porque o repositorio atual concentra estilos globais inline em `templates/base.html`; nao foi criado `base.css` para evitar ampliar escopo.
