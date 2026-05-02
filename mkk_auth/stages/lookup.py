"""
Lookup stages — category "identify".

Each one queries an external system to identify the user.
Optionally accepts a password for added security.
"""
from __future__ import annotations
from typing import Any, Optional

from mkk_auth.providers.protocols import LookupProvider, CredentialStore
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import register
from mkk_auth.state import StageResult


class _LookupStageBase(BaseStage):
    """Shared logic for all lookup-style identify stages."""
    LOOKUP_KEY: str = ""             # passed to LookupProvider.lookup(key=...)
    DEFAULT_PASSWORD_TYPE: str = ""  # for verifying password against CredentialStore

    def __init__(
        self,
        config: dict[str, Any],
        lookup_provider: LookupProvider,
        credentials: Optional[CredentialStore] = None,
    ):
        super().__init__(config)
        self.lookup_provider = lookup_provider
        self.credentials = credentials

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "_LookupStageBase":
        lookup = providers.get("lookup")
        if lookup is None:
            from mkk_auth.exceptions import PolicyError
            raise PolicyError(
                f"{cls.__name__} requires 'lookup' provider"
            )
        creds = providers.get("credentials") if config.get("requirePassword") else None
        if config.get("requirePassword") and creds is None:
            from mkk_auth.exceptions import PolicyError
            raise PolicyError(
                f"{cls.__name__} has requirePassword=true but no 'credentials' provider"
            )
        return cls(config=config, lookup_provider=lookup, credentials=creds)

    def get_input_descriptors(self, ctx: StageContext) -> list[dict]:
        descriptors = [{
            "name": self.field_name("in", ctx.step_index, ctx.column_index),
            "label": self.config.get("inputLabel", "Değer"),
            "type": "text",
            "validation": self.config.get("validation", ".+"),
        }]
        if self.config.get("requirePassword"):
            descriptors.append({
                "name": self.field_name("p", ctx.step_index, ctx.column_index),
                "label": self.config.get("passwordLabel", "Şifre"),
                "type": "password",
            })
        return descriptors


@register
class MersisLookupStage(_LookupStageBase):
    """
    Looks up a company by MERSIS number.
    Writes mersis_data to context (containing company + representatives).
    If only one representative exists, also writes identified_user directly.
    """
    STAGE_TYPE = "mersis_lookup"
    CATEGORY = "identify"
    DISPLAY_NAME = "MERSIS Sorgu"
    LOOKUP_KEY = "mersis"
    DEFAULT_PASSWORD_TYPE = "mersis"

    def evaluate(self, ctx: StageContext) -> StageResult:
        mersis_no = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if not mersis_no:
            return StageResult.pending("MERSIS numarası bekleniyor")

        ctx.logger.info(
            "provider.lookup",
            "MERSIS lookup",
            stage_type=self.STAGE_TYPE,
            step_index=ctx.step_index,
            user_identifier=self.mask_pii(mersis_no),
            attributes={"key": self.LOOKUP_KEY},
        )

        record = self.lookup_provider.lookup(self.LOOKUP_KEY, mersis_no)
        if record is None:
            ctx.logger.warn(
                "stage.failed",
                "MERSIS not found",
                stage_type=self.STAGE_TYPE,
                user_identifier=self.mask_pii(mersis_no),
            )
            return StageResult.failed("MERSIS bulunamadı", field=in_field)

        # Optional password check
        if self.config.get("requirePassword"):
            password = self.get_input(ctx, "p")
            p_field = self.field_name("p", ctx.step_index, ctx.column_index)
            if not password:
                return StageResult.pending("Şifre bekleniyor")
            verified = self.credentials.verify(
                self.DEFAULT_PASSWORD_TYPE, mersis_no, password
            )
            if verified is None:
                ctx.logger.warn(
                    "stage.failed",
                    "MERSIS password mismatch",
                    stage_type=self.STAGE_TYPE,
                    user_identifier=self.mask_pii(mersis_no),
                )
                return StageResult.failed("Şifre yanlış", field=p_field)

        # Persist results in auth context
        ctx.auth_context.mersis_data = record
        if len(record.get("representatives", [])) == 1:
            ctx.auth_context.identified_user = record["representatives"][0]

        return StageResult.success()


@register
class TcknStandaloneStage(_LookupStageBase):
    """
    Looks up an individual by TCKN.
    Writes identified_user to context.
    """
    STAGE_TYPE = "tckn_standalone"
    CATEGORY = "identify"
    DISPLAY_NAME = "TCKN Sorgu"
    LOOKUP_KEY = "tckn"
    DEFAULT_PASSWORD_TYPE = "tckn"

    def evaluate(self, ctx: StageContext) -> StageResult:
        tckn = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if not tckn:
            return StageResult.pending("TCKN bekleniyor")

        # Validate format
        validation = self.config.get("validation", r"\d{11}")
        import re
        if not re.fullmatch(validation, tckn):
            return StageResult.failed("TCKN formatı geçersiz", field=in_field)

        ctx.logger.info(
            "provider.lookup",
            "TCKN lookup",
            stage_type=self.STAGE_TYPE,
            step_index=ctx.step_index,
            user_identifier=self.mask_pii(tckn),
            attributes={"key": self.LOOKUP_KEY},
        )

        record = self.lookup_provider.lookup(self.LOOKUP_KEY, tckn)
        if record is None:
            return StageResult.failed("TCKN bulunamadı", field=in_field)

        # Optional password check
        if self.config.get("requirePassword"):
            password = self.get_input(ctx, "p")
            p_field = self.field_name("p", ctx.step_index, ctx.column_index)
            if not password:
                return StageResult.pending("Şifre bekleniyor")
            verified = self.credentials.verify(
                self.DEFAULT_PASSWORD_TYPE, tckn, password
            )
            if verified is None:
                return StageResult.failed("Şifre yanlış", field=p_field)

        ctx.auth_context.identified_user = record
        return StageResult.success()


@register
class GenericLookupStage(_LookupStageBase):
    """
    Configurable lookup against any provider.
    Reads `provider` config to know which lookup key to use.
    """
    STAGE_TYPE = "generic_lookup"
    CATEGORY = "identify"
    DISPLAY_NAME = "Generic Lookup"
    DEFAULT_PASSWORD_TYPE = "generic"

    def evaluate(self, ctx: StageContext) -> StageResult:
        value = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if not value:
            return StageResult.pending("Değer bekleniyor")

        provider_key = self.config.get("provider", "custom")

        ctx.logger.info(
            "provider.lookup",
            f"Generic lookup ({provider_key})",
            stage_type=self.STAGE_TYPE,
            step_index=ctx.step_index,
            user_identifier=self.mask_pii(value),
            attributes={"key": provider_key},
        )

        record = self.lookup_provider.lookup(provider_key, value)
        if record is None:
            return StageResult.failed(f"{provider_key} sorgusu sonuçsuz", field=in_field)

        if self.config.get("requirePassword"):
            password = self.get_input(ctx, "p")
            p_field = self.field_name("p", ctx.step_index, ctx.column_index)
            if not password:
                return StageResult.pending("Şifre bekleniyor")
            verified = self.credentials.verify(provider_key, value, password)
            if verified is None:
                return StageResult.failed("Şifre yanlış", field=p_field)

        ctx.auth_context.identified_user = record
        return StageResult.success()
