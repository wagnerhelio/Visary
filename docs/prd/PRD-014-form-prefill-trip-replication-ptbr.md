# PRD-014: Pre-preenchimento e replicacao correta de formularios de viagem

## Resumo
Corrigir a pre-carga dos formularios de visto e a replicacao de dados entre cliente principal e dependente para evitar respostas duplicadas, desconexas ou copiadas para campos pessoais errados.

## Problema atual
As regras de pre-preenchimento tratavam perguntas genericas de endereco, passaporte, empregador, escola, contatos e acompanhantes como se fossem dados pessoais do cliente. Como varias dessas perguntas ficam na etapa 1 dos JSONs, o sistema preenchia respostas indevidas com dados do cadastro do cliente. Alem disso, a acao de replicar respostas do cliente principal copiava todas as respostas para o dependente, incluindo dados pessoais que devem ser exclusivos de cada pessoa. Havia tambem textos visiveis usando "trip" em ingles.

## Objetivo
Permitir pre-preenchimento automatico apenas para dados pessoais diretos do aplicante na primeira etapa do formulario, preservar respostas existentes, impedir copia de campos pessoais do principal para dependentes e trocar textos de "trip" para "viagem" no UI.

## Contexto consultado
- Context7: indisponivel neste ambiente; a correcao e local ao dominio Django existente.
- Web: nao consultada; a revisao foi feita nos JSONs locais em `static/forms_ini/` e nos servicos `form_prefill`/`form_prefill_rules`.
- JSONs revisados: Australia Estudante, Australia Visitante, Canada Estudante, Canada TRV, EUA B1/B2, EUA F1, EUA J1.
- Screenshots citados pelo usuario: os arquivos `screencapture-localhost-8000-viagens-1-formularios-1-visualizar-2026-04-14-15_10_26.png` e `screencapture-localhost-8000-cliente-dashboard-2026-04-14-14_03_30.png` nao foram encontrados pelo nome no workspace.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: regras de pre-preenchimento, replicacao de respostas do principal para dependente, labels "trip" em templates de viagem, testes.
- Fora do escopo: redesenho completo dos formularios, alteracao estrutural dos JSONs, migracoes e reset de banco.

## Arquivos impactados
- `system/services/form_prefill.py`
- `system/services/form_prefill_rules.py`
- `system/views/travel_views.py`
- `templates/travel/create_trip.html`
- `templates/travel/edit_trip.html`
- `templates/travel/list_trips.html`
- `templates/travel/view_destination_country.html`
- `templates/travel/view_visa_type.html`
- `templates/travel/edit_client_form.html`
- `templates/partner_area/view_client.html`
- `templates/client_area/dashboard.html`
- `templates/client/view_client.html`
- `templates/process/create_process.html`
- `system/tests/test_form_prefill.py`
- `system/tests/test_trip_form_replication.py`

## Riscos e edge cases
- Perguntas de "Nome" repetidas em blocos de contato/familia na etapa 1 nao podem receber o nome do aplicante mais de uma vez.
- Perguntas de passaporte e endereco podem estar na etapa 1, mas nao devem ser pre-carregadas automaticamente quando o objetivo e somente dados pessoais iniciais.
- A replicacao do principal deve continuar util para respostas de viagem compartilhadas, mas nao pode copiar dados pessoais do principal para o dependente.
- Respostas ja preenchidas manualmente devem ser preservadas.

## Regras e restricoes (SDD, TDD, MTV, Design Patterns aplicaveis)
- TDD com testes red para os comportamentos criticos.
- Servicos concentram regra de dominio; views apenas orquestram.
- Sem novas dependencias.
- Textos visiveis em pt-BR.

## Criterios de aceite (escritos como assertions testaveis)
- [x] O pre-preenchimento deve preencher apenas dados pessoais diretos da primeira etapa: nome, sobrenome, CPF, data de nascimento, nacionalidade, telefone e e-mail.
- [x] O pre-preenchimento nao deve preencher endereco, passaporte, escola, empregador, contatos, acompanhantes ou perguntas repetidas de nome/telefone/e-mail fora do aplicante.
- [x] A replicacao do principal para dependente nao deve copiar respostas de dados pessoais do principal.
- [x] A replicacao deve preservar respostas ja preenchidas pelo dependente.
- [x] Textos visiveis alterados em templates de viagem/processo nao devem usar "trip" em labels de usuario.
- [x] A suite completa deve permanecer verde.

## Plano (ordenado por dependencia)
- [x] 1. Adicionar testes red para pre-preenchimento restrito e nao duplicado.
- [x] 2. Adicionar teste red para impedir replicacao de campos pessoais do principal.
- [x] 3. Reescrever regras de classificacao de pre-preenchimento com categorias pessoais permitidas.
- [x] 4. Ajustar replicacao para copiar apenas respostas compartilhaveis de viagem.
- [x] 5. Trocar labels "trip" por "viagem".
- [x] 6. Validar com testes, check, collectstatic e verificacao de estaticos.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_form_prefill system.tests.test_trip_form_replication --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py findstatic system/css/home_sections_mobile.css`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py showmigrations system`

## Implementado
- `form_prefill_rules` agora permite somente campos pessoais diretos do aplicante para pre-preenchimento automatico.
- `form_prefill` removeu mapeamentos automaticos de endereco/passaporte e passou a preencher cada categoria pessoal apenas uma vez, preservando respostas existentes.
- A replicacao do principal para dependente ignora a etapa 1 e qualquer pergunta classificada como dado pessoal do cliente, copiando apenas respostas compartilhaveis de viagem.
- Labels visiveis relacionados a "trip" foram convertidos para "viagem" nos templates impactados.
- Testes cobrindo pre-preenchimento restrito, bloqueio de duplicidade, bloqueio de copia de dados pessoais do principal e preservacao de respostas do dependente.

## Desvios do plano
- `findstatic css/base.css` nao se aplica a este projeto porque nao existe `static/css/base.css`; a validacao foi feita no arquivo estatico real `system/css/home_sections_mobile.css`.
- Validacao visual por screenshot nao foi repetida porque os arquivos enviados por nome nao estavam acessiveis no workspace e as telas dependem de sessao/dados locais. O comportamento critico foi coberto por testes automatizados de servico/view.

## Evidencias
- Ambiente: PowerShell com UTF-8 e Python da `.venv` confirmado.
- Django check: `System check identified no issues (0 silenced).`
- Migracoes: `system [X] 0001_initial`.
- Collectstatic: `0 static files copied ... 186 unmodified.`
- Findstatic: `Found 'system/css/home_sections_mobile.css'`.
- Testes focados: 6 testes OK.
- Testes completos: 64 testes OK.
