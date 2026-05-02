"""
Auth stages — category "auth".

These stages perform actual identity proof: knowing a secret, possessing
a token, presenting biometrics.
"""
from __future__ import annotations
import time
from typing import Any, Optional

from mkk_auth.exceptions import PolicyError
from mkk_auth.providers.protocols import (
    CredentialStore, LdapProvider, ESignProvider,
    MobileSignProvider, PushProvider,
)
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import register
from mkk_auth.state import StageResult


@register
class UserpassStage(BaseStage):
    """
    Identifier + password (configurable identifier type).
    Identifier types: username, tckn, vkn, sicil, uye_no, yatirimci_no,
                      passport, vergi_no, hesap_no, iban, email, custom.
    """
    STAGE_TYPE = "userpass"
    CATEGORY = "auth"
    DISPLAY_NAME = "Identifier + Şifre"

    def __init__(self, config: dict[str, Any], credentials: CredentialStore):
        super().__init__(config)
        self.credentials = credentials

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "UserpassStage":
        creds = providers.get("credentials")
        if creds is None:
            raise PolicyError("UserpassStage requires 'credentials' provider")
        return cls(config=config, credentials=creds)

    def evaluate(self, ctx: StageContext) -> StageResult:
        identifier = self.get_input(ctx, "u")
        password = self.get_input(ctx, "p")
        u_field = self.field_name("u", ctx.step_index, ctx.column_index)
        p_field = self.field_name("p", ctx.step_index, ctx.column_index)

        if not identifier:
            return StageResult.pending("Kullanıcı adı bekleniyor")
        if not password:
            return StageResult.pending("Şifre bekleniyor")

        identifier_type = self.config.get("identifierType", "username")

        # Validate format if regex provided
        validation = self.config.get("validation")
        if validation and validation != ".+":
            import re
            if not re.fullmatch(validation, identifier):
                return StageResult.failed(
                    f"{identifier_type} formatı geçersiz", field=u_field
                )

        # Track who's trying to login - used by rate limiter even on failure
        ctx.auth_context.attempted_identifier = identifier

        # Rate-limit pre-check: if this account is locked, don't even try
        # The engine reads attempted_identifier and checks before next call,
        # but for the same call, we need an explicit hook
        # (Engine calls _rate_limit_key which now reads attempted_identifier)

        ctx.logger.info(
            "stage.start",
            f"Verifying credentials ({identifier_type})",
            stage_type=self.STAGE_TYPE,
            step_index=ctx.step_index,
            user_identifier=self.mask_pii(identifier),
        )

        record = self.credentials.verify(identifier_type, identifier, password)
        if record is None:
            ctx.logger.warn(
                "stage.failed",
                "Invalid credentials",
                stage_type=self.STAGE_TYPE,
                user_identifier=self.mask_pii(identifier),
                attributes={"identifier_type": identifier_type},
            )
            return StageResult.failed("Geçersiz kullanıcı/şifre")

        ctx.auth_context.identified_user = {
            "identifier": identifier,
            "identifier_type": identifier_type,
            **record,
        }
        ctx.logger.info(
            "stage.success",
            "Credentials verified",
            stage_type=self.STAGE_TYPE,
            user_identifier=self.mask_pii(identifier),
        )
        return StageResult.success()

    def get_input_descriptors(self, ctx: StageContext) -> list[dict]:
        return [
            {
                "name": self.field_name("u", ctx.step_index, ctx.column_index),
                "label": self.config.get("inputLabel", "Kullanıcı adı"),
                "type": "text",
                "validation": self.config.get("validation", ".+"),
            },
            {
                "name": self.field_name("p", ctx.step_index, ctx.column_index),
                "label": self.config.get("passwordLabel", "Şifre"),
                "type": "password",
            },
        ]


@register
class LdapStage(BaseStage):
    """LDAP/AD bind."""
    STAGE_TYPE = "ldap"
    CATEGORY = "auth"
    DISPLAY_NAME = "LDAP / AD"

    def __init__(self, config: dict[str, Any], ldap: LdapProvider):
        super().__init__(config)
        self.ldap = ldap

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "LdapStage":
        ldap = providers.get("ldap")
        if ldap is None:
            raise PolicyError("LdapStage requires 'ldap' provider")
        return cls(config=config, ldap=ldap)

    def evaluate(self, ctx: StageContext) -> StageResult:
        username = self.get_input(ctx, "u")
        password = self.get_input(ctx, "p")
        u_field = self.field_name("u", ctx.step_index, ctx.column_index)

        if not username or not password:
            return StageResult.pending("Kullanıcı adı ve şifre bekleniyor")

        ctx.logger.info(
            "stage.start", "LDAP bind",
            stage_type=self.STAGE_TYPE,
            user_identifier=self.mask_pii(username),
        )

        attrs = self.ldap.bind(username, password)
        if attrs is None:
            return StageResult.failed("LDAP bind başarısız")

        ctx.auth_context.identified_user = {"username": username, **attrs}
        return StageResult.success()


