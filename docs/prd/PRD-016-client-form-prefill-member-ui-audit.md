# PRD-016: Auditoria de pre-preenchimento, formulario do membro e avisos visuais

## Resumo
Corrigir a area do cliente e a visualizacao de formularios para que cada membro abra o proprio formulario, os dados do cadastro do cliente preencham somente campos com vinculo real, e perguntas opcionais sem resposta nao exibam aviso de pendencia.

## Problema atual
- No dashboard do cliente, todos os botoes de "Preencher Formulario" apontam apenas para a viagem. Ao clicar no dependente, o formulario aberto ainda usa o cliente logado/principal, por isso os dados do membro nao aparecem.
- O pre-preenchimento automatico ficou restrito a poucos campos pessoais e nao usa campos existentes no cadastro, como endereco e passaporte, quando a pergunta do formulario representa claramente o proprio aplicante.
- A visualizacao administrativa do formulario exibe aviso de pergunta nao respondida tambem para perguntas opcionais.
- A tela de visualizacao nao tem um marcador visual claro por pergunta preenchida.

## Objetivo
Garantir que o formulario aberto seja sempre do membro selecionado, que o pre-preenchimento seja feito por uma matriz explicita de campos por seed, e que a UI diferencie visualmente campos preenchidos sem alertar perguntas opcionais vazias.

## Contexto consultado
- `CLAUDE.md`: app unico `system`, rotas em pt-BR e dominio concentrado em services/views.
- `system/models/client_models.py`: campos reais disponiveis no cadastro do cliente.
- `static/forms_ini/*.json`: seeds atuais de formularios.
- `system/services/form_prefill.py` e `system/services/form_prefill_rules.py`: regra atual de pre-preenchimento.
- `templates/client_area/dashboard.html`: links de membro.
- `templates/client_area/view_form.html`: preenchimento do cliente.
- `templates/travel/view_client_form.html`: visualizacao administrativa do formulario.
- Web/Context7: nao usado; correcao depende dos JSONs locais e do dominio do projeto.

## Dados do cadastro disponiveis para pre-preenchimento
- Dados pessoais: `first_name`, `last_name`, `cpf`, `birth_date`, `nationality`, `phone`, `secondary_phone`, `email`.
- Endereco residencial: `zip_code`, `street`, `street_number`, `complement`, `district`, `city`, `state`.
- Passaporte: `passport_type`, `passport_number`, `passport_issuing_country`, `passport_issue_date`, `passport_expiry_date`, `passport_authority`, `passport_issuing_city`, `passport_stolen`.
- Nao existem no cadastro: sexo, estado civil, cidade/estado/pais de nascimento, nomes anteriores, redes sociais, dados de pais/conjuge/filhos, escola, empregador, historico de viagens, respostas consulares, CASV/consulado.

## Auditoria por formulario seed

### FORMULARIO_AUSTRALIA_ESTUDANTE.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `Data de Nascimento (Dia/Mes/Ano)` -> `birth_date`
- `Nacionalidade` -> `nationality`
- `CPF` -> `cpf`
- `Passaporte` -> `passport_number`
- `Pais da Emissao` -> `passport_issuing_country`
- `Data de emissao do passaporte` -> `passport_issue_date`
- `Data de validade do passaporte` -> `passport_expiry_date`
- `Endereco completo` -> endereco residencial completo
- `Cidade e estado em que reside` -> `city`/`state`
- `CEP` -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
Nao preencher: nascimento local, estado civil, contato emergencial, empregador/escola, supervisor, endereco/telefone de terceiros, dividas e perguntas consulares.

### FORMULARIO_AUSTRALIA_VISITANTE.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `CPF` -> `cpf`
- `Data de Nascimento (Dia/Mes/Ano)` -> `birth_date`
- `Endereco residencial completo` -> endereco residencial completo
- `Cep` -> `zip_code`
- `Telefone residencial` -> `phone`
- `Telefone celular` -> `phone`
- `E-mail` -> `email`
- `Numero do Passaporte` -> `passport_number`
- `Pais da Emissao` -> `passport_issuing_country`
- `Qual a sua nacionalidade` -> `nationality`
- `Data de emissao do passaporte` -> `passport_issue_date`
- `Data de validade do passaporte` -> `passport_expiry_date`
- `Local de emissao / autoridade emissora` -> `passport_authority`
Nao preencher: cidade/estado/pais de nascimento, estado civil, conjuge, empregador/escola, contatos, acompanhantes, filhos, vistos anteriores e perguntas consulares.

