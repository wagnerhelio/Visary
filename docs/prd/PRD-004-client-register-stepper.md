# PRD-004: Corrigir sequencia visual do cadastro de cliente
## Resumo
Corrigir o componente de etapas da tela `Cadastrar Cliente`, que esta quebrando a visualizacao da sequencia no desktop e no celular.

## Problema atual
O template usa `.etapas-navegacao`, mas o CSS existente estiliza `.stages-navegacao`. O template tambem aplica `.concluida`, enquanto o CSS espera `.completed`. Com isso, a navegacao de etapas fica sem layout correto e as linhas conectores invadem a tela.

## Objetivo
Implementar um stepper responsivo semelhante ao wizard do projeto `lvjiujitsu`, com barra de progresso, itens compactos e leitura correta no mobile.

## Contexto consultado
- Context7: indisponivel nesta sessao.
- Referencia local: `C:\Users\whsf\Documents\GitHub\lvjiujitsu\templates\login\register.html` e `C:\Users\whsf\Documents\GitHub\lvjiujitsu\static\system\css\auth\login.css`.
- Web: MDN `flex-wrap`, usado como referencia de comportamento de flexbox responsivo.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: visual da sequencia de etapas em `templates/client/register_client.html` e CSS namespaced especifico.
- Fora do escopo: regras de negocio do cadastro, persistencia das etapas, campos do formulario e fluxo de dependentes.

## Arquivos impactados
- `templates/client/register_client.html`
- `static/system/css/client_register_wizard.css`
- `system/views/client_views.py`
- `system/tests/test_cep_api.py`

## Riscos e edge cases
- Etapas com nomes longos precisam caber no mobile sem quebrar a pagina.
- Estados ativa/concluida precisam continuar refletindo o contexto atual.
- A tela nao deve gerar overflow horizontal no documento, apenas scroll interno da faixa de etapas quando necessario.

## Regras e restricoes
- CSS especifico em arquivo estatico namespaced.
- Menor mudanca correta, sem alterar a view.
- Texto visivel ao usuario em pt-BR.

## Criterios de aceite
- [x] O stepper de cadastro deve renderizar em uma faixa horizontal consistente no desktop.
- [x] No mobile, a sequencia deve ficar legivel sem conectores atravessando a tela.
- [x] Etapa ativa e etapas concluidas devem ter estado visual distinto.
- [x] `collectstatic --noinput` deve rodar sem erro.
- [x] Suite Django deve passar.

## Plano
- [x] 1. Identificar template e classes quebradas.
- [x] 2. Consultar referencia visual no `lvjiujitsu`.
- [x] 3. Adicionar CSS namespaced para o stepper.
- [x] 4. Ajustar classes do template para estado concluido consistente.
- [x] 5. Validar com Playwright mobile/desktop, estaticos e testes.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py collectstatic --noinput`
- `.\.venv\Scripts\python.exe manage.py findstatic system/css/client_register_wizard.css`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- Criado `static/system/css/client_register_wizard.css` com layout de wizard inspirado no `lvjiujitsu`: barra de progresso, cards de etapa, estado ativo/concluido e scroll horizontal interno no mobile.
- Linkado o CSS em `templates/client/register_client.html`.
- Adicionada barra de progresso com `{% widthratio current_stage.order stages|length 100 %}`.
- Ajustada a classe de etapa concluida para incluir `completed` e preservar `concluida`.
- Restaurada a renderizacao dos campos do cliente: a view agora mapeia campos legados das seeds (`nome`, `cep`, `senha`, etc.) para os nomes reais do `ConsultancyClientForm` (`first_name`, `zip_code`, `password`, etc.).
- O template agora usa `display_fields` e `current_stage`, em vez de variaveis inexistentes como `stage_atual` e `stage_field_obj`, no bloco principal de campos.
- Corrigido o campo de confirmacao de senha: o template agora busca `confirm_password`, nao `confirmar_senha`, no bloco da senha.
- Corrigido o CEP na etapa de Endereco:
  - API `api_search_zip` aceita `zip_code` e tambem o parametro legado `cep`.
  - JS principal chama `?zip_code=...`, nao `?cep=...`.
  - Script de CEP agora e emitido com `display_fields`, nao com a variavel inexistente `stage_field_obj`.
  - Seletores corrigidos para os campos reais `street`, `district`, `city` e `state`.
  - Mapeamento das seeds corrigido para `complemento -> complement` e `cidade -> city`.
  - Criados testes `system/tests/test_cep_api.py` para cobrir os parametros `zip_code` e `cep`.
- Evidencia adicional:
  - Playwright mobile encontrou 12 controles no form principal, 11 visiveis, incluindo `Assessor responsável`, `Nome`, `Sobrenome`, `CPF`, `Data de nascimento`, `Nacionalidade` e telefones.
  - Screenshot: `docs/prd/PRD-004-client-register-fields-mobile.png`.
  - Playwright mobile confirmou `confirm_password` visivel, label `Confirme a senha *` presente e avanço da etapa 1 para `Etapa 2: Endereço` sem o erro `Confirme a senha: Este campo é obrigatório`.
  - Screenshot: `docs/prd/PRD-004-client-register-confirm-password-mobile.png`.
  - Busca real de CEP via tela com `01001-000` preencheu `Praça da Sé`, `Sé`, `São Paulo` e `SP`.
  - Screenshot: `docs/prd/PRD-004-client-register-cep-mobile.png`.
- Evidencias Playwright:
  - mobile 390x844: `documentScrollWidth=390`, `cssLoaded=True`, `navDisplay='flex'`, `navOverflowX='auto'`, `afterContent='none'`, `activeCount=1`, `stepCount=4`.
  - desktop 1440x900: `documentScrollWidth=1440`, `cssLoaded=True`, `navDisplay='grid'`, `afterContent='none'`, `activeCount=1`, `stepCount=4`.
  - screenshots: `docs/prd/PRD-004-client-register-mobile.png` e `docs/prd/PRD-004-client-register-desktop.png`.
- Validacao:
  - `collectstatic --noinput`: 1 arquivo copiado, 182 inalterados.
  - rodada final de `collectstatic --noinput`: 0 arquivos copiados, 183 inalterados.
  - `findstatic system/css/client_register_wizard.css`: encontrado.
  - `manage.py check`: sem issues.
  - `manage.py test system.tests.test_cep_api --verbosity 2`: 2 testes OK.
  - `manage.py test --verbosity 2`: 31 testes OK.

## Desvios do plano
- nenhum
