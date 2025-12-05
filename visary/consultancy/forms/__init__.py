"""
Formulários do domínio de consultoria.
"""

from .client_forms import ClienteConsultoriaForm
from .etapa_forms import (
    CampoEtapaClienteForm,
    CampoEtapaClienteInlineForm,
    EtapaCadastroClienteForm,
)
from .financial_forms import DarBaixaFinanceiroForm
from .form_forms import FormularioVistoForm, PerguntaFormularioForm
from .opcao_forms import OpcaoSelecaoForm
from .partners_forms import PartnerForm
from .process_forms import EtapaProcessoForm, ProcessoForm
from .status_processo_forms import StatusProcessoForm
from .travel_forms import PaisDestinoForm, TipoVistoForm, ViagemForm

__all__ = (
    "CampoEtapaClienteForm",
    "CampoEtapaClienteInlineForm",
    "ClienteConsultoriaForm",
    "DarBaixaFinanceiroForm",
    "EtapaCadastroClienteForm",
    "EtapaProcessoForm",
    "FormularioVistoForm",
    "OpcaoSelecaoForm",
    "PartnerForm",
    "PaisDestinoForm",
    "PerguntaFormularioForm",
    "ProcessoForm",
    "StatusProcessoForm",
    "TipoVistoForm",
    "ViagemForm",
)

