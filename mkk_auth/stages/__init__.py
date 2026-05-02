"""
Stage implementations.

Each stage type from the JSON policy maps to a class here. The library
auto-registers all known stage types and the engine looks them up by name.

Java equivalent:
    Each stage = a class implementing AuthStage interface.
    Spring's @Component scanning auto-registers them.
    StageRegistry resolves by string type name.
"""
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import StageRegistry, get_default_registry

# Importing all stages registers them with the default registry
from mkk_auth.stages.lookup import MersisLookupStage, TcknStandaloneStage, GenericLookupStage
from mkk_auth.stages.verify import (
    FieldMatchStage,
    RepresentativeSelectStage,
    CaptchaStage,
    ImageCaptchaStage,
)
from mkk_auth.stages.deliver import SmsOobStage, EmailOobStage
from mkk_auth.stages.auth import (
    UserpassStage,
    LdapStage,
    TotpStage,
    ESignStage,
    MobileSignStage,
    PushApproveStage,
    MobileAuthenticatorStage,
)
from mkk_auth.stages.external import ExternalIdpStage

__all__ = [
    "BaseStage", "StageContext", "StageRegistry", "get_default_registry",
    "MersisLookupStage", "TcknStandaloneStage", "GenericLookupStage",
    "FieldMatchStage", "RepresentativeSelectStage", "CaptchaStage", "ImageCaptchaStage",
    "SmsOobStage", "EmailOobStage",
    "UserpassStage", "LdapStage", "TotpStage", "ESignStage", "MobileSignStage",
    "PushApproveStage", "MobileAuthenticatorStage",
    "ExternalIdpStage",
]
