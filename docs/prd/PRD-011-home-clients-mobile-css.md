# PRD-011: Responsividade de Meus Clientes no celular
## Resumo
Corrigir o CSS mobile da tela `Meus Clientes` para que KPIs e dados dos clientes caibam no viewport do celular sem cortar informacoes.

## Problema atual
No celular, a tela `Meus Clientes` apresenta cards de KPI e tabela de clientes com conteudo vazando horizontalmente. A tabela permanece em formato desktop, dificultando a leitura de nome, progresso, status financeiro e demais informacoes.

## Objetivo
Exibir a tela de clientes no celular com layout legivel: cards de acao e KPIs empilhados, tabela convertida em blocos por cliente, labels por campo e botoes acessiveis sem overflow horizontal.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: MDN sobre tabelas HTML/CSS em telas pequenas, especialmente o uso de overflow e alteracao de display para melhorar a leitura de tabelas largas.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
No escopo: CSS mobile da tela `templates/client/home_clients.html` via arquivo estatico namespaced.
Fora do escopo: redesenho desktop, alteracao de dados da view, mudanca no fluxo de cadastro/listagem.

## Arquivos impactados
- `templates/client/home_clients.html`
- `static/system/css/home_clients_mobile.css`
- `system/tests/test_home_clients_mobile_css.py`

## Riscos e edge cases
- A tabela possui muitas colunas; no mobile os labels precisam continuar alinhados aos respectivos campos.
- Nomes e e-mails longos devem quebrar linha sem estourar o card.
- Os botoes de acao devem continuar utilizaveis no celular.

## Regras e restricoes
- SDD/TDD: teste de regressao para carregamento do CSS antes da implementacao visual.
- CSS novo em arquivo estatico namespaced.
- Sem nova dependencia.

## Criterios de aceite
- [x] A tela `Meus Clientes` deve carregar `system/css/home_clients_mobile.css`.
- [x] No mobile, KPIs devem ocupar uma coluna sem overflow horizontal.
- [x] No mobile, cada linha da tabela deve virar um bloco com labels por campo.
- [x] No mobile, botoes de acao devem quebrar linha e caber no viewport.

## Plano
- [x] 1. Criar teste de carregamento do CSS mobile.
- [x] 2. Incluir o CSS namespaced no template.
- [x] 3. Criar CSS mobile para cards, KPIs, tabela e botoes.
- [x] 4. Validar com testes, collectstatic e Playwright/headless.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_home_clients_mobile_css --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Criado `static/system/css/home_clients_mobile.css` com regras responsivas para a tela `Meus Clientes`.
- Incluido o CSS no template `templates/client/home_clients.html`.
- Transformada a tabela de clientes em cards mobile com labels por campo em viewports pequenos.
- Forcada a grade de KPIs para uma coluna no celular e ajustadas quebras de texto/botoes para evitar overflow horizontal.
- Criado `system/tests/test_home_clients_mobile_css.py` para garantir carregamento do CSS.
- Validado via Playwright em viewport 269x768: `scrollWidth == clientWidth`, tabela e linhas em `display: block`, KPI em uma coluna e sem erros de console.

## Desvios do plano
- A validacao visual exigiu execucao elevada do Playwright porque o Chromium precisa iniciar subprocesso fora das restricoes do sandbox.
