import datetime
import json
import os

from django.conf import settings
from django.contrib.auth.models import User

from consultancy.models import (
    ClienteConsultoria,
    EtapaProcesso,
    Financeiro,
    FormularioVisto,
    OpcaoSelecao,
    PaisDestino,
    Partner,
    PerguntaFormulario,
    Processo,
    RespostaFormulario,
    StatusFinanceiro,
    StatusProcesso,
    TipoVisto,
    Viagem,
)
from system.models import UsuarioConsultoria


FORMS_INI_DIR = os.path.join(settings.BASE_DIR, "static", "forms_ini")


def get_admin_user():
    admin, _ = User.objects.get_or_create(
        username="admin",
        defaults={"email": "admin@visary.com", "is_staff": True, "is_superuser": True},
    )
    return admin


def get_assessor(email):
    return UsuarioConsultoria.objects.filter(email=email).first()


def cpf_valido(seed: str) -> str:
    import hashlib
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    digits = str(h % 10**9).zfill(9)

    def digito(d):
        w = len(d) + 1
        s = sum(int(x) * (w - i) for i, x in enumerate(d))
        r = s % 11
        return "0" if r < 2 else str(11 - r)

    d1 = digito(digits)
    d2 = digito(digits + d1)
    raw = digits + d1 + d2
    return f"{raw[:3]}.{raw[3:6]}.{raw[6:9]}-{raw[9:]}"


def criar_cliente(assessor, admin_user, nome, cpf_seed, data_nasc, email="", telefone="(62) 99999-0001", parceiro=None):
    cpf = cpf_valido(cpf_seed)
    cliente, _ = ClienteConsultoria.objects.get_or_create(
        cpf=cpf,
        defaults={
            "nome": nome,
            "email": email,
            "assessor_responsavel": assessor,
            "data_nascimento": data_nasc,
            "nacionalidade": "Brasileira",
            "telefone": telefone,
            "criado_por": admin_user,
            "parceiro_indicador": parceiro,
        },
    )
    cliente.set_password("visary123")
    cliente.save()
    return cliente


def criar_dependente(principal, assessor, admin_user, nome, cpf_seed, data_nasc, email=""):
    cpf = cpf_valido(cpf_seed)
    dep, _ = ClienteConsultoria.objects.get_or_create(
        cpf=cpf,
        defaults={
            "nome": nome,
            "email": email,
            "assessor_responsavel": assessor,
            "data_nascimento": data_nasc,
            "nacionalidade": "Brasileira",
            "telefone": "(62) 99999-0002",
            "criado_por": admin_user,
            "cliente_principal": principal,
        },
    )
    dep.set_password("visary123")
    dep.save()
    return dep


def obter_ou_criar_viagem(assessor, admin_user, pais_nome, visto_nome, data_viagem, data_retorno, valor):
    pais = PaisDestino.objects.filter(nome=pais_nome).first()
    if not pais:
        raise ValueError(f"Pais nao encontrado: {pais_nome}. Execute seed_test_infra primeiro.")
    tipo_visto = TipoVisto.objects.filter(pais_destino=pais, nome=visto_nome).first()
    if not tipo_visto:
        raise ValueError(f"Tipo de visto nao encontrado: {visto_nome}. Execute seed_test_infra primeiro.")
    viagem, _ = Viagem.objects.get_or_create(
        assessor_responsavel=assessor,
        tipo_visto=tipo_visto,
        data_prevista_viagem=data_viagem,
        defaults={
            "pais_destino": pais,
            "data_prevista_retorno": data_retorno,
            "valor_assessoria": valor,
            "criado_por": admin_user,
        },
    )
    return viagem


def adicionar_cliente_viagem(viagem, cliente, visto_individual=None):
    viagem.clientes.add(cliente)
    if visto_individual:
        from consultancy.models import ClienteViagem
        cv = viagem.clienteviagem_set.filter(cliente=cliente).first()
        if cv:
            cv.tipo_visto = visto_individual
            cv.save()


def criar_financeiro(viagem, cliente, assessor, admin_user, valor, status):
    fin, _ = Financeiro.objects.update_or_create(
        viagem=viagem,
        cliente=cliente,
        defaults={
            "assessor_responsavel": assessor,
            "valor": valor,
            "status": status,
            "data_pagamento": datetime.date.today() if status == StatusFinanceiro.PAGO else None,
            "criado_por": admin_user,
        },
    )
    if status == StatusFinanceiro.PAGO and cliente and not cliente.cliente_principal_id:
        for dep in cliente.dependentes.all():
            Financeiro.objects.filter(cliente=dep, viagem=viagem).update(
                status=StatusFinanceiro.PAGO,
                data_pagamento=datetime.date.today(),
            )
    return fin