### FORMULARIO_CANADA_ESTUDANTE.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `CPF` -> `cpf`
- `Data de Nascimento (Dia/Mes/Ano)` -> `birth_date`
- `Numero do Passaporte` -> `passport_number`
- `Pais referente ao passaporte` -> `passport_issuing_country`
- `Data de emissao do passaporte` -> `passport_issue_date`
- `Data de expiracao do passaporte` -> `passport_expiry_date`
- `Endereco completo` -> endereco residencial completo
- `Bairro` -> `district`
- `CEP` -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
Nao preencher: cidade/estado/pais de nascimento, estado civil, conjuge, instituicao de ensino, empregador, pais/mae e acompanhantes.

### FORMULARIO_CANADA_TRV.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `CPF` -> `cpf`
- `Data de Nascimento (Dia/Mes/Ano)` -> `birth_date`
- `Numero do Passaporte` -> `passport_number`
- `Pais referente ao passaporte` -> `passport_issuing_country`
- `Data de emissao do passaporte` -> `passport_issue_date`
- `Data de expiracao do passaporte` -> `passport_expiry_date`
- `Endereco completo` -> endereco residencial completo
- `Bairro` -> `district`
- `CEP` -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
Nao preencher: cidade/estado/pais de nascimento, estado civil, conjuge, pessoa/instituicao visitada, instituicao de ensino, empregador, pais/mae e acompanhantes.

### FORMULARIO_EUA_B1_B2.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `Data de Nascimento` -> `birth_date`
- `Pais de Nacionalidade` -> `nationality`
- `CPF` -> `cpf`
- `Endereco(rua/quadra/avenida)` -> `street`/`street_number`/`complement`
- `Bairro` -> `district`
- `CEP` -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
- `Tipo de Passaporte` -> `passport_type`
- `Numero do Passaporte Valido` -> `passport_number`
- `Pais que emitiu o passaporte` -> `passport_issuing_country`
- `Orgao Emissor` -> `passport_authority`
- `Cidade onde foi emitido` -> `passport_issuing_city`
- `Data de Emissao` -> `passport_issue_date`
- `Valido ate` -> `passport_expiry_date`
- `Ja teve algum passaporte roubado?` -> `passport_stolen`
Nao preencher: sexo, estado civil, cidade/estado/pais de nascimento, endereco nos EUA, telefone de trabalho, redes sociais, parente nos EUA, conjuge, pais, empregador/escola, supervisor, instituicao, seguranca e agendamento.

### FORMULARIO_EUA_F1.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `Data de Nascimento` -> `birth_date`
- `CPF` -> `cpf`
- `Endereco(rua/quadra/avenida)` -> `street`/`street_number`/`complement`
- `Bairro` -> `district`
- `CEP` residencial -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
Nao preencher: estado civil, cidade natal/estado, endereco alternativo, dados da escola, contatos, endereco/telefone/email de contatos, redes sociais e endereco nos EUA.

### FORMULARIO_EUA_J1.json
Preencher do cadastro:
- `Sobrenome` -> `last_name`
- `Nome` -> `first_name`
- `Data de Nascimento` -> `birth_date`
- `CPF` -> `cpf`
- `Endereco(rua/quadra/avenida)` -> `street`/`street_number`/`complement`
- `Bairro` -> `district`
- `CEP` residencial -> `zip_code`
- `Telefone Primario` -> `phone`
- `Telefone Secundario` -> `secondary_phone`
- `E-mail` -> `email`
Nao preencher: estado civil, cidade natal/estado, endereco alternativo, dados da escola, contatos, endereco/telefone/email de contatos, redes sociais e endereco nos EUA.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: matriz de pre-preenchimento, abertura/salvamento de formulario do membro selecionado na area do cliente, avisos/indicadores da visualizacao de formulario.
- Fora do escopo: adicionar novos campos ao cadastro, reescrever os JSONs de seed, alterar login/autenticacao.

## Arquivos impactados
- `system/services/form_prefill_rules.py`
- `system/services/form_prefill.py`
- `system/views/client_area_views.py`
- `templates/client_area/dashboard.html`
- `templates/client_area/view_form.html`
- `templates/travel/view_client_form.html`
- `system/tests/test_form_prefill.py`
- `system/tests/test_client_area_dashboard.py`

