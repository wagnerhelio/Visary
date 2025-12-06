"""
Formulários relacionados a processos de visto.
"""

from django import forms
from django.contrib.auth.models import User

from consultancy.models import EtapaProcesso, Processo, ViagemStatusProcesso
from system.models import UsuarioConsultoria


class ProcessoForm(forms.ModelForm):
    """Formulário para cadastro de processo."""

    class Meta:
        model = Processo
        fields = (
            "viagem",
            "cliente",
            "observacoes",
            "assessor_responsavel",
        )
        widgets = {
            "viagem": forms.Select(attrs={"class": "input"}),
            "cliente": forms.Select(attrs={"class": "input"}),
            "observacoes": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 3,
                }
            ),
            "assessor_responsavel": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, user: User | None = None, cliente_id: int | None = None, viagem_id: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user

        # Filtrar viagens ativas
        from consultancy.models import Viagem, ClienteConsultoria

        viagens_queryset = Viagem.objects.select_related(
            "pais_destino", "tipo_visto"
        ).order_by("-data_prevista_viagem")
        
        # Se cliente_id fornecido, filtrar apenas viagens onde cliente está vinculado
        if cliente_id:
            try:
                cliente = ClienteConsultoria.objects.get(pk=cliente_id)
                # Viagens onde cliente está diretamente OU é dependente de cliente principal na viagem
                viagens_queryset = viagens_queryset.filter(
                    clientes=cliente
                ).distinct()
            except ClienteConsultoria.DoesNotExist:
                pass
        
        self.fields["viagem"].queryset = viagens_queryset
        
        # Personalizar exibição das viagens no select
        def label_from_instance_viagem(obj):
            """Formata a exibição da viagem: País - Tipo de Visto - Data da Viagem"""
            pais = obj.pais_destino.nome if obj.pais_destino else "N/A"
            tipo_visto = obj.tipo_visto.nome if obj.tipo_visto else "N/A"
            data_viagem = obj.data_prevista_viagem.strftime('%d/%m/%Y') if obj.data_prevista_viagem else "N/A"
            return f"{pais} - {tipo_visto} - {data_viagem}"
        
        self.fields["viagem"].label_from_instance = label_from_instance_viagem

        # Filtrar clientes ativos
        clientes_queryset = ClienteConsultoria.objects.all().order_by("nome")
        
        # Se viagem_id fornecido, filtrar apenas clientes vinculados à viagem
        viagem_obj = None
        if viagem_id:
            try:
                viagem_obj = Viagem.objects.get(pk=viagem_id)
                # Clientes diretamente na viagem
                clientes_na_viagem = viagem_obj.clientes.all()
                
                # Buscar emails dos clientes que estão na viagem
                emails_na_viagem = set(clientes_na_viagem.values_list('email', flat=True))
                
                # Remover emails vazios/None
                emails_na_viagem = {email for email in emails_na_viagem if email}
                
                # Incluir clientes que compartilham o mesmo email dos clientes na viagem
                clientes_com_mesmo_email = ClienteConsultoria.objects.none()
                if emails_na_viagem:
                    clientes_com_mesmo_email = ClienteConsultoria.objects.filter(
                        email__in=emails_na_viagem
                    )
                
                # Combinar: clientes diretamente na viagem + clientes com mesmo email
                clientes_ids = set(clientes_na_viagem.values_list('pk', flat=True))
                if clientes_com_mesmo_email.exists():
                    clientes_ids.update(clientes_com_mesmo_email.values_list('pk', flat=True))
                
                clientes_queryset = clientes_queryset.filter(
                    pk__in=clientes_ids
                ).distinct()
            except Viagem.DoesNotExist:
                pass
        
        self.fields["cliente"].queryset = clientes_queryset
        
        # Definir valores iniciais se parâmetros fornecidos
        if cliente_id and not self.instance.pk:
            try:
                self.fields["cliente"].initial = int(cliente_id)
            except (ValueError, TypeError):
                pass
        elif viagem_obj and not self.instance.pk and not cliente_id:
            # Se viagem_id fornecido mas não cliente_id, verificar se há apenas um cliente
            # Usar o queryset já filtrado para contar
            clientes_list = list(clientes_queryset)
            if len(clientes_list) == 1:
                # Se há apenas um cliente, pré-selecionar e desabilitar
                cliente_unico = clientes_list[0]
                if cliente_unico:
                    self.fields["cliente"].initial = cliente_unico.pk
                    self.fields["cliente"].widget.attrs['disabled'] = True
                    self.fields["cliente"].widget.attrs['style'] = 'opacity: 0.6; cursor: not-allowed;'
                    # Adicionar campo hidden para garantir que o valor seja enviado no POST
                    from django import forms as django_forms
                    self.fields['cliente_hidden'] = django_forms.IntegerField(
                        widget=django_forms.HiddenInput(),
                        initial=cliente_unico.pk,
                        required=False
                    )
        
        if viagem_id and not self.instance.pk:
            try:
                viagem_id_int = int(viagem_id)
                self.fields["viagem"].initial = viagem_id_int
                # Quando viagem_id é fornecido, tornar o campo disabled pois já está vinculado
                self.fields["viagem"].widget.attrs['disabled'] = True
                self.fields["viagem"].widget.attrs['style'] = 'opacity: 0.6; cursor: not-allowed;'
                # Adicionar campo hidden para garantir que o valor seja enviado no POST
                from django import forms as django_forms
                self.fields['viagem_hidden'] = django_forms.IntegerField(
                    widget=django_forms.HiddenInput(),
                    initial=viagem_id_int,
                    required=False
                )
            except (ValueError, TypeError):
                pass

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

    def full_clean(self):
        """Sobrescreve full_clean para processar campos hidden antes da validação."""
        # Processar campos hidden antes de chamar super().full_clean()
        if self.data and hasattr(self, 'fields'):
            # Processar viagem_hidden
            if "viagem_hidden" in self.fields and self.data.get("viagem_hidden"):
                try:
                    viagem_id = int(self.data.get("viagem_hidden"))
                    if "viagem" in self.fields and not self.data.get("viagem"):
                        # Se viagem não foi enviada mas viagem_hidden foi, usar o hidden
                        self.data = self.data.copy()
                        self.data["viagem"] = str(viagem_id)
                except (ValueError, TypeError):
                    pass
            
            # Processar cliente_hidden
            if "cliente_hidden" in self.fields and self.data.get("cliente_hidden"):
                try:
                    cliente_id = int(self.data.get("cliente_hidden"))
                    if "cliente" in self.fields and not self.data.get("cliente"):
                        # Se cliente não foi enviado mas cliente_hidden foi, usar o hidden
                        self.data = self.data.copy()
                        self.data["cliente"] = str(cliente_id)
                except (ValueError, TypeError):
                    pass
        
        super().full_clean()
    
    def clean(self):
        cleaned_data = super().clean()
        # Se viagem estiver disabled, usar o campo hidden ou o valor do POST
        if not cleaned_data.get("viagem"):
            viagem_id = None
            # Tentar obter do campo hidden primeiro
            if "viagem_hidden" in self.fields:
                viagem_id = cleaned_data.get("viagem_hidden")
                if not viagem_id and self.fields.get("viagem_hidden"):
                    viagem_id = self.fields.get("viagem_hidden").initial
            # Se não encontrou no hidden, tentar obter diretamente do POST
            if not viagem_id and self.data.get("viagem_hidden"):
                try:
                    viagem_id = int(self.data.get("viagem_hidden"))
                except (ValueError, TypeError):
                    pass
            
            if viagem_id:
                from consultancy.models import Viagem
                try:
                    viagem = Viagem.objects.get(pk=viagem_id)
                    cleaned_data["viagem"] = viagem
                except (Viagem.DoesNotExist, ValueError, TypeError, AttributeError):
                    pass
        
        # Se cliente estiver disabled, usar o campo hidden ou o valor do POST
        if not cleaned_data.get("cliente"):
            cliente_id = None
            # Tentar obter do campo hidden primeiro
            if "cliente_hidden" in self.fields:
                cliente_id = cleaned_data.get("cliente_hidden")
                if not cliente_id and self.fields.get("cliente_hidden"):
                    cliente_id = self.fields.get("cliente_hidden").initial
            # Se não encontrou no hidden, tentar obter diretamente do POST
            if not cliente_id and self.data.get("cliente_hidden"):
                try:
                    cliente_id = int(self.data.get("cliente_hidden"))
                except (ValueError, TypeError):
                    pass
            
            if cliente_id:
                from consultancy.models import ClienteConsultoria
                try:
                    cliente = ClienteConsultoria.objects.get(pk=cliente_id)
                    cleaned_data["cliente"] = cliente
                except (ClienteConsultoria.DoesNotExist, ValueError, TypeError, AttributeError):
                    pass
        
        viagem = cleaned_data.get("viagem")
        cliente = cleaned_data.get("cliente")

        if viagem and cliente:
            # Buscar todos os clientes diretamente na viagem
            clientes_na_viagem = viagem.clientes.all()
            cliente_na_viagem = cliente in clientes_na_viagem
            
            # Verificar se o cliente compartilha email com algum cliente na viagem
            cliente_com_mesmo_email_na_viagem = False
            if not cliente_na_viagem and cliente.email:
                # Buscar emails dos clientes que estão na viagem
                emails_na_viagem = set(clientes_na_viagem.values_list('email', flat=True))
                emails_na_viagem = {email for email in emails_na_viagem if email}
                
                # Verificar se o cliente compartilha email com algum cliente na viagem
                if cliente.email in emails_na_viagem:
                    cliente_com_mesmo_email_na_viagem = True
            
            # Verificar se o cliente é dependente de outro cliente que está na viagem
            cliente_principal_na_viagem = False
            if cliente.cliente_principal:
                cliente_principal_na_viagem = cliente.cliente_principal in viagem.clientes.all()
            
            # Verificar se algum dependente do cliente está na viagem (caso o cliente seja principal)
            dependente_na_viagem = False
            if cliente.is_principal:
                dependentes_na_viagem = viagem.clientes.filter(cliente_principal=cliente).exists()
                dependente_na_viagem = dependentes_na_viagem
            
            # Cliente deve estar na viagem OU compartilhar email com cliente na viagem OU ser membro de um grupo familiar vinculado
            cliente_valido = cliente_na_viagem or cliente_com_mesmo_email_na_viagem or cliente_principal_na_viagem or dependente_na_viagem
            
            if not cliente_valido:
                self.add_error(
                    "cliente",
                    "O cliente selecionado não está vinculado à viagem escolhida. "
                    "Por favor, vincule o cliente à viagem antes de criar o processo."
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
                self.add_error(
                    "cliente",
                    f"Já existe um processo cadastrado para este cliente nesta viagem."
                )

        return cleaned_data

    def save(self, commit: bool = True) -> Processo:
        processo = super().save(commit=False)
        if self._user and not processo.criado_por_id:
            processo.criado_por = self._user

        if commit:
            processo.save()
            # Criar etapas automaticamente baseadas nos status vinculados à viagem
            self._criar_etapas(processo)

        return processo

    def _criar_etapas(self, processo: Processo) -> None:
        """Cria as etapas do processo baseadas nos status vinculados à viagem."""
        status_vinculados = ViagemStatusProcesso.objects.filter(
            viagem=processo.viagem,
            ativo=True
        ).select_related('status').order_by('status__ordem', 'status__nome')

        for viagem_status in status_vinculados:
            status = viagem_status.status
            # Usar o prazo padrão do status se disponível
            prazo_dias = status.prazo_padrao_dias if status.prazo_padrao_dias > 0 else 0

            EtapaProcesso.objects.get_or_create(
                processo=processo,
                status=status,
                defaults={
                    'prazo_dias': prazo_dias,
                    'ordem': status.ordem,
                }
            )


class EtapaProcessoForm(forms.ModelForm):
    """Formulário para editar uma etapa do processo."""

    class Meta:
        model = EtapaProcesso
        fields = (
            "concluida",
            "prazo_dias",
            "data_conclusao",
            "observacoes",
        )
        widgets = {
            "concluida": forms.CheckboxInput(attrs={"class": "input"}),
            "prazo_dias": forms.NumberInput(
                attrs={
                    "class": "input",
                    "min": "0",
                    "step": "1",
                }
            ),
            "data_conclusao": forms.DateInput(
                attrs={
                    "class": "input",
                    "type": "date",
                }
            ),
            "observacoes": forms.Textarea(
                attrs={
                    "class": "input",
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["prazo_dias"].required = False
