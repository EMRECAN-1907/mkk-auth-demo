"""
External Identity Provider stage.

Configurable for: e-Devlet, GIB, Google, Apple, Microsoft, AD FS, custom.
Implements the redirect-callback dance:
  1. Build authorize URL → return PENDING with redirect URL
  2. App redirects user to provider
  3. Provider sends user back with `code` parameter
  4. App calls engine again with the code → exchange for user info
"""
from __future__ import annotations
import secrets
from typing import Any

from mkk_auth.exceptions import PolicyError
from mkk_auth.providers.protocols import ExternalIdpProvider
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import register
from mkk_auth.state import StageResult


@register
class ExternalIdpStage(BaseStage):
    STAGE_TYPE = "external_idp"
    CATEGORY = "auth"
    DISPLAY_NAME = "Harici Kimlik Sağlayıcı"

    def __init__(self, config: dict[str, Any], idp: ExternalIdpProvider):
        super().__init__(config)
        self.idp = idp

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "ExternalIdpStage":
        # Pick provider by config name first, fall back to generic 'idp'
        provider_name = config.get("provider", "custom")
        idp = providers.get(f"idp_{provider_name}") or providers.get("idp")
        if idp is None:
            raise PolicyError(
                f"ExternalIdpStage requires 'idp' or 'idp_{provider_name}' provider"
            )
        return cls(config=config, idp=idp)

    def evaluate(self, ctx: StageContext) -> StageResult:
        key = f"idp_{ctx.step_index}_{ctx.column_index}"
        provider_name = self.config.get("provider", "custom")

        # If callback code arrived, exchange it
        callback_code = self.get_input(ctx, "code")
        if callback_code:
            ctx.logger.info(
                "external_idp.callback",
                f"{provider_name} callback received",
                stage_type=self.STAGE_TYPE,
                step_index=ctx.step_index,
                attributes={"provider": provider_name},
            )

            user_info = self.idp.exchange_code(callback_code)
            if user_info is None:
                return StageResult.failed(
                    f"{provider_name} token değişimi başarısız"
                )

            ctx.auth_context.identified_user = {
                "provider": provider_name,
                **user_info,
            }
            ctx.auth_context._idp_completed[key] = True
            return StageResult.success()

        # Otherwise, build authorize URL and pending
        if key not in ctx.auth_context._idp_completed:
            state_token = secrets.token_urlsafe(16)
            redirect_uri = self.config.get(
                "redirectUri",
                "https://mkk.com.tr/auth/callback",
            )
            auth_url = self.idp.build_authorize_url(state_token, redirect_uri)

            ctx.logger.info(
                "external_idp.redirect",
                f"Redirecting to {provider_name}",
                stage_type=self.STAGE_TYPE,
                step_index=ctx.step_index,
                attributes={
                    "provider": provider_name,
                    "state": state_token,
                },
            )
            return StageResult.pending(
                f"{provider_name} sayfasına yönlendiriliyor",
                redirect_url=auth_url,
                state=state_token,
                provider=provider_name,
            )

        return StageResult.success()