def criar_processo(viagem, cliente, assessor, admin_user):
    processo, _ = Processo.objects.get_or_create(
        viagem=viagem,
        cliente=cliente,
        defaults={
            "assessor_responsavel": assessor,
            "criado_por": admin_user,
        },
    )
    return processo


def carregar_formulario_json(nome_arquivo):
    caminho = os.path.join(FORMS_INI_DIR, nome_arquivo)
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _texto_padrao_por_indice(indice):
    amostras = [
        "São Paulo, SP - Brasil.",
        "Rua São João, nº 45 - Setor Oeste / Goiânia.",
        "Análise técnica, revisão documental e conferência final.",
        "João D'Ávila - referência familiar / contato principal.",
        "Apto. 1204, Bloco B - Residencial Águas Claras.",
        "Viagem a turismo, negócios e reunião com parceiros.",
        "Observação: documentação válida, assinada e conferida.",
    ]
    return amostras[indice % len(amostras)]


def _texto_simulado(pergunta, cliente):
    texto_pergunta = (pergunta or "").lower()
    nome_cliente = (cliente.nome or "José Álvaro da Conceição").strip()
    partes_nome = [p for p in nome_cliente.split(" ") if p]
    primeiro_nome = partes_nome[0] if partes_nome else "José"
    ultimo_nome = partes_nome[-1] if partes_nome else "Conceição"

    if "sobrenome" in texto_pergunta:
        return f"{ultimo_nome}-Silva."
    if "primeiro nome" in texto_pergunta or texto_pergunta.strip() == "nome":
        return f"{primeiro_nome}, José."
    if "nome" in texto_pergunta:
        return f"{nome_cliente} - versão teste/produção."
    if "cpf" in texto_pergunta:
        return cliente.cpf or "123.456.789-09"
    if "e-mail" in texto_pergunta or "email" in texto_pergunta:
        return f"{primeiro_nome.lower()}.{ultimo_nome.lower()}-teste/2026@exemplo.com.br"
    if "telefone" in texto_pergunta:
        return "+55 (62) 9.9123-4567"
    if "cep" in texto_pergunta:
        return "74.110-030"
    if "endereço" in texto_pergunta or "endereco" in texto_pergunta:
        return "Av. República do Líbano, nº 1.240 - Jardim Goiás / Goiânia."
    if "cidade" in texto_pergunta:
        return "Goiânia, GO."
    if "estado" in texto_pergunta:
        return "Goiás - GO."
    if "país" in texto_pergunta or "pais" in texto_pergunta:
        return "Brasil / América do Sul."
    if "passaporte" in texto_pergunta:
        return "BR12.345-678/9"
    if "motivo" in texto_pergunta:
        return "Turismo, férias e visita a familiares."
    if "ocupação" in texto_pergunta or "ocupacao" in texto_pergunta:
        return "Engenheiro de Produção - Óleo/Gás."
    if "funções" in texto_pergunta or "funcoes" in texto_pergunta or "atividades" in texto_pergunta:
        return "Gestão de projetos, análise técnico-financeira e revisão de contratos."
    if "rede social" in texto_pergunta:
        return "Instagram: @joao.silva-viagem/2026"
    return _texto_padrao_por_indice(len(texto_pergunta))


def _data_simulada(pergunta, viagem):
    texto_pergunta = (pergunta or "").lower()
    hoje = datetime.date.today()
    if "chegada" in texto_pergunta or "entrada" in texto_pergunta:
        return viagem.data_prevista_viagem or datetime.date(2026, 8, 10)
    if "saída" in texto_pergunta or "saida" in texto_pergunta or "término" in texto_pergunta or "termino" in texto_pergunta:
        return viagem.data_prevista_retorno or datetime.date(2026, 8, 25)
    if "nascimento" in texto_pergunta:
        return datetime.date(1991, 9, 23)
    if "emissão" in texto_pergunta or "emissao" in texto_pergunta:
        return datetime.date(hoje.year - 5, max(1, min(12, hoje.month)), max(1, min(28, hoje.day)))
    return datetime.date(2024, 3, 15)


def _numero_simulado(pergunta):
    texto_pergunta = (pergunta or "").lower()
    if "salário" in texto_pergunta or "salario" in texto_pergunta:
        return 8750.35
    if "fundos" in texto_pergunta or "disponíveis" in texto_pergunta or "disponiveis" in texto_pergunta:
        return 12850.75
    if "quantos filhos" in texto_pergunta:
        return 2
    return 3475.90