@register
class TotpStage(BaseStage):
    """
    TOTP — typically 6-digit code from Google Authenticator.
    For demo purposes, accepts any 6-digit value (real impl uses pyotp).
    """
    STAGE_TYPE = "totp"
    CATEGORY = "auth"
    DISPLAY_NAME = "TOTP"

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "TotpStage":
        return cls(config=config)

    def evaluate(self, ctx: StageContext) -> StageResult:
        code = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)
        if not code:
            return StageResult.pending("TOTP kodu bekleniyor")

        import re
        if not re.fullmatch(r"\d{6}", code):
            return StageResult.failed("6 haneli kod olmalı", field=in_field)

        # Real impl: pyotp.TOTP(secret).verify(code)
        # Demo: any 6 digits except 000000 passes
        if code == "000000":
            return StageResult.failed("TOTP doğrulanamadı", field=in_field)

        ctx.auth_context.verified = True
        return StageResult.success()


@register
class ESignStage(BaseStage):
    """e-İmza — USB token + certificate signing."""
    STAGE_TYPE = "esign"
    CATEGORY = "auth"
    DISPLAY_NAME = "e-İmza"

    def __init__(self, config: dict[str, Any], esign: ESignProvider):
        super().__init__(config)
        self.esign = esign

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "ESignStage":
        esign = providers.get("esign")
        if esign is None:
            raise PolicyError("ESignStage requires 'esign' provider")
        return cls(config=config, esign=esign)

    def evaluate(self, ctx: StageContext) -> StageResult:
        pin = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if not pin:
            return StageResult.pending("PIN bekleniyor")

        # In real impl, signed_data comes from a client-side signing applet
        signed_data = b"<demo signed data>"
        cert_subject = self.esign.verify_signature(signed_data, pin)
        if cert_subject is None:
            return StageResult.failed("e-İmza doğrulaması başarısız", field=in_field)

        # Merge cert_subject with existing identified_user.
        # Preserve phone/email from earlier stages — cert won't have them.
        existing = ctx.auth_context.identified_user or {}
        merged = {**existing, **cert_subject}
        for field in ("phone", "email"):
            if field not in cert_subject and field in existing:
                merged[field] = existing[field]
        ctx.auth_context.identified_user = merged
        ctx.logger.info(
            "stage.success",
            "e-Sign verified",
            stage_type=self.STAGE_TYPE,
            attributes={"subject_cn": cert_subject.get("name", "")},
        )
        return StageResult.success()


@register
class MobileSignStage(BaseStage):
    """Mobile signature via operator (Turkcell, Vodafone, TT)."""
    STAGE_TYPE = "mobile_sign"
    CATEGORY = "auth"
    DISPLAY_NAME = "Mobil İmza"

    def __init__(self, config: dict[str, Any], mobile_sign: MobileSignProvider):
        super().__init__(config)
        self.mobile_sign = mobile_sign

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "MobileSignStage":
        ms = providers.get("mobile_sign")
        if ms is None:
            raise PolicyError("MobileSignStage requires 'mobile_sign' provider")
        return cls(config=config, mobile_sign=ms)

    def evaluate(self, ctx: StageContext) -> StageResult:
        # Multi-call stage: first send, then poll
        key = f"mobsign_{ctx.step_index}_{ctx.column_index}"
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        if key not in ctx.auth_context._otp_codes:
            user = ctx.auth_context.identified_user or {}
            phone = user.get("phone", "")
            if not phone:
                return StageResult.failed("Telefon yok")

            operator = self.config.get("operator", "auto")
            challenge = f"MKK-Auth-{int(time.time())}"
            req_id = self.mobile_sign.request_signature(phone, operator, challenge)
            ctx.auth_context._otp_codes[key] = req_id

            ctx.logger.info(
                "mobile_sign.requested", "Mobile signature requested",
                stage_type=self.STAGE_TYPE,
                attributes={"operator": operator, "request_id": req_id},
            )
            return StageResult.pending(
                "Telefonuna gelen isteği onayla",
                request_id=req_id,
            )

        # Polling: check if user has approved on phone
        req_id = ctx.auth_context._otp_codes[key]
        result = self.mobile_sign.poll_result(req_id)
        if result is None:
            # Demo mode: auto-approve on second submit (user pressed "Devam" or
            # "Bu yöntemle Giriş"). In production this would be a real poll.
            # If form has any data OR if it's a second call (key exists),
            # treat as approved for demo purposes.
            user_code = self.get_input(ctx, "in")
            if user_code and user_code != "000000":
                return StageResult.success()
            # Auto-approve: mark as approved in provider and succeed
            if hasattr(self.mobile_sign, "approve"):
                self.mobile_sign.approve(req_id)
                return StageResult.success()
            return StageResult.pending("Hala kullanıcı onayı bekleniyor")

        ctx.auth_context.verified = True
        return StageResult.success()


