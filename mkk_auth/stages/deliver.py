"""
Deliver stages — category "deliver".

Sends OTPs/codes via SMS or Email. The user reads the code and types it back.
"""
from __future__ import annotations
import secrets
from typing import Any

from mkk_auth.exceptions import PolicyError
from mkk_auth.providers.protocols import OOBChannel
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import register
from mkk_auth.state import StageResult


def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 5:
        return phone or "***"
    return phone[:3] + "*" * (len(phone) - 5) + phone[-2:]


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return email
    return local[0] + "*" * (len(local) - 2) + local[-1] + "@" + domain


class _OobBase(BaseStage):
    """Shared logic for SMS and email OTP stages."""

    DEFAULT_OTP_LENGTH = 6

    def __init__(self, config: dict[str, Any], channel: OOBChannel):
        super().__init__(config)
        self.channel = channel

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "_OobBase":
        provider_key = cls._provider_key()
        ch = providers.get(provider_key)
        if ch is None:
            raise PolicyError(
                f"{cls.__name__} requires '{provider_key}' provider"
            )
        return cls(config=config, channel=ch)

    @classmethod
    def _provider_key(cls) -> str:
        raise NotImplementedError

    def _key(self, ctx: StageContext) -> str:
        return f"{ctx.step_index}_{ctx.column_index}"

    def _generate_code(self) -> str:
        length = self.config.get("otpLength", self.DEFAULT_OTP_LENGTH)
        return "".join(str(secrets.randbelow(10)) for _ in range(length))

    def _get_recipient(self, ctx: StageContext) -> str:
        raise NotImplementedError

    def _mask(self, recipient: str) -> str:
        raise NotImplementedError

    def evaluate(self, ctx: StageContext) -> StageResult:
        key = self._key(ctx)

        # First call: generate + send code, return PENDING
        if key not in ctx.auth_context._otp_codes:
            recipient = self._get_recipient(ctx)
            if not recipient:
                # If config says "skip if no recipient", auto-succeed.
                # Useful for branching flows: e.g. external_idp users who
                # don't have a phone/email registered → just skip OOB step.
                if self.config.get("skipIfNoRecipient"):
                    ctx.logger.info(
                        "oob.skipped",
                        f"{self.DISPLAY_NAME} skipped: no recipient available",
                        stage_type=self.STAGE_TYPE,
                    )
                    return StageResult.success(
                        f"{self.DISPLAY_NAME} atlandı (alıcı bilgisi yok)"
                    )
                # In parallel scenarios, identified_user may be set by a sibling
                # stage that hasn't completed yet. Return PENDING so the engine
                # keeps the flow alive — sibling stages will populate it.
                return StageResult.pending(
                    "Alıcı bilgisi henüz hazır değil — paralel adımı bekliyorum"
                )

            code = self._generate_code()
            ctx.auth_context._otp_codes[key] = code

            ok = self.channel.send(recipient, code, options=self.config)
            if not ok:
                ctx.logger.error(
                    "oob.send_failed",
                    f"Failed to send code via {self.STAGE_TYPE}",
                    stage_type=self.STAGE_TYPE,
                    user_identifier=self._mask(recipient),
                )
                return StageResult.failed("Kod gönderilemedi")

            ctx.logger.info(
                "oob.code_sent",
                f"Code sent via {self.STAGE_TYPE}",
                stage_type=self.STAGE_TYPE,
                step_index=ctx.step_index,
                user_identifier=self._mask(recipient),
                attributes={"length": len(code)},
            )
            return StageResult.pending("Kod gönderildi, kullanıcıdan bekleniyor")

        # Subsequent calls: verify input
        user_code = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if not user_code:
            return StageResult.pending("Kod bekleniyor")

        expected = ctx.auth_context._otp_codes[key]
        if user_code != expected:
            ctx.logger.warn(
                "stage.failed",
                "OTP code mismatch",
                stage_type=self.STAGE_TYPE,
                step_index=ctx.step_index,
            )
            return StageResult.failed("Kod yanlış", field=in_field)

        ctx.auth_context.verified = True
        ctx.logger.info(
            "stage.success",
            "OTP verified",
            stage_type=self.STAGE_TYPE,
            step_index=ctx.step_index,
        )
        return StageResult.success()


@register
class SmsOobStage(_OobBase):
    STAGE_TYPE = "sms_oob"
    CATEGORY = "deliver"
    DISPLAY_NAME = "SMS OTP"

    @classmethod
    def _provider_key(cls) -> str:
        return "sms"

    def _get_recipient(self, ctx: StageContext) -> str:
        user = ctx.auth_context.identified_user or {}
        return user.get("phone", "")

    def _mask(self, recipient: str) -> str:
        return _mask_phone(recipient)


@register
class EmailOobStage(_OobBase):
    STAGE_TYPE = "email_oob"
    CATEGORY = "deliver"
    DISPLAY_NAME = "Email OTP"

    @classmethod
    def _provider_key(cls) -> str:
        return "email"

    def _get_recipient(self, ctx: StageContext) -> str:
        user = ctx.auth_context.identified_user or {}
        return user.get("email", "")

    def _mask(self, recipient: str) -> str:
        return _mask_email(recipient)
