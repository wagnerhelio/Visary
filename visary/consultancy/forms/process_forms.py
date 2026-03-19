   
                                              
   

import logging

from django import forms
from django.contrib.auth.models import User

from consultancy.models import EtapaProcesso, Processo, ViagemStatusProcesso
from system.models import UsuarioConsultoria

logger = logging.getLogger(__name__)


class ProcessoForm(forms.ModelForm):
                                               

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

    etapas_selecionadas = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Etapas do Processo",
        help_text="Selecione as etapas que deseja incluir no processo"
    )

    def __init__(self, *args, user: User | None = None, cliente_id: int | None = None, viagem_id: int | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._user = user
        self._viagem_id = viagem_id
        
                                                                                                
        viagem_id_para_etapas = viagem_id
        if not viagem_id_para_etapas and self.data:
                                            
            viagem_id_post = self.data.get('viagem') or self.data.get('viagem_hidden')
            if viagem_id_post:
                try:
                    viagem_id_para_etapas = int(viagem_id_post)
                except (ValueError, TypeError):
                    logger.warning("viagem_hidden/viagem inválido em ProcessoForm.__init__: %r", viagem_id_post)
        
        if viagem_id_para_etapas:
            from consultancy.models import ViagemStatusProcesso
            status_vinculados = ViagemStatusProcesso.objects.filter(
                viagem_id=viagem_id_para_etapas,
                ativo=True
            ).select_related('status').order_by('status__ordem', 'status__nome')
            
            choices = [(vs.status.pk, vs.status.nome) for vs in status_vinculados]
            self.fields['etapas_selecionadas'].choices = choices
            self.fields['etapas_selecionadas'].widget = forms.CheckboxSelectMultiple()
                                                                                 
            if not self.instance.pk and not self.data:
                self.fields['etapas_selecionadas'].initial = [str(pk) for pk, _ in choices]
        else:
            self.fields['etapas_selecionadas'].widget = forms.HiddenInput()
            self.fields['etapas_selecionadas'].choices = []

                                
        from consultancy.models import Viagem, ClienteConsultoria

        viagens_queryset = Viagem.objects.select_related(
            "pais_destino", "tipo_visto"
        ).order_by("-data_prevista_viagem")
        
                                                                                     
        if cliente_id:
            try:
                cliente = ClienteConsultoria.objects.get(pk=cliente_id)
                                                                                                      
                viagens_queryset = viagens_queryset.filter(
                    clientes=cliente
                ).distinct()
            except ClienteConsultoria.DoesNotExist:
                logger.warning("ClienteConsultoria não encontrado em ProcessoForm.__init__: cliente_id=%r", cliente_id)
        
        self.fields["viagem"].queryset = viagens_queryset
        
                                                     
        def label_from_instance_viagem(obj):
                                                                                     
            pais = obj.pais_destino.nome if obj.pais_destino else "N/A"
            tipo_visto = obj.tipo_visto.nome if obj.tipo_visto else "N/A"
            data_viagem = obj.data_prevista_viagem.strftime('%d/%m/%Y') if obj.data_prevista_viagem else "N/A"
            return f"{pais} - {tipo_visto} - {data_viagem}"
        
        self.fields["viagem"].label_from_instance = label_from_instance_viagem

                                 
        clientes_queryset = ClienteConsultoria.objects.all().order_by("nome")
        
                                                                             
        viagem_obj = None
        if viagem_id:
            try:
                viagem_obj = Viagem.objects.get(pk=viagem_id)
                                                
                clientes_na_viagem = viagem_obj.clientes.all()
                
                clientes_ids = set(clientes_na_viagem.values_list('pk', flat=True))
                for cliente_viagem in clientes_na_viagem:
                    if cliente_viagem.is_principal:
                        clientes_ids.update(
                            ClienteConsultoria.objects.filter(cliente_principal=cliente_viagem).values_list('pk', flat=True)
                        )
                    elif cliente_viagem.cliente_principal_id:
                        clientes_ids.add(cliente_viagem.cliente_principal_id)
                        clientes_ids.update(
                            ClienteConsultoria.objects.filter(cliente_principal_id=cliente_viagem.cliente_principal_id).values_list('pk', flat=True)
                        )
                
                clientes_queryset = clientes_queryset.filter(
                    pk__in=clientes_ids
                ).distinct()
            except Viagem.DoesNotExist:
                logger.warning("Viagem não encontrada em ProcessoForm.__init__: viagem_id=%r", viagem_id)
        
        self.fields["cliente"].queryset = clientes_queryset
        
                                                           
        if cliente_id and not self.instance.pk:
            try:
                self.fields["cliente"].initial = int(cliente_id)
            except (ValueError, TypeError):
                logger.warning("Falha ao converter cliente_id=%r em ProcessoForm.__init__", cliente_id)
        elif viagem_obj and not self.instance.pk and not cliente_id:
                                                                                          
                                                     
            clientes_list = list(clientes_queryset)
            if len(clientes_list) == 1:
                                                                       
                cliente_unico = clientes_list[0]
                if cliente_unico:
                    self.fields["cliente"].initial = cliente_unico.pk
                    self.fields["cliente"].widget.attrs['disabled'] = True
                    self.fields["cliente"].widget.attrs['style'] = 'opacity: 0.6; cursor: not-allowed;'
                                                                                           
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
                                                                                              
                self.fields["viagem"].widget.attrs['disabled'] = True
                self.fields["viagem"].widget.attrs['style'] = 'opacity: 0.6; cursor: not-allowed;'
                                                                                       
                from django import forms as django_forms
                self.fields['viagem_hidden'] = django_forms.IntegerField(
                    widget=django_forms.HiddenInput(),
                    initial=viagem_id_int,
                    required=False
                )
            except (ValueError, TypeError):
                logger.warning("Falha ao converter viagem_id=%r em ProcessoForm.__init__", viagem_id)

                                   
        self.fields["assessor_responsavel"].queryset = (
            UsuarioConsultoria.objects.filter(ativo=True).order_by("nome").select_related("perfil")
        )

                                                                              
        if user is not None and not user.is_superuser and not user.is_staff:
            if consultor := (
                UsuarioConsultoria.objects.filter(email__iexact=user.email, ativo=True)
                .order_by("-atualizado_em")
                .first()
            ):
                self.fields["assessor_responsavel"].initial = consultor.pk

    def full_clean(self):
                                                                                     
                                                                      
        if self.data and hasattr(self, 'fields'):
                                     
            if "viagem_hidden" in self.fields and self.data.get("viagem_hidden"):
                try:
                    viagem_id = int(self.data.get("viagem_hidden"))
                    if "viagem" in self.fields and not self.data.get("viagem"):
                                                                                        
                        self.data = self.data.copy()
                        self.data["viagem"] = str(viagem_id)
                except (ValueError, TypeError):
                                                                                    
                    pass
            
                                      
            if "cliente_hidden" in self.fields and self.data.get("cliente_hidden"):
                try:
                    cliente_id = int(self.data.get("cliente_hidden"))
                    if "cliente" in self.fields and not self.data.get("cliente"):
                                                                                          
                        self.data = self.data.copy()
                        self.data["cliente"] = str(cliente_id)
                except (ValueError, TypeError):
                                                                                     
                    pass
        
        super().full_clean()
    
    def clean(self):
        cleaned_data = super().clean()
                                                                            
        if not cleaned_data.get("viagem"):
            viagem_id = None
                                                   
            if "viagem_hidden" in self.fields:
                hidden_val = self.data.get("viagem_hidden")
                viagem_id = cleaned_data.get("viagem_hidden")

                                                                               
                                                                                   
                if not viagem_id:
                    if hidden_val not in (None, ""):
                        self.add_error("viagem", "Viagem inválida.")
                        viagem_id = None
                    elif self.fields.get("viagem_hidden"):
                        viagem_id = self.fields.get("viagem_hidden").initial
            
            if viagem_id:
                from consultancy.models import Viagem
                try:
                    viagem = Viagem.objects.get(pk=viagem_id)
                    cleaned_data["viagem"] = viagem
                except (Viagem.DoesNotExist, ValueError, TypeError, AttributeError):
                    self.add_error("viagem", "Viagem inválida.")
        
                                                                             
        if not cleaned_data.get("cliente"):
            cliente_id = None
                                                   
            if "cliente_hidden" in self.fields:
                hidden_val = self.data.get("cliente_hidden")
                cliente_id = cleaned_data.get("cliente_hidden")

                                                                               
                                                      
                if not cliente_id:
                    if hidden_val not in (None, ""):
                        self.add_error("cliente", "Cliente inválido.")
                        cliente_id = None
                    elif self.fields.get("cliente_hidden"):
                        cliente_id = self.fields.get("cliente_hidden").initial
            
            if cliente_id:
                from consultancy.models import ClienteConsultoria
                try:
                    cliente = ClienteConsultoria.objects.get(pk=cliente_id)
                    cleaned_data["cliente"] = cliente
                except (ClienteConsultoria.DoesNotExist, ValueError, TypeError, AttributeError):
                    self.add_error("cliente", "Cliente inválido.")
        
        viagem = cleaned_data.get("viagem")
        cliente = cleaned_data.get("cliente")

        if viagem and cliente:
                                                            
            clientes_na_viagem = viagem.clientes.all()
            cliente_na_viagem = cliente in clientes_na_viagem
            
                                                                                  
            cliente_com_mesmo_email_na_viagem = False
            if not cliente_na_viagem and cliente.email:
                                                                
                emails_na_viagem = set(clientes_na_viagem.values_list('email', flat=True))
                emails_na_viagem = {email for email in emails_na_viagem if email}
                
                                                                                      
                if cliente.email in emails_na_viagem:
                    cliente_com_mesmo_email_na_viagem = True
            
                                                                                     
            cliente_principal_na_viagem = False
            if cliente.cliente_principal:
                cliente_principal_na_viagem = cliente.cliente_principal in viagem.clientes.all()
            
                                                                                                     
            dependente_na_viagem = False
            if cliente.is_principal:
                dependentes_na_viagem = viagem.clientes.filter(cliente_principal=cliente).exists()
                dependente_na_viagem = dependentes_na_viagem
            
                                                                                                                                   
            cliente_valido = cliente_na_viagem or cliente_com_mesmo_email_na_viagem or cliente_principal_na_viagem or dependente_na_viagem
            
            if not cliente_valido:
                self.add_error(
                    "cliente",
                    "O cliente selecionado não está vinculado à viagem escolhida. "
                    "Por favor, vincule o cliente à viagem antes de criar o processo."
                )

                                                                        
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
                                                                                  
            self._criar_etapas(processo)

        return processo

    def _criar_etapas(self, processo: Processo) -> None:
                                                                                        
        etapas_selecionadas = self.cleaned_data.get('etapas_selecionadas', [])
        
        if not etapas_selecionadas:
                                                                                           
            status_vinculados = ViagemStatusProcesso.objects.filter(
                viagem=processo.viagem,
                ativo=True
            ).select_related('status').order_by('status__ordem', 'status__nome')
            
            for viagem_status in status_vinculados:
                status = viagem_status.status
                prazo_dias = status.prazo_padrao_dias if status.prazo_padrao_dias > 0 else 0
                
                EtapaProcesso.objects.get_or_create(
                    processo=processo,
                    status=status,
                    defaults={
                        'prazo_dias': prazo_dias,
                        'ordem': status.ordem,
                    }
                )
        else:
                                                 
            from consultancy.models import StatusProcesso
            status_ids = [int(sid) for sid in etapas_selecionadas]
            status_selecionados = StatusProcesso.objects.filter(pk__in=status_ids)
            
            for status in status_selecionados:
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
