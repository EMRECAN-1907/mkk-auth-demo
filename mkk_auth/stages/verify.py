"""
Verify stages — category "verify".

These stages disambiguate or confirm a user from candidates produced by
an earlier identify stage. They don't authenticate, just narrow down.
"""
from __future__ import annotations
import secrets
import string
from typing import Any

from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import register
from mkk_auth.state import StageResult


@register
class FieldMatchStage(BaseStage):
    """
    User submits a value, library checks if it matches a field on any
    record in mersis_data.representatives (or on identified_user).
    """
    STAGE_TYPE = "field_match"
    CATEGORY = "verify"
    DISPLAY_NAME = "Field Match"

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "FieldMatchStage":
        return cls(config=config)

    def evaluate(self, ctx: StageContext) -> StageResult:
        value = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)
        match_field = self.config.get("inputField", "tckn")

        if not value:
            return StageResult.pending("Değer bekleniyor")

        mersis = ctx.auth_context.mersis_data
        if not mersis:
            return StageResult.failed(
                "Önceki adımda liste yok", field=in_field
            )

        for rep in mersis.get("representatives", []):
            if str(rep.get(match_field, "")) == value:
                ctx.auth_context.selected_record = rep
                ctx.auth_context.identified_user = rep
                return StageResult.success()

        return StageResult.failed("Eşleşme bulunamadı", field=in_field)

    def get_input_descriptors(self, ctx: StageContext) -> list[dict]:
        return [{
            "name": self.field_name("in", ctx.step_index, ctx.column_index),
            "label": self.config.get("inputLabel", "Değer"),
            "type": "text",
        }]


@register
class RepresentativeSelectStage(BaseStage):
    """
    User picks one record from a list (e.g. company representatives).
    Auto-skips if only one option exists and config says so.
    """
    STAGE_TYPE = "representative_select"
    CATEGORY = "verify"
    DISPLAY_NAME = "Listeden Seç"

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "RepresentativeSelectStage":
        return cls(config=config)

    def evaluate(self, ctx: StageContext) -> StageResult:
        selected_tckn = self.get_input(ctx, "selected")
        field = self.field_name("selected", ctx.step_index, ctx.column_index)

        mersis = ctx.auth_context.mersis_data
        if not mersis:
            return StageResult.failed(
                "Listede temsilci yok", field=field
            )

        reps = mersis.get("representatives", [])
        # Auto-skip if single rep
        if self.config.get("autoSkipIfSingle", True) and len(reps) == 1:
            ctx.auth_context.selected_record = reps[0]
            ctx.auth_context.identified_user = reps[0]
            return StageResult.success()

        if not selected_tckn:
            return StageResult.pending("Temsilci seçimi bekleniyor")

        for rep in reps:
            if str(rep.get("tckn", "")) == selected_tckn:
                ctx.auth_context.selected_record = rep
                ctx.auth_context.identified_user = rep
                return StageResult.success()

        return StageResult.failed("Geçersiz seçim", field=field)


@register
class CaptchaStage(BaseStage):
    """Generic captcha (reCAPTCHA, Turnstile)."""
    STAGE_TYPE = "captcha"
    CATEGORY = "verify"
    DISPLAY_NAME = "Captcha"

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "CaptchaStage":
        return cls(config=config)

    def evaluate(self, ctx: StageContext) -> StageResult:
        token = self.get_input(ctx, "in")
        field = self.field_name("in", ctx.step_index, ctx.column_index)
        if not token:
            return StageResult.pending("Captcha bekleniyor")
        # In a real impl we'd verify via the provider's API.
        # For demo: any non-empty token passes.
        return StageResult.success()


@register
class ImageCaptchaStage(BaseStage):
    """
    Distorted-text image captcha. Library generates a random code, stores it
    in context, and the application renders it as an image.
    """
    STAGE_TYPE = "image_captcha"
    CATEGORY = "verify"
    DISPLAY_NAME = "Doğrulama Kodu"

    _CHARSET = "abcdefghijkmnpqrstuvwxyz23456789"  # exclude ambiguous 0/o/1/l

    @classmethod
    def from_config(cls, config: dict, providers: dict) -> "ImageCaptchaStage":
        return cls(config=config)

    def _key(self, ctx: StageContext) -> str:
        return f"{ctx.step_index}_{ctx.column_index}"

    def _generate_code(self) -> str:
        length = self.config.get("length", 5)
        return "".join(secrets.choice(self._CHARSET) for _ in range(length))

    def evaluate(self, ctx: StageContext) -> StageResult:
        key = self._key(ctx)
        # Generate code on first eval (i.e. before user submission)
        if key not in ctx.auth_context._captcha_codes:
            ctx.auth_context._captcha_codes[key] = self._generate_code()
            ctx.logger.debug(
                "captcha.generated",
                "Captcha code generated",
                stage_type=self.STAGE_TYPE,
                step_index=ctx.step_index,
            )
            return StageResult.pending("Kullanıcının resimden okuması bekleniyor")

        user_input = self.get_input(ctx, "in")
        in_field = self.field_name("in", ctx.step_index, ctx.column_index)
        if not user_input:
            return StageResult.failed("Doğrulama kodunu gir", field=in_field)

        expected = ctx.auth_context._captcha_codes[key]
        case_sensitive = self.config.get("caseSensitive", False)
        match = (
            user_input == expected
            if case_sensitive
            else user_input.lower() == expected.lower()
        )
        if not match:
            return StageResult.failed("Doğrulama kodu yanlış", field=in_field)

        return StageResult.success()
