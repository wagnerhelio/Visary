# Visary - Sistema de Gestão de Consultoria de Vistos

Sistema web completo para gestão de consultoria de vistos, desenvolvido em Django. Permite gerenciar clientes, viagens, processos de visto, formulários dinâmicos, parceiros e controle financeiro.

## 📋 Índice

- [Sobre o Projeto](#sobre-o-projeto)
- [Tecnologias](#tecnologias)
- [Funcionalidades](#funcionalidades)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Instalação e Configuração](#instalação-e-configuração)
- [Execução](#execução)
- [Modelos e Estrutura de Dados](#modelos-e-estrutura-de-dados)
- [Sistema de Permissões](#sistema-de-permissões)
- [APIs Disponíveis](#apis-disponíveis)
- [Comandos Personalizados](#comandos-personalizados)

## 🎯 Sobre o Projeto

O **Visary** é uma plataforma completa para empresas de consultoria de vistos gerenciarem todo o ciclo de vida dos processos de visto dos seus clientes. O sistema permite:

- Cadastro e gestão de clientes com etapas configuráveis
- Organização de viagens por país e tipo de visto
- Acompanhamento de processos com checklist de etapas
- Formulários dinâmicos por tipo de visto
- Área do cliente para preenchimento de formulários
- Gestão de parceiros indicadores
- Controle financeiro por viagem
- Sistema de permissões e perfis de usuário

## 🛠 Tecnologias

- **Django 5.2.8** - Framework web Python
- **Python 3.x** - Linguagem de programação
- **SQLite** - Banco de dados (desenvolvimento)
- **HTML/CSS/JavaScript** - Frontend
- **Bibliotecas Python:**
  - `brazilcep` - Busca de CEP
  - `pycep-correios` - Busca alternativa de CEP
  - `requests` - Requisições HTTP
  - `django-environ` - Gerenciamento de variáveis de ambiente

## ✨ Funcionalidades

### 1. Gestão de Clientes

- **Cadastro de Clientes**: Sistema de cadastro em etapas configuráveis
  - Dados pessoais (nome, data de nascimento, nacionalidade, contatos)
  - Endereço completo com busca automática por CEP
  - Gestão de dependentes (vínculo cliente principal/dependente)
  - Dados de passaporte
  - Observações e histórico

- **Etapas Configuráveis**: Sistema flexível de etapas de cadastro
  - Etapas personalizáveis com campos configuráveis
  - Tipos de campo: texto, data, número, booleano, seleção
  - Controle de campos obrigatórios
  - Acompanhamento de progresso por etapa

- **Área do Cliente**: Portal para clientes preencherem seus dados
  - Dashboard com viagens vinculadas
  - Formulários de visto por viagem
  - Acompanhamento de status do processo

### 2. Gestão de Viagens

- **Países de Destino**: Cadastro e gestão de países
- **Tipos de Visto**: Tipos específicos por país
- **Viagens**: Organização de viagens
  - Associação de país e tipo de visto
  - Datas previstas de viagem e retorno
  - Valor da assessoria
  - Vínculo de múltiplos clientes
  - Status disponíveis para processos

### 3. Processos de Visto

- **Processos**: Processo único por cliente/viagem
  - Checklist de etapas configurável por viagem
  - Status personalizáveis por tipo de visto
  - Prazos por etapa
  - Controle de conclusão
  - Cálculo de progresso percentual

- **Status de Processo**: Status reutilizáveis
  - Vinculação opcional a tipo de visto
  - Prazo padrão em dias
  - Ordem de exibição
  - Status ativo/inativo

### 4. Formulários Dinâmicos

- **Formulários de Visto**: Formulários por tipo de visto
  - Um formulário por tipo de visto
  - Perguntas configuráveis com ordem
  - Tipos de campo: texto, data, número, booleano, seleção
  - Campos obrigatórios/opcionais
  - Opções de seleção para campos do tipo seleção

- **Respostas**: Armazenamento de respostas dos clientes
  - Respostas por cliente/viagem/pergunta
  - Tipos de resposta conforme tipo de pergunta
  - Edição e exclusão de respostas

### 5. Gestão de Parceiros

- **Parceiros**: Cadastro de parceiros indicadores
  - Dados do responsável e empresa
  - CPF/CNPJ
  - Segmento (Agência de Viagem, Consultoria, Advocacia, Educação, Outros)
  - Controle de ativação
  - Vínculo com clientes indicados

### 6. Controle Financeiro

- **Registros Financeiros**: Por viagem e cliente
  - Valores e datas de pagamento
  - Status: Pendente, Pago, Cancelado
  - Dar baixa em pagamentos
  - Observações

### 7. Sistema de Permissões

- **Módulos**: Organização funcional do sistema
- **Perfis**: Grupos de permissões
  - Permissões CRUD (criar, visualizar, atualizar, excluir)
  - Vínculo com módulos acessíveis
- **Usuários**: Usuários da consultoria com perfil
  - Autenticação própria (não usa Django User diretamente)
  - Senhas com hash
  - Controle de acesso baseado em perfil

### 8. Administração

- Gestão de usuários da consultoria
- Gestão de perfis e permissões
- Gestão de módulos
- Superusuário Django para acesso ao admin

## 📁 Estrutura do Projeto

```
Visary/
├── visary/                    # Aplicação principal
│   ├── consultancy/          # App de consultoria (domínio principal)
│   │   ├── models/          # Modelos de dados
│   │   │   ├── client_models.py
│   │   │   ├── travel_models.py
│   │   │   ├── process_models.py
│   │   │   ├── form_models.py
│   │   │   ├── partners_models.py
│   │   │   ├── financial_models.py
│   │   │   └── etapa_models.py
│   │   ├── forms/           # Formulários Django
│   │   ├── services/        # Serviços (ex: busca CEP)
│   │   └── migrations/      # Migrações do banco
│   ├── system/              # App de sistema (usuários, permissões)
│   │   ├── models/         # Modelos de permissão
│   │   ├── views/          # Views do sistema
│   │   ├── forms/          # Formulários de sistema
│   │   ├── management/     # Comandos personalizados
│   │   └── migrations/
│   ├── templates/          # Templates HTML
│   │   ├── admin/
│   │   ├── client/
│   │   ├── forms/
│   │   ├── partners/
│   │   ├── process/
│   │   ├── travel/
│   │   └── ...
│   ├── static/             # Arquivos estáticos
│   │   ├── logo/
│   │   ├── icons/
│   │   ├── forms_ini/     # Formulários iniciais (JSON)
│   │   └── etapas_cliente_ini/  # Etapas iniciais (JSON)
│   ├── visary/            # Configurações Django
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── ...
│   └── manage.py
├── requirements.txt        # Dependências Python
├── .env_exemple          # Exemplo de variáveis de ambiente
└── README.md
```

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.8+
- pip
- Virtual environment (recomendado)

### Passo a Passo

1. **Clone o repositório** (ou acesse o diretório do projeto)

2. **Crie e ative um ambiente virtual:**

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/Mac
source .venv/bin/activate
```

3. **Instale as dependências:**

```bash
pip install -r requirements.txt
```

4. **Configure as variáveis de ambiente:**

Crie um arquivo `.env` baseado em `.env_exemple` e configure:

```env
SECRET_KEY=sua-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=*
SYSTEM_SEED_PROFILES=[...]  # JSON com perfis iniciais
```

5. **Execute as migrações:**

```bash
cd visary
python manage.py makemigrations
python manage.py migrate
```

6. **Crie o superusuário inicial:**

```bash
python manage.py criar_superuser_admin
```

Este comando cria/atualiza o usuário:
- **Username:** `admin`
- **Email:** `admin@admin.com`
- **Senha:** `admin`

⚠️ **Importante:** Altere a senha em produção!

7. **Carregue dados iniciais** (se houver fixtures ou comandos personalizados):

O sistema pode carregar automaticamente:
- Formulários iniciais de `static/forms_ini/`
- Etapas iniciais de `static/etapas_cliente_ini/`
- Módulos e perfis baseados em `SYSTEM_SEED_PROFILES`

## ▶️ Execução

### Servidor de Desenvolvimento

```bash
# Ative o ambiente virtual (se ainda não estiver ativo)
.\.venv\Scripts\Activate.ps1  # Windows
# ou
source .venv/bin/activate     # Linux/Mac

# Entre no diretório visary
cd visary

# Execute o servidor
python manage.py runserver 0.0.0.0:8000
```

O sistema estará disponível em: `http://localhost:8000`

### Acesso Inicial

- **URL:** http://localhost:8000
- **Login:** `admin` / `admin`
- Após login, você será redirecionado para a home do sistema

## 📊 Modelos e Estrutura de Dados

### Consultancy App

#### ClienteConsultoria
- Informações pessoais, contato, endereço
- Senha para área do cliente (hash)
- Assessor responsável (UsuarioConsultoria)
- Parceiro indicador (opcional)
- Cliente principal (para dependentes)
- Etapas de cadastro (booleanos)
- Dados de passaporte

#### Viagem
- País de destino e tipo de visto
- Datas previstas
- Valor da assessoria
- Múltiplos clientes (via ClienteViagem)
- Status disponíveis para processos

#### Processo
- Vínculo único: viagem + cliente
- Checklist de etapas (EtapaProcesso)
- Progresso calculado automaticamente

#### FormularioVisto
- Um formulário por TipoVisto
- Perguntas ordenadas (PerguntaFormulario)
- Respostas por cliente/viagem (RespostaFormulario)

#### Partner
- Dados de parceiros que indicam clientes
- Segmento e localização
- Controle de ativação

#### Financeiro
- Registros financeiros por viagem
- Cliente opcional
- Status: Pendente, Pago, Cancelado

### System App

#### Modulo
- Módulos funcionais do sistema
- Ordem de exibição
- Controle de ativação

#### Perfil
- Grupos de permissões
- Permissões CRUD
- Módulos acessíveis

#### UsuarioConsultoria
- Usuários internos da consultoria
- Autenticação própria (não Django User)
- Vinculado a um Perfil

## 🔐 Sistema de Permissões

O sistema utiliza um modelo de permissões baseado em:

1. **Módulos**: Funcionalidades do sistema (ex: Clientes, Viagens, Processos)
2. **Perfis**: Grupos de permissões com permissões CRUD
3. **Usuários**: Vinculados a um perfil

### Permissões por Perfil

- `pode_criar`: Criar novos registros
- `pode_visualizar`: Visualizar registros (padrão: True)
- `pode_atualizar`: Editar registros
- `pode_excluir`: Excluir registros

### Configuração Inicial

Os perfis são definidos via variável de ambiente `SYSTEM_SEED_PROFILES` (JSON):

```json
[
  {
    "nome": "Administrador",
    "descricao": "Acesso total ao sistema",
    "pode_criar": true,
    "pode_visualizar": true,
    "pode_atualizar": true,
    "pode_excluir": true,
    "ativo": true
  },
  {
    "nome": "Assessor",
    "descricao": "Gestão de clientes e processos",
    "pode_criar": true,
    "pode_visualizar": true,
    "pode_atualizar": true,
    "pode_excluir": false,
    "ativo": true
  }
]
```

## 🌐 APIs Disponíveis

### APIs de Dados

- **`/api/buscar-cep/`**: Busca endereço por CEP
  - Método: GET
  - Parâmetro: `cep`
  - Retorna: JSON com logradouro, bairro, cidade, UF

- **`/api/tipos-visto/`**: Lista tipos de visto por país
  - Método: GET
  - Parâmetro: `pais_id`
  - Retorna: JSON com tipos de visto

- **`/api/clientes-viagem/`**: Clientes de uma viagem
  - Método: GET
  - Parâmetro: `viagem_id`
  - Retorna: JSON com lista de clientes

- **`/api/status-processo/`**: Status de processo por tipo de visto
  - Método: GET
  - Parâmetro: `tipo_visto_id`
  - Retorna: JSON com status disponíveis

- **`/api/prazo-status-processo/`**: Prazo padrão de um status
  - Método: GET
  - Parâmetro: `status_id`
  - Retorna: JSON com prazo em dias

- **`/api/cliente-info/`**: Informações de um cliente
  - Método: GET
  - Parâmetro: `cliente_id`
  - Retorna: JSON com dados do cliente

### Área do Cliente

- **`/cliente/dashboard/`**: Dashboard do cliente
- **`/cliente/viagem/<id>/formulario/`**: Visualizar formulário da viagem
- **`/cliente/viagem/<id>/salvar-resposta/`**: Salvar resposta do formulário

## 🔧 Comandos Personalizados

### criar_superuser_admin

Cria ou atualiza o superusuário padrão do Django:

```bash
python manage.py criar_superuser_admin
```

**Credenciais padrão:**
- Username: `admin`
- Email: `admin@admin.com`
- Senha: `admin`

⚠️ **Altere a senha em produção!**

## 📝 Funcionalidades Detalhadas

### Busca de CEP

O sistema utiliza múltiplas fontes para busca de CEP com fallback automático:

1. ViaCEP (API pública)
2. BrasilAPI (API pública)
3. pycep-correios (biblioteca)
4. brazilcep (biblioteca)

Implementado em: `consultancy/services/cep.py`

### Formulários Dinâmicos

- Criação de formulários por tipo de visto
- Perguntas ordenadas com tipos variados
- Validação de campos obrigatórios
- Opções de seleção configuráveis
- Respostas persistidas por cliente/viagem

### Processos com Checklist

- Etapas configuráveis por viagem
- Status reutilizáveis por tipo de visto
- Prazos por etapa
- Cálculo automático de progresso
- Controle de conclusão com data

### Área do Cliente

- Portal autenticado para clientes
- Visualização de viagens vinculadas
- Preenchimento de formulários de visto
- Acompanhamento de processos

## 🔒 Segurança

- Senhas armazenadas com hash (Django hashers)
- Proteção CSRF em formulários
- Autenticação de usuários
- Controle de acesso por perfil
- Validação de permissões nas views

## 📌 Observações

- **Banco de dados:** SQLite (desenvolvimento). Configure PostgreSQL/MySQL para produção.
- **Arquivos estáticos:** Em desenvolvimento, servidos automaticamente. Configure para produção.
- **DEBUG:** Mantenha `False` em produção.
- **SECRET_KEY:** Gere uma nova chave secreta para produção.

## 🐛 Troubleshooting

### Problemas comuns

1. **Erro ao buscar CEP:**
   - Verifique conexão com internet
   - O sistema tenta múltiplas fontes automaticamente

2. **Migrações não aplicadas:**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

3. **Erro de permissões:**
   - Verifique se o perfil do usuário tem as permissões necessárias
   - Verifique se os módulos estão vinculados ao perfil

4. **Erro ao criar superusuário:**
   - Verifique se o banco de dados foi criado (migrate)
   - Verifique se não há conflito com usuário existente

## 📄 Licença

Este projeto é privado/proprietário.

## 👥 Contato

Para dúvidas ou suporte, entre em contato com a equipe de desenvolvimento.

---

**Versão:** 1.0  
**Última atualização:** Janeiro 2026

clear; python cleanup.py; python manage.py makemigrations; python manage.py migrate; python manage.py criar_superuser_admin; python manage.py criar_seeds_test; python manage.py runserver 0.0.0.0:8000

clear; python cleanup.py; python manage.py makemigrations; python manage.py migrate; python manage.py criar_superuser_admin; python manage.py runserver 0.0.0.0:8000