@register
class PushApproveStage(BaseStage):
    """
    Push notification + tap-to-approve.
    No text input from user; approval comes through the push provider.
    """
    STAGE_TYPE = "push_approve"
    CATEGORY = "auth"
    DISPLAY_NAME = "Push Onay"

    def __init__(self, config: dict[str, Any], push: PushProvider):
        super().__init__(config)
        self.push = push

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "PushApproveStage":
        push = providers.get("push")
        if push is None:
            raise PolicyError("PushApproveStage requires 'push' provider")
        return cls(config=config, push=push)

    def evaluate(self, ctx: StageContext) -> StageResult:
        key = f"push_{ctx.step_index}_{ctx.column_index}"

        if key not in ctx.auth_context._otp_codes:
            user = ctx.auth_context.identified_user or {}
            user_id = user.get("identifier") or user.get("tckn") or user.get("username", "")
            if not user_id:
                return StageResult.failed("Kullanıcı tanımlı değil")

            req_id = self.push.send_approval_request(user_id, {
                "type": "login_approval",
                "ip": ctx.auth_context.request_metadata.get("ip", "unknown"),
                "device": ctx.auth_context.request_metadata.get("user_agent", ""),
                "timestamp": time.time(),
            })
            ctx.auth_context._otp_codes[key] = req_id

            ctx.logger.info(
                "push.sent", "Push approval requested",
                stage_type=self.STAGE_TYPE,
                user_identifier=self.mask_pii(user_id),
                attributes={"request_id": req_id},
            )
            return StageResult.pending("Push gönderildi", request_id=req_id)

        # Polling: did the user approve?
        req_id = ctx.auth_context._otp_codes[key]
        response = self.push.poll_response(req_id)

        if response is None:
            return StageResult.pending("Hala kullanıcı onayı bekleniyor")
        if response == "rejected":
            ctx.logger.warn(
                "push.rejected", "User rejected push",
                stage_type=self.STAGE_TYPE,
            )
            return StageResult.failed("Kullanıcı reddetti")
        if response == "approved":
            ctx.auth_context.verified = True
            ctx.logger.info("push.approved", "User approved push", stage_type=self.STAGE_TYPE)
            return StageResult.success()

        return StageResult.failed(f"Beklenmeyen yanıt: {response}")


@register
class MobileAuthenticatorStage(BaseStage):
    """
    Mobile authenticator — like Google's "tap the matching number" UX.
    Library generates a challenge; user sees the same number on browser
    and phone, taps the right one with biometrics.
    """
    STAGE_TYPE = "mobile_authenticator"
    CATEGORY = "auth"
    DISPLAY_NAME = "Mobil Authenticator"

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "MobileAuthenticatorStage":
        return cls(config=config)

    def evaluate(self, ctx: StageContext) -> StageResult:
        key = f"mobauth_{ctx.step_index}_{ctx.column_index}"
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)

        # First call: generate challenge
        if key not in ctx.auth_context._otp_codes:
            import secrets
            length = self.config.get("challengeLength", 8)
            min_val = 10 ** (length - 1)
            max_val = 10 ** length - 1
            challenge = str(secrets.randbelow(max_val - min_val) + min_val)
            ctx.auth_context._otp_codes[key] = challenge

            ctx.logger.info(
                "mobile_auth.challenge", "Authenticator challenge sent",
                stage_type=self.STAGE_TYPE,
                attributes={"challenge_length": length},
            )
            return StageResult.pending(
                "Telefondan onayla",
                challenge=challenge,
            )

        user_code = self.get_input(ctx, "in")
        if not user_code:
            return StageResult.pending("Kod bekleniyor")

        expected = ctx.auth_context._otp_codes[key]
        if user_code != expected:
            return StageResult.failed("Kod yanlış", field=in_field)

        ctx.auth_context.verified = True
        return StageResult.success()
