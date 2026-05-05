# PRD-015: Redirecionamento de formularios inexistentes apos reset

## Resumo
Corrigir o acesso a URLs antigas de formulario de viagem quando o banco foi resetado ou quando a viagem/cliente/vinculo nao existe mais.

## Problema atual
Depois de autenticar, uma URL como `/viagens/1/formularios/1/visualizar/` pode cair em 404 se a viagem ou o cliente nao existir mais. Para uso operacional, esse erro deve voltar para a home com mensagem clara, evitando tela tecnica de erro.

## Objetivo
Ao acessar formulario de viagem inexistente, cliente inexistente ou cliente nao vinculado a viagem, redirecionar para a home e exibir mensagem de erro em pt-BR.

## Contexto consultado
- `CLAUDE.md`: projeto Django, app unico `system`, rotas em pt-BR.
- `system/urls.py`: rota `view_client_form`.
- `system/views/travel_views.py`: view usa `get_object_or_404` e `PermissionDenied`.
- Web/Context7: nao necessario; correcao local de fluxo Django.

## Dependencias adicionadas
- nenhuma

## Escopo / Fora do escopo
- Escopo: tela de visualizacao de formulario de viagem.
- Fora do escopo: middleware global de erro 404/403, redesign visual, alteracao de seed/reset.

## Arquivos impactados
- `system/views/travel_views.py`
- `system/tests/test_trip_form_replication.py`

## Riscos e edge cases
- Redirecionar para uma pagina protegida sem usuario autenticado nao deve quebrar o fluxo de login.
- Nao esconder erro de permissao real como sucesso; deve aparecer mensagem de erro.
- A view de edicao/exclusao ainda pode precisar de politica semelhante em demanda separada.

## Regras e restricoes
- TDD: adicionar teste primeiro.
- View deve continuar fina e sem alterar regras de preenchimento de formulario.
- Mensagem visivel em pt-BR.

## Criterios de aceite
- [x] Usuario autenticado acessando formulario com viagem inexistente deve ser redirecionado para a home.
- [x] Usuario autenticado acessando formulario com cliente inexistente deve ser redirecionado para a home.
- [x] Usuario autenticado acessando formulario de cliente nao vinculado a viagem deve ser redirecionado para a home.
- [x] O redirecionamento deve adicionar mensagem de erro em pt-BR.
- [x] Testes automatizados devem passar.

## Plano
- [x] 1. Criar testes red para viagem inexistente, cliente inexistente e vinculo inexistente.
- [x] 2. Ajustar `view_client_form` para buscar objetos com `.filter().first()` e redirecionar com `messages.error`.
- [x] 3. Rodar testes focados.
- [x] 4. Rodar validacao Django e suite completa.

## Comandos de validacao
- `.\.venv\Scripts\python.exe manage.py test system.tests.test_trip_form_replication --verbosity 2`
- `.\.venv\Scripts\python.exe manage.py check`
- `.\.venv\Scripts\python.exe manage.py test --verbosity 2`

## Implementado
- `view_client_form` agora redireciona para `system:home` com `messages.error` quando a viagem nao existe.
- `view_client_form` agora redireciona para `system:home` com `messages.error` quando o cliente nao existe.
- `view_client_form` agora redireciona para `system:home` com `messages.error` quando o cliente nao esta vinculado a viagem.
- As mensagens visiveis foram mantidas em pt-BR com acentuacao: "Formulário de viagem não encontrado.", "Cliente não encontrado para este formulário." e "Este cliente não está vinculado a esta viagem."
- `edit_client_form` tambem recebeu a mesma protecao para cliente inexistente ou nao vinculado, evitando stack trace/403 em URLs antigas de edicao.
- Testes adicionados em `system/tests/test_trip_form_replication.py`.

## Desvios do plano
- Nao houve alteracao de estaticos; `collectstatic` nao foi necessario nesta correcao.

## Evidencias
- Red: testes novos falharam com 404/403 antes da correcao.
- Focado: `.\.venv\Scripts\python.exe manage.py test system.tests.test_trip_form_replication --verbosity 2` retornou 5 testes OK.
- Check: `.\.venv\Scripts\python.exe manage.py check` retornou `System check identified no issues (0 silenced).`
- Suite completa: `.\.venv\Scripts\python.exe manage.py test --verbosity 2` retornou 67 testes OK.
