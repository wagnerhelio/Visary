# PRD-011: Responsividade das telas home no celular
## Resumo
Corrigir o CSS mobile das telas `Meus Clientes`, `Meus Formularios`, `Meus Processos` e `Minhas Viagens` para que KPIs e dados tabulares caibam no viewport do celular sem cortar informacoes.

## Problema atual
No celular, as telas de Clientes, Formularios, Processos e Viagens apresentam cards de KPI e tabelas com conteudo vazando horizontalmente. As tabelas permanecem em formato desktop, dificultando a leitura de nome, progresso, status, tipo de visto, parceiro e acoes.

## Objetivo
Exibir as telas home no celular com layout legivel: cards de acao e KPIs empilhados, tabelas convertidas em blocos por item, labels por campo e botoes acessiveis sem overflow horizontal.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Web: MDN sobre tabelas HTML/CSS em telas pequenas, especialmente o uso de overflow e alteracao de display para melhorar a leitura de tabelas largas.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
No escopo: CSS mobile compartilhado para as telas home com tabelas `.mini-table`.
Fora do escopo: redesenho desktop, alteracao de dados das views, mudanca no fluxo de cadastro/listagem.

## Arquivos impactados
- `templates/client/home_clients.html`
- `templates/forms/home_forms.html`
- `templates/process/home_processes.html`
- `templates/travel/home_trips.html`
- `static/system/css/home_sections_mobile.css`
- `system/tests/test_home_clients_mobile_css.py`

## Riscos e edge cases
- As tabelas possuem colunas diferentes; no mobile os labels precisam continuar alinhados aos respectivos campos.
- Nomes, e-mails e tipos de visto longos devem quebrar linha sem estourar o card.
- Os botoes de acao devem continuar utilizaveis no celular.

## Regras e restricoes
- SDD/TDD: teste de regressao para carregamento do CSS antes da implementacao visual.
- CSS novo em arquivo estatico namespaced.
- Sem nova dependencia.

## Criterios de aceite
- [x] As telas Clientes, Formularios, Processos e Viagens devem carregar `system/css/home_sections_mobile.css`.
- [x] No mobile, KPIs devem ocupar uma coluna sem overflow horizontal.
- [x] No mobile, cada linha da tabela deve virar um bloco com labels por campo corretos para sua tela.
- [x] No mobile, botoes de acao devem quebrar linha e caber no viewport.

## Plano
- [x] 1. Atualizar teste de carregamento do CSS mobile compartilhado nas quatro telas.
- [x] 2. Incluir o CSS namespaced nos templates afetados.
- [x] 3. Criar CSS mobile compartilhado para cards, KPIs, tabela, labels por secao e botoes.
- [x] 4. Validar com testes, collectstatic e Playwright/headless nas quatro telas.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_home_clients_mobile_css --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Criado `static/system/css/home_sections_mobile.css` com regras responsivas compartilhadas para Clientes, Formularios, Processos e Viagens.
- Atualizados `templates/client/home_clients.html`, `templates/forms/home_forms.html`, `templates/process/home_processes.html` e `templates/travel/home_trips.html` para carregar o CSS compartilhado.
- Adicionados IDs nas secoes de formularios pendentes/preenchidos para labels mobile especificos.
- Atualizado `system/tests/test_home_clients_mobile_css.py` para garantir que as quatro telas carregam o CSS compartilhado.
- Validado via Playwright em viewport 269x768: nas quatro telas `scrollWidth == clientWidth`, tabela e linhas em `display: block`, KPI em uma coluna, CSS carregado e nenhum erro de console.

## Desvios do plano
- Mantido o arquivo anterior `home_clients_mobile.css` no repositório por compatibilidade local; as quatro telas corrigidas usam o novo `home_sections_mobile.css`.
- A validacao visual exigiu execucao elevada do Playwright porque o Chromium precisa iniciar subprocesso fora das restricoes do sandbox.