## Riscos e edge cases
- Campos genericos como `Cidade`, `Estado`, `Nome` e `Telefone` aparecem em blocos de terceiros. So devem ser preenchidos quando a regra e direta ou quando a duplicidade for controlada pelo servico.
- Campo opcional sem resposta nao e erro e nao deve gerar aviso visual de pendencia.
- O cliente principal pode preencher dependentes apenas quando o vinculo `trip_primary_client` aponta para ele.
- Respostas existentes nao podem ser sobrescritas pelo pre-preenchimento.

## Criterios de aceite
- [x] O dashboard do cliente deve abrir o formulario do membro selecionado, principal ou dependente.
- [x] O salvamento na area do cliente deve persistir respostas para o membro selecionado.
- [x] Cada seed deve preencher somente os campos listados na auditoria deste PRD.
- [x] Campos de terceiros, empregador, escola, familia, acompanhantes e contatos nao devem receber dados do aplicante.
- [x] Perguntas opcionais sem resposta nao devem exibir aviso amarelo de pendencia na visualizacao.
- [x] Perguntas preenchidas devem ter marcador visual verde/claro.
- [x] Testes automatizados devem cobrir pre-preenchimento, membro selecionado e UI renderizada.

## Plano
- [x] 1. Adicionar testes red para membro dependente na area do cliente.
- [x] 2. Adicionar testes red para pre-preenchimento de endereco/passaporte e bloqueio de terceiros.
- [x] 3. Ajustar service de pre-preenchimento com matriz conservadora.
- [x] 4. Ajustar views/templates da area do cliente para `client_id` do membro selecionado.
- [x] 5. Ajustar visualizacao para marcador verde e aviso apenas em obrigatorias.
- [x] 6. Rodar testes focados, check, collectstatic e suite completa.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_form_prefill system.tests.test_client_area_dashboard --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- `form_prefill_rules` passou a mapear campos diretos de endereco residencial e passaporte do aplicante, mantendo bloqueio para terceiros, escola, empregador, familia, acompanhantes e contatos.
- `form_prefill` passou a montar endereco residencial, cidade/UF, labels de passaporte e datas de passaporte, preservando respostas existentes.
- `form_prefill` tambem impede `Endereco completo` generico de ser preenchido depois que endereco residencial ja foi identificado por rua/bairro/CEP, evitando preencher blocos de contato nos formularios F1/J1.
- Dashboard da area do cliente agora envia `client_id` no link do membro selecionado.
- `client_view_form` e `client_save_answer` agora resolvem o cliente-alvo da viagem e permitem que o principal preencha o dependente vinculado.
- `client_area/view_form.html` inclui `client_id` escondido, informa quando o formulario e de dependente e marca visualmente campos preenchidos em verde.
- `travel/view_client_form.html` mostra marcador verde `Campo preenchido` e exibe aviso amarelo somente para pergunta obrigatoria sem resposta.
- Corrigido o JS de regra condicional da area do cliente para ler `data-ordem`, que era o atributo realmente renderizado.

## Desvios do plano
- Nao foram alterados os JSONs de seed. A correcao fica na matriz de pre-preenchimento e no controle de duplicidade do service.
- A auditoria automatica lista candidatos por texto; o service ainda aplica regra de ordem/duplicidade. Por isso `Endereco completo` de contato em F1/J1 pode ser candidato textual, mas nao e salvo quando rua/bairro/CEP residencial ja foram preenchidos.

## Evidencias
- Red: testes novos falharam antes da implementacao para dependente selecionado, endereco/passaporte e UI.
- Focados: `.\.venv\Scripts\python.exe manage.py test system.tests.test_form_prefill system.tests.test_client_area_dashboard system.tests.test_trip_form_replication --verbosity 2` retornou 17 testes OK.
- Check: `.\.venv\Scripts\python.exe manage.py check` retornou `System check identified no issues (0 silenced).`
- Estaticos: `.\.venv\Scripts\python.exe manage.py collectstatic --noinput` retornou `0 static files copied ... 186 unmodified.`
- Suite completa: `.\.venv\Scripts\python.exe manage.py test --verbosity 2` retornou 74 testes OK.
