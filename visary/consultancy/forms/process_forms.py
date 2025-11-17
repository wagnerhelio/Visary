"""
Formulários relacionados a processos de visto.
"""

from django import forms
from django.contrib.auth.models import User

from consultancy.models import Processo
from system.models import UsuarioConsultoria


class ProcessoForm(forms.ModelForm):
    """Formulário para cadastro de processo."""

    class Meta:
        model = Processo
        fields = (
            "viagem",
            "cliente",
            "status",
            "prazo_dias",
            "observacoes",
            "assessor_responsavel",
        )
        widgets = {
            "viagem": forms.Select(attrs={"class": "input"}),
            "cliente": forms.Select(attrs={"class": "input"}),
            "status": forms.Select(attrs={"class": "input"}),
            "prazo_dias": forms.NumberInput(
                attrs={
                    "class": "input",
                    "min": "0",
                    "step": "1",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 3,
                }
            ),
            "assessor_responsavel": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, user: User | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user

        # Filtrar viagens ativas
        from consultancy.models import Viagem

        self.fields["viagem"].queryset = Viagem.objects.select_related(
            "pais_destino", "tipo_visto"
        ).order_by("-data_prevista_viagem")

        # Filtrar clientes ativos
        from consultancy.models import ClienteConsultoria

        self.fields["cliente"].queryset = ClienteConsultoria.objects.all().order_by("nome")

        # Permitir todos os status ativos (gerais ou específicos)
        from consultancy.models import StatusProcesso

        if self.instance.pk and self.instance.viagem:
            # Se estiver editando, mostrar todos os status ativos
            self.fields["status"].queryset = StatusProcesso.objects.filter(
                ativo=True
            ).order_by("ordem", "nome")
        else:
            # Se estiver criando, mostrar todos os status ativos
            self.fields["status"].queryset = StatusProcesso.objects.filter(
                ativo=True
            ).order_by("ordem", "nome")

        # Filtrar assessores ativos
        self.fields["assessor_responsavel"].queryset = (
            UsuarioConsultoria.objects.filter(ativo=True).order_by("nome").select_related("perfil")
        )

        # Se não for admin, definir assessor responsável como o usuário logado
        if user is not None and not user.is_superuser and not user.is_staff:
            if consultor := (
                UsuarioConsultoria.objects.filter(email__iexact=user.email, ativo=True)
                .order_by("-atualizado_em")
                .first()
            ):
                self.fields["assessor_responsavel"].initial = consultor.pk

    def clean(self):
        cleaned_data = super().clean()
        viagem = cleaned_data.get("viagem")
        cliente = cleaned_data.get("cliente")

        if viagem and cliente:
            # Verificar se o cliente está vinculado à viagem
            if cliente not in viagem.clientes.all():
                raise forms.ValidationError(
                    "O cliente selecionado não está vinculado à viagem escolhida."
                )

            # Verificar se já existe processo para esta viagem e cliente
            processos_existentes = (
                Processo.objects.filter(viagem=viagem, cliente=cliente).exclude(
                    pk=self.instance.pk
                )
                if self.instance.pk
                else Processo.objects.filter(viagem=viagem, cliente=cliente)
            )

            if processos_existentes.exists():
                raise forms.ValidationError(
                    "Já existe um processo cadastrado para este cliente nesta viagem."
                )

        return cleaned_data

    def save(self, commit: bool = True) -> Processo:
        processo = super().save(commit=False)
        if self._user and not processo.criado_por_id:
            processo.criado_por = self._user

        # Se o prazo não foi definido, usar o prazo padrão do status
        if processo.prazo_dias == 0 and processo.status and processo.status.prazo_padrao_dias > 0:
            processo.prazo_dias = processo.status.prazo_padrao_dias

        if commit:
            processo.save()

        return processo

