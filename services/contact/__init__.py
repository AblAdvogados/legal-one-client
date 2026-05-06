"""
Pacote services/contact — caso de uso de criação e consulta de contatos.

Importações públicas:
    from services.contact import ContactService, build_payload, ContactPayload
    from domain.contact import (
        CreateContactInput, PersonalData, Address, Phone, CustomFields,
        ContactSummary, ContactDetails,
    )
"""

from services.contact.service import ContactService, build_payload
from services.contact.dto import ContactPayload

# Define a interface pública do pacote, controlando o que é exportado com from services.contact import *.
# Facilita refatoração e documentação da API pública, uma vez que permite identificar o que pode ser importado do módulo.
__all__ = [
    "ContactService",
    "build_payload",
    "ContactPayload",
]