def seed_formulario_para_visto(tipo_visto, nome_arquivo):
    dados = carregar_formulario_json(nome_arquivo)
    for bloco in dados:
        formulario, _ = FormularioVisto.objects.get_or_create(
            tipo_visto=tipo_visto,
            defaults={"ativo": True},
        )
        formulario.ativo = True
        formulario.save()

        for perg_def in bloco["perguntas"]:
            opcoes = perg_def.pop("opcoes", [])
            pergunta, _ = PerguntaFormulario.objects.get_or_create(
                formulario=formulario,
                ordem=perg_def["ordem"],
                defaults={
                    "pergunta": perg_def["pergunta"],
                    "tipo_campo": perg_def["tipo_campo"],
                    "obrigatorio": perg_def["obrigatorio"],
                    "ativo": perg_def.get("ativo", True),
                },
            )
            for idx, texto_opcao in enumerate(opcoes, 1):
                OpcaoSelecao.objects.get_or_create(
                    pergunta=pergunta,
                    texto=texto_opcao,
                    defaults={"ordem": idx, "ativo": True},
                )


def preencher_formulario(viagem, cliente, admin_user, proporcao=1.0):
    tipo_visto = viagem.tipo_visto
    try:
        formulario = FormularioVisto.objects.get(tipo_visto=tipo_visto)
    except FormularioVisto.DoesNotExist:
        return

    perguntas = list(formulario.perguntas.filter(ativo=True).order_by("ordem"))
    limite = max(1, int(len(perguntas) * proporcao))

    for pergunta in perguntas[:limite]:
        defaults = {}
        if pergunta.tipo_campo == "texto":
            defaults["resposta_texto"] = _texto_simulado(pergunta.pergunta, cliente)
        elif pergunta.tipo_campo == "data":
            defaults["resposta_data"] = _data_simulada(pergunta.pergunta, viagem)
        elif pergunta.tipo_campo == "numero":
            defaults["resposta_numero"] = _numero_simulado(pergunta.pergunta)
        elif pergunta.tipo_campo == "booleano":
            defaults["resposta_booleano"] = pergunta.ordem % 2 == 0
        elif pergunta.tipo_campo == "selecao":
            opcoes = list(OpcaoSelecao.objects.filter(pergunta=pergunta, ativo=True).order_by("ordem"))
            if opcoes:
                defaults["resposta_selecao"] = opcoes[pergunta.ordem % len(opcoes)]

        RespostaFormulario.objects.update_or_create(
            viagem=viagem,
            cliente=cliente,
            pergunta=pergunta,
            defaults=defaults,
        )


def criar_partner(admin_user, nome_responsavel, nome_empresa, cpf_seed, email, telefone, segmento="Agência de intercâmbio"):
    import hashlib
    from django.contrib.auth.hashers import make_password
    cpf = cpf_valido(cpf_seed)
    senha_hash = make_password("visary123")
    partner, _ = Partner.objects.get_or_create(
        email=email,
        defaults={
            "nome_responsavel": nome_responsavel,
            "nome_empresa": nome_empresa,
            "cpf": cpf,
            "email": email,
            "senha": senha_hash,
            "telefone": telefone,
            "segmento": segmento,
            "cidade": "Goiânia",
            "estado": "GO",
            "ativo": True,
            "criado_por": admin_user,
        },
    )
    return partner


def criar_etapas_processo(processo, proporcao_concluidas=0.0):
    viagem = processo.viagem
    status_vinculados = list(
        viagem.status_disponiveis.filter(ativo=True).select_related("status").order_by("status__ordem")
    )
    total = len(status_vinculados)
    n_concluidas = int(total * proporcao_concluidas)
    for i, vsp in enumerate(status_vinculados):
        concluida = i < n_concluidas
        etapa, _ = EtapaProcesso.objects.get_or_create(
            processo=processo,
            status=vsp.status,
            defaults={
                "ordem": vsp.status.ordem,
                "concluida": concluida,
                "prazo_dias": vsp.status.prazo_padrao_dias,
                "data_conclusao": datetime.date.today() if concluida else None,
            },
        )
        if etapa.concluida != concluida:
            etapa.concluida = concluida
            etapa.data_conclusao = datetime.date.today() if concluida else None
            etapa.save(update_fields=["concluida", "data_conclusao", "atualizado_em"])
