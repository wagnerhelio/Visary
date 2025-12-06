"""
Formulário para cadastro de clientes da consultoria.
"""

from __future__ import annotations

import contextlib
from typing import Optional

from django import forms
from django.contrib.auth import get_user_model

from consultancy.models import ClienteConsultoria, Partner
from system.models import UsuarioConsultoria

User = get_user_model()


class ClienteConsultoriaForm(forms.ModelForm):
    confirmar_senha = forms.CharField(
        label="Confirme a senha",
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder": "Repita a senha de acesso",
                "data-lpignore": "true",
                "data-1p-ignore": "true",
                "data-bwignore": "true",
                "data-form-type": "other",
            }
        ),
    )

    class Meta:
        model = ClienteConsultoria
        fields = (
            "assessor_responsavel",
            "nome",
            "data_nascimento",
            "nacionalidade",
            "telefone",
            "telefone_secundario",
            "email",
            "senha",
            "parceiro_indicador",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "tipo_passaporte",
            "tipo_passaporte_outro",
            "numero_passaporte",
            "pais_emissor_passaporte",
            "data_emissao_passaporte",
            "valido_ate_passaporte",
            "autoridade_passaporte",
            "cidade_emissao_passaporte",
            "passaporte_roubado",
            "observacoes",
        )
        widgets = {
            "assessor_responsavel": forms.Select(attrs={"class": "input"}),
            "parceiro_indicador": forms.Select(
                attrs={
                    "class": "input",
                    "data-partner-select": "true",
                }
            ),
            "nome": forms.TextInput(
                attrs={"placeholder": "Nome completo", "autocomplete": "name"}
            ),
            "data_nascimento": forms.DateInput(
                attrs={
                    "type": "date",
                    "placeholder": "dd/mm/aaaa",
                },
                format="%Y-%m-%d",
            ),
            "nacionalidade": forms.TextInput(
                attrs={"placeholder": "Nacionalidade", "autocomplete": "country-name"}
            ),
            "telefone": forms.TextInput(
                attrs={"placeholder": "Telefone principal", "autocomplete": "tel"}
            ),
            "telefone_secundario": forms.TextInput(
                attrs={"placeholder": "Telefone secundário", "autocomplete": "tel"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "email@dominio.com",
                    "autocomplete": "email",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                    "data-bwignore": "true",
                }
            ),
            "senha": forms.PasswordInput(
                attrs={
                    "autocomplete": "new-password",
                    "placeholder": "Senha de acesso do cliente",
                    "data-lpignore": "true",
                    "data-1p-ignore": "true",
                    "data-bwignore": "true",
                    "data-form-type": "other",
                }
            ),
            "cep": forms.TextInput(
                attrs={
                    "placeholder": "00000-000",
                    "maxlength": "9",
                    "class": "cep-input",
                    "autocomplete": "postal-code",
                }
            ),
            "logradouro": forms.TextInput(
                attrs={"placeholder": "Rua, Avenida, etc.", "autocomplete": "street-address"}
            ),
            "numero": forms.TextInput(
                attrs={"placeholder": "Número", "autocomplete": "off"}
            ),
            "complemento": forms.TextInput(
                attrs={"placeholder": "Apto, Bloco, etc.", "autocomplete": "off"}
            ),
            "bairro": forms.TextInput(
                attrs={"placeholder": "Bairro", "autocomplete": "address-level2"}
            ),
            "cidade": forms.TextInput(
                attrs={"placeholder": "Cidade", "autocomplete": "address-level1"}
            ),
            "uf": forms.TextInput(
                attrs={
                    "placeholder": "UF",
                    "maxlength": "2",
                    "style": "text-transform: uppercase;",
                    "autocomplete": "address-level1",
                }
            ),
            "tipo_passaporte": forms.Select(attrs={"class": "input"}),
            "tipo_passaporte_outro": forms.TextInput(
                attrs={"placeholder": "Especifique o tipo de passaporte"}
            ),
            "numero_passaporte": forms.TextInput(
                attrs={"placeholder": "Número do passaporte válido"}
            ),
            "pais_emissor_passaporte": forms.TextInput(
                attrs={"placeholder": "País que emitiu o passaporte"}
            ),
            "data_emissao_passaporte": forms.DateInput(
                attrs={
                    "type": "date",
                    "placeholder": "dd/mm/aaaa",
                },
                format="%Y-%m-%d",
            ),
            "valido_ate_passaporte": forms.DateInput(
                attrs={
                    "type": "date",
                    "placeholder": "dd/mm/aaaa",
                },
                format="%Y-%m-%d",
            ),
            "autoridade_passaporte": forms.TextInput(
                attrs={"placeholder": "Autoridade emissora"}
            ),
            "cidade_emissao_passaporte": forms.TextInput(
                attrs={"placeholder": "Cidade onde foi emitido"}
            ),
            "passaporte_roubado": forms.CheckboxInput(),
            "observacoes": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Informações adicionais sobre o atendimento",
                }
            ),
        }

    def __init__(self, *args, user: Optional[User] = None, cliente_principal=None, usar_dados_principal: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user
        self.cliente_principal = cliente_principal
        self.usar_dados_principal = usar_dados_principal  # Flag para usar dados do cliente principal
        
        # Se estiver usando dados do cliente principal, tornar senha opcional ANTES de qualquer outra configuração
        if usar_dados_principal:
            if 'senha' in self.fields:
                self.fields['senha'].required = False
                self.fields['senha'].widget.attrs['data-usar-dados-principal'] = 'true'
            if 'confirmar_senha' in self.fields:
                self.fields['confirmar_senha'].required = False
                self.fields['confirmar_senha'].widget.attrs['data-usar-dados-principal'] = 'true'
        
        self.fields["assessor_responsavel"].queryset = (
            UsuarioConsultoria.objects.filter(ativo=True)
            .order_by("nome")
            .select_related("perfil")
        )
        
        # Campo de parceiro opcional
        self.fields["parceiro_indicador"].queryset = Partner.objects.filter(ativo=True).order_by("nome_empresa", "nome_responsavel")
        self.fields["parceiro_indicador"].required = False
        self.fields["parceiro_indicador"].empty_label = "Nenhum parceiro"
        
        # Configurar campo tipo_passaporte
        self.fields["tipo_passaporte"].required = False
        self.fields["tipo_passaporte"].choices = [
            ("", "Selecione o tipo de passaporte"),
            ("comum", "Passaporte Comum/Regular"),
            ("diplomatico", "Passaporte Diplomático"),
            ("servico", "Passaporte de Serviço"),
            ("outro", "Outro"),
        ]
        self.fields["tipo_passaporte_outro"].required = False

        # Pré-preenche assessor responsável se o usuário for um UsuarioConsultoria
        # (funciona tanto para assessores quanto para administradores)
        if user is not None:
            consultor = (
                UsuarioConsultoria.objects.filter(email__iexact=user.email, ativo=True)
                .order_by("-atualizado_em")
                .first()
            )
            if consultor and not self.instance.pk:  # Só pré-preenche em criação, não em edição
                self.fields["assessor_responsavel"].initial = consultor.pk
    
    def full_clean(self):
        """Sobrescreve full_clean para garantir que senha seja opcional quando usar_dados_principal."""
        # Se estiver usando dados do cliente principal, garantir que campos de senha são opcionais
        if self.usar_dados_principal:
            if 'senha' in self.fields:
                self.fields['senha'].required = False
            if 'confirmar_senha' in self.fields:
                self.fields['confirmar_senha'].required = False
        super().full_clean()

    def clean_confirmar_senha(self):
        # Se estiver usando dados do cliente principal, não validar - retornar vazio
        if self.usar_dados_principal:
            return ""
        
        senha = self.cleaned_data.get("senha", "")
        confirmar = self.cleaned_data.get("confirmar_senha", "")

        # Se ambos estão vazios e é edição, não validar
        if not senha and not confirmar and self.instance.pk:
            return confirmar

        if senha and confirmar and senha != confirmar:
            raise forms.ValidationError("As senhas informadas não conferem.")

        return confirmar

    def clean_senha(self):
        # Se estiver usando dados do cliente principal, não validar - retornar vazio
        if self.usar_dados_principal:
            return ""
        
        senha = self.cleaned_data.get("senha", "")
        # Se for um novo cliente (sem pk), a senha é obrigatória
        if not senha and not self.instance.pk:
            raise forms.ValidationError("A senha é obrigatória para novos clientes.")
        return senha
    
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email
        
        # Verificar se email já existe
        queryset = ClienteConsultoria.objects.filter(email=email)
        if self.instance.pk:
            # Se estiver editando, excluir a própria instância da verificação
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            cliente_existente = queryset.first()
            
            # Se estamos criando/editando um dependente
            if self.cliente_principal:
                # Permitir se o email pertence ao cliente principal
                if cliente_existente.pk == self.cliente_principal.pk:
                    return email
                # Permitir se o email pertence a outro dependente do mesmo cliente principal
                if cliente_existente.cliente_principal_id == self.cliente_principal.pk:
                    return email
                # Caso contrário, erro
                raise forms.ValidationError(
                    f"Este email já está em uso por outro cliente: {cliente_existente.nome}. "
                    "Apenas o cliente principal e seus membros podem compartilhar o mesmo email."
                )
            
            # Se estamos criando/editando um cliente principal
            # Verificar se é dependente que pode compartilhar email
            if not self.instance.pk or not self.instance.cliente_principal:
                # Se o email pertence a algum dependente deste cliente (em edição)
                if self.instance.pk:
                    dependentes_ids = list(ClienteConsultoria.objects.filter(
                        cliente_principal_id=self.instance.pk
                    ).values_list('pk', flat=True))
                    if cliente_existente.pk in dependentes_ids:
                        return email
                # Se o email pertence a outro cliente principal ou dependente de outro grupo, erro
                raise forms.ValidationError(
                    f"Este email já está em uso por outro cliente: {cliente_existente.nome}. "
                    "Emails podem ser compartilhados apenas entre cliente principal e seus membros."
                )
        
        return email
    
    def clean_tipo_passaporte_outro(self):
        tipo_passaporte = self.cleaned_data.get("tipo_passaporte")
        tipo_passaporte_outro = self.cleaned_data.get("tipo_passaporte_outro")
        
        # Se tipo_passaporte for "outro", tipo_passaporte_outro é obrigatório
        if tipo_passaporte == "outro" and not tipo_passaporte_outro:
            raise forms.ValidationError("Especifique o tipo de passaporte quando selecionar 'Outro'.")
        
        return tipo_passaporte_outro

    def save(self, commit: bool = True) -> ClienteConsultoria:
        cliente = super().save(commit=False)
        
        # Só atualizar senha se foi fornecida (não vazia)
        if senha := self.cleaned_data.get("senha"):
            # Sempre fazer hash da senha
            cliente.set_password(senha)
        # Se estiver editando e senha vazia, manter a senha atual
        elif cliente.pk:
            # Manter a senha atual do banco (já está em hash)
            with contextlib.suppress(ClienteConsultoria.DoesNotExist):
                cliente_atual = ClienteConsultoria.objects.get(pk=cliente.pk)
                cliente.senha = cliente_atual.senha
        # Se for novo cliente e não tem senha, isso é um erro
        # Mas deixamos o Django validar isso no modelo

        if self._user and not cliente.criado_por_id:
            cliente.criado_por = self._user

        if commit:
            cliente.save()

        return cliente

