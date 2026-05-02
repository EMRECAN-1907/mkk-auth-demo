"""
Universal Policy Runner
========================

Bu script, builder'dan indirdiğin HERHANGİ BİR JSON dosyasını alıp
interaktif olarak çalıştırır. Yani:

    1. flow_builder.html'i aç
    2. Bir akış kur (mersis → temsilci → SMS, ya da herhangi başka)
    3. JSON'u indir
    4. python examples/run_policy.py path/to/policy.json

Komut satırından bu script seni adım adım yönlendirir, her stage için
input ister, sonunda akış tamamlanır.

Kullanım:
    python examples/run_policy.py policies/01_aracikurum.json
    python examples/run_policy.py /path/to/builder_export.json

Bu script her stage tipine nasıl input vereceğini bilir. Ek olarak:
- Mock provider'lar otomatik olarak hangilerinin gerektiğini görür
- SMS/Email kodları konsola yazdırılır (gerçekte gönderilirdi)
- Push onayı "Enter = onayla / r = reddet" ile sahnelenir
- e-Devlet redirect ekrana yazılır, callback otomatik döner
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from typing import Any, Optional

# Project root'u import path'e ekle
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory, Policy, AuthOutcome
from mkk_auth.providers.memory import (
    InMemoryLookupProvider, InMemoryOOBChannel, InMemoryCredentialStore,
    InMemoryLdapProvider, InMemoryRateLimiter,
    InMemoryPushProvider, InMemoryExternalIdp, InMemoryESignProvider,
    InMemoryMobileSignProvider,
)


# ============================================================
# Mock data — runner herhangi bir policy ile çalışsın diye
# elimizde geniş bir test verisi olsun
# ============================================================

MERSIS_DATA = {
    "0123456789012345": {
        "company_name": "Acme Aracı Kurum A.Ş.",
        "representatives": [
            {"tckn": "11111111110", "sicil": "001234", "name": "Emrecan Bayhan",
             "phone": "05321234567", "email": "emrecan@acme.com.tr"},
            {"tckn": "22222222220", "sicil": "005678", "name": "Ali Yılmaz",
             "phone": "05332345678", "email": "ali@acme.com.tr"},
        ],
    },
    "9876543210987654": {
        "company_name": "Beta Holding A.Ş.",
        "representatives": [
            {"tckn": "33333333330", "sicil": "009999", "name": "Veli Demir",
             "phone": "05551234567", "email": "veli@beta.com.tr"},
        ],
    },
}

TCKN_DATA = {
    "11111111110": {"tckn": "11111111110", "name": "Emrecan Bayhan",
                    "phone": "05321234567", "email": "emrecan@acme.com.tr"},
    "22222222220": {"tckn": "22222222220", "name": "Ali Yılmaz",
                    "phone": "05332345678", "email": "ali@acme.com.tr"},
    "44444444440": {"tckn": "44444444440", "name": "Test Kullanıcısı",
                    "phone": "05554443322", "email": "test@example.com"},
}

SICIL_DATA = {
    "001234": {"sicil": "001234", "name": "Emrecan Bayhan",
               "phone": "05321234567", "email": "emrecan@acme.com.tr"},
}

PASSPORT_DATA = {
    "U12345678": {"passport": "U12345678", "name": "John Smith",
                  "phone": "+14155552671", "email": "john@example.com",
                  "country": "USA"},
}

# Username + password tablosu, identifier_type → {identifier: (password, attrs)}
CREDENTIALS_DATA = {
    "username": {
        "demo": ("demo1234", {"name": "Demo User", "role": "user"}),
        "emrecan": ("test1234", {"name": "Emrecan B.", "role": "admin"}),
    },
    "tckn": {
        "11111111110": ("tckn1234", {"name": "Emrecan Bayhan",
                                      "phone": "05321234567"}),
        "22222222220": ("tckn5678", {"name": "Ali Yılmaz",
                                      "phone": "05332345678"}),
    },
    "vkn": {
        "1234567890": ("vkn1234", {"company": "Acme A.Ş."}),
    },
    "sicil": {
        "001234": ("sicil12", {"name": "Emrecan Bayhan", "department": "BT"}),
    },
    "passport": {
        "U12345678": ("pass1234", {"name": "John Smith", "country": "USA"}),
    },
    "mersis": {
        "0123456789012345": ("mersis12", {"company": "Acme A.Ş."}),
    },
    "generic": {
        # generic_lookup için
    },
    "email": {
        "test@example.com": ("email12", {"name": "Email User"}),
    },
}

LDAP_DATA = {
    "demo": ("ldap1234", {"cn": "Demo User", "dn": "cn=demo,ou=users",
                          "memberOf": ["users"]}),
    "admin": ("admin123", {"cn": "Admin User", "dn": "cn=admin,ou=admins",
                           "memberOf": ["admins", "users"]}),
}


# ============================================================
# Provider factory — policy'ye bakıp hangi provider'lar gerekli
# olduğunu otomatik belirler
# ============================================================

def discover_required_providers(policy: Policy) -> set[str]:
    """Policy'deki tüm stage'leri tara, hangi provider'lar lazım onları belirle."""
    required = set()
    for step in policy.steps:
        for item in step.items:
            t = item.type
            cfg = item.config
            if t in ("mersis_lookup", "tckn_standalone", "generic_lookup"):
                required.add("lookup")
                if cfg.get("requirePassword"):
                    required.add("credentials")
            elif t in ("userpass",):
                required.add("credentials")
            elif t == "ldap":
                required.add("ldap")
            elif t == "sms_oob":
                required.add("sms")
            elif t == "email_oob":
                required.add("email")
            elif t == "push_approve":
                required.add("push")
            elif t == "external_idp":
                required.add("idp")
            elif t == "esign":
                required.add("esign")
            elif t == "mobile_sign":
                required.add("mobile_sign")
            # totp, captcha, image_captcha, field_match, representative_select,
            # mobile_authenticator: provider gerektirmiyor
    return required


def build_providers(policy: Policy) -> dict[str, Any]:
    """Policy'nin gerektirdiği tüm provider'ları kur — in-memory ile."""
    needed = discover_required_providers(policy)
    providers = {}

    if "lookup" in needed:
        # Tüm lookup verilerini birleştir, key'e göre seç
        combined = {}
        combined.update(MERSIS_DATA)
        combined.update(TCKN_DATA)
        combined.update(SICIL_DATA)
        combined.update(PASSPORT_DATA)
        providers["lookup"] = InMemoryLookupProvider(combined)

    if "credentials" in needed:
        providers["credentials"] = InMemoryCredentialStore(CREDENTIALS_DATA)

    if "ldap" in needed:
        providers["ldap"] = InMemoryLdapProvider(LDAP_DATA)

    if "sms" in needed:
        providers["sms"] = InMemoryOOBChannel(
            sink=lambda phone, code, opts: print(
                f"\n  📱 [SMS  → {phone}] kod: {code}\n"
            )
        )

    if "email" in needed:
        providers["email"] = InMemoryOOBChannel(
            sink=lambda email, code, opts: print(
                f"\n  ✉  [EMAIL → {email}] kod: {code}\n"
            )
        )

    if "push" in needed:
        providers["push"] = InMemoryPushProvider()

    if "idp" in needed:
        providers["idp"] = InMemoryExternalIdp(
            base_url="https://giris.turkiye.gov.tr/oauth2/authorize",
            fake_user={
                "tckn": "11111111110", "name": "Emrecan Bayhan",
                "verified_at": "edevlet",
            },
        )

    if "esign" in needed:
        providers["esign"] = InMemoryESignProvider(
            fake_subject={"name": "Emrecan Bayhan", "tckn": "11111111110"}
        )

    if "mobile_sign" in needed:
        providers["mobile_sign"] = InMemoryMobileSignProvider(
            fake_user_attrs={"name": "Emrecan Bayhan", "verified_via": "mobil_imza"}
        )

    return providers


# ============================================================
# Input collector — current step'e göre kullanıcıdan input topla
# ============================================================

def prompt_inputs_from_policy_step(policy: Policy, step_idx: int) -> dict:
    """İlk çağrıda — policy'den direkt step bilgisini al, kullanıcıya sor."""
    if step_idx >= len(policy.steps):
        return {}
    step = policy.steps[step_idx]
    return _prompt_for_items(step.items, step_idx)


def prompt_inputs_from_state(state, providers: dict) -> dict:
    """Sonraki çağrılarda — state.current_step'e göre input topla."""
    if not state.current_step:
        return {}

    step_idx = state.current_step.step_number - 1
    form_data = {}

    for col_idx, stage_info in enumerate(state.current_step.stages):
        prefix = f"s_{step_idx}_{col_idx}_"
        st = stage_info.type
        cfg = stage_info.config

        print(f"\n  ┌─ {stage_info.name} ({stage_info.category}) ─────")

        # --- OOB stages: kod gösterilip kullanıcıdan istenir ---
        if st == "sms_oob":
            ch = providers.get("sms")
            if ch and ch.last_code():
                print(f"  │ (Yukarıda gönderilen SMS kodunu gir)")
            form_data[f"{prefix}in"] = input(f"  │ SMS Kodu: ").strip()

        elif st == "email_oob":
            ch = providers.get("email")
            if ch and ch.last_code():
                print(f"  │ (Yukarıda gönderilen Email kodunu gir)")
            form_data[f"{prefix}in"] = input(f"  │ Email Kodu: ").strip()

        # --- Push: provider üzerinden onaylanır ---
        elif st == "push_approve":
            push = providers.get("push")
            pending = state.context.get("pending_data", {})
            req_id = pending.get("request_id")
            if req_id and push:
                ans = input(f"  │ 📲 Push geldi! [Enter=Onayla, r=Reddet]: ").strip()
                if ans.lower().startswith("r"):
                    push.reject(req_id)
                    print(f"  │   → Reddedildi")
                else:
                    push.approve(req_id)
                    print(f"  │   → Onaylandı")
            # No form_data needed — provider handles it

        # --- Mobile authenticator: kullanıcı numara seçer ---
        elif st == "mobile_authenticator":
            pending = state.context.get("pending_data", {})
            challenge = pending.get("challenge", "")
            if challenge:
                print(f"  │ 📱 Telefonda gözüken numara: {challenge}")
            form_data[f"{prefix}in"] = input(f"  │ Numarayı tekrar gir: ").strip()

        # --- Mobile sign: provider'ı otomatik onayla ---
        elif st == "mobile_sign":
            ms = providers.get("mobile_sign")
            pending = state.context.get("pending_data", {})
            req_id = pending.get("request_id")
            if req_id and ms:
                ans = input(f"  │ 📲 Mobil imza isteği geldi [Enter=Onayla]: ").strip()
                ms.approve(req_id)
            else:
                form_data[f"{prefix}in"] = input(f"  │ Onay kodu: ").strip()

        # --- External IDP: redirect'i sahnele, sonra callback ---
        elif st == "external_idp":
            pending = state.context.get("pending_data", {})
            redirect = pending.get("redirect_url", "")
            provider = pending.get("provider", "external")
            if redirect:
                print(f"  │ 🌐 Tarayıcı şuraya gider: {redirect[:60]}...")
                input(f"  │    [Enter] tuşuna bas — {provider} sayfasında giriş yapmış say")
                # Demo callback code
                form_data[f"{prefix}code"] = "demo_oauth_code_xyz"

        # --- Image captcha: sahte renderlama ---
        elif st == "image_captcha":
            # Library kodu üretti, internal context'te tutuyor
            # Geliştirme için runner direkt context'ten okuyalım
            ctx_dict = state.context
            # _captcha_codes attribute'ünü context dict'inden alamayız (private)
            # Ama runner için, mock olarak rastgele bir kod alıp basitçe gösterelim
            print(f"  │ 🖼  [Demo: Burada bir image captcha resmi olurdu]")
            print(f"  │    Geliştirme modunda, herhangi bir 4-5 haneli kod gir")
            print(f"  │    (Gerçekte kullanıcı resimden okurdu)")
            form_data[f"{prefix}in"] = input(f"  │ Captcha kodu: ").strip()
            # NB: Demo olması için bu çoğu zaman fail olur — case_sensitive ayarı önemli

        # --- Diğer tüm stage'ler: standart input topla ---
        else:
            inputs = _prompt_for_items([_make_item(stage_info)], step_idx, col_offset=col_idx)
            form_data.update(inputs)

    return form_data


def _make_item(stage_info):
    """StageInfo'yu policy.StageConfig benzeri bir nesneye çevir."""
    class _Item:
        def __init__(self, info):
            self.type = info.type
            self.config = info.config
    return _Item(stage_info)


def _prompt_for_items(items: list, step_idx: int, col_offset: int = 0) -> dict:
    """Items listesini gez, her biri için input topla."""
    form_data = {}
    for i, item in enumerate(items):
        col_idx = col_offset if col_offset else i
        prefix = f"s_{step_idx}_{col_idx}_"
        t = item.type
        cfg = item.config

        if t in ("mersis_lookup", "tckn_standalone", "generic_lookup"):
            label = cfg.get("inputLabel", "Değer")
            form_data[f"{prefix}in"] = input(f"  │ {label}: ").strip()
            if cfg.get("requirePassword"):
                pw_label = cfg.get("passwordLabel", "Şifre")
                form_data[f"{prefix}p"] = input(f"  │ {pw_label}: ").strip()

        elif t == "field_match":
            label = cfg.get("inputLabel", "Değer")
            form_data[f"{prefix}in"] = input(f"  │ {label}: ").strip()

        elif t == "representative_select":
            # auto-skip ise zaten kütüphane atlar, biz boş geçeriz
            choice = input(f"  │ Temsilci TCKN'si: ").strip()
            form_data[f"{prefix}selected"] = choice

        elif t == "captcha":
            form_data[f"{prefix}in"] = input(f"  │ Captcha (mock — herhangi bir değer): ").strip()

        elif t in ("userpass",):
            label = cfg.get("inputLabel", "Kullanıcı")
            pw_label = cfg.get("passwordLabel", "Şifre")
            form_data[f"{prefix}u"] = input(f"  │ {label}: ").strip()
            form_data[f"{prefix}p"] = input(f"  │ {pw_label}: ").strip()

        elif t == "ldap":
            form_data[f"{prefix}u"] = input(f"  │ Kullanıcı adı: ").strip()
            form_data[f"{prefix}p"] = input(f"  │ Şifre: ").strip()

        elif t == "totp":
            form_data[f"{prefix}in"] = input(f"  │ TOTP kodu (000000 dışında 6 hane): ").strip()

        elif t == "esign":
            form_data[f"{prefix}in"] = input(f"  │ e-İmza PIN (0000 dışında 4+ hane): ").strip()
        # Diğerleri (sms_oob, email_oob, push_approve, external_idp, vb.) burada gelmez —
        # onlar sadece state-pending modunda olur, prompt_inputs_from_state'de toplanır

    return form_data


# ============================================================
# Pretty printer — state'i göster
# ============================================================

def print_separator():
    print("─" * 60)


def print_state_summary(state, step_num: int):
    print()
    print_separator()
    print(f"  Outcome: {state.outcome.value.upper()}")

    if state.errors:
        for err in state.errors:
            print(f"    ⚠ {err.message}")

    user = state.context.get("identified_user")
    if user:
        name = user.get("name", "?")
        ident = (user.get("tckn") or user.get("identifier")
                 or user.get("username") or "?")
        print(f"  Tanımlı kullanıcı: {name} ({ident})")

    mersis = state.context.get("mersis_data")
    if mersis and not user:
        print(f"  Şirket: {mersis.get('company_name', '?')}")
        reps = mersis.get("representatives", [])
        if reps:
            print(f"  Temsilciler:")
            for r in reps:
                print(f"    • {r.get('name')} (TCKN: {r.get('tckn')})")

    if state.attempts_remaining:
        for stage_type, n in state.attempts_remaining.items():
            print(f"  Kalan deneme: {stage_type}={n}")

    print_separator()


# ============================================================
# Main loop
# ============================================================

def run(policy_path: Path, verbose: bool = False):
    print()
    print("╔" + "═" * 58 + "╗")
    print(f"║  MKK Auth — Universal Policy Runner".ljust(59) + "║")
    print(f"║  Policy: {policy_path.name}".ljust(59) + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    # 1) Policy'yi yükle
    policy = Policy.from_file(policy_path)
    print(f"  Policy yüklendi: {policy.display_name}")
    print(f"  Uygulama:        {policy.app_label or '(yok)'}")
    print(f"  Adım sayısı:     {len(policy.steps)}")
    print(f"  Açıklama:        {policy.description or '(yok)'}")

    # 2) Provider'ları otomatik kur
    needed = discover_required_providers(policy)
    print(f"  Gereken provider'lar: {sorted(needed) or '(yok)'}")
    providers = build_providers(policy)

    # 3) Engine'i kur
    engine = AuthEngine(
        policy=policy,
        providers=providers,
        logger=LoggerFactory.console(verbose=verbose),
        rate_limiter=InMemoryRateLimiter(max_failures=5, lockout_seconds=60),
    )

    # 4) İlk adım: policy'ye bakıp inputları topla, sonra start çağır
    print()
    print(f"╶─ Adım 1/{len(policy.steps)}: {_step_label(policy, 0)} ─╴")
    form_data = prompt_inputs_from_policy_step(policy, 0)

    state = engine.start(form_data=form_data)
    print_state_summary(state, 1)

    # 5) Loop: pending olduğu sürece devam et
    step_count = 1
    while state.outcome == AuthOutcome.PENDING_INPUT:
        # Aynı adımda hata ile döndüyse → tekrar input al
        # Yeni adıma geçtiyse → adım numarasını güncelle
        current_step_num = state.current_step.step_number if state.current_step else step_count
        if current_step_num > step_count:
            step_count = current_step_num
            print()
            print(f"╶─ Adım {step_count}/{len(policy.steps)}: "
                  f"{_step_label(policy, step_count - 1)} ─╴")

        form_data = prompt_inputs_from_state(state, providers)
        sid = state.context["session_id"]
        state = engine.resume(sid, form_data=form_data)
        print_state_summary(state, step_count)

    # 6) Sonuç
    print()
    if state.outcome == AuthOutcome.SUCCESS:
        user = state.context.get("identified_user", {})
        print(f"  ✅ GİRİŞ BAŞARILI: {user.get('name', '?')}")
    elif state.outcome == AuthOutcome.LOCKED:
        print(f"  🔒 KİLİTLENDİ — {state.locked_until_seconds}s sonra dene")
    elif state.outcome == AuthOutcome.EXPIRED:
        print(f"  ⏱  ZAMAN DOLDU")
    elif state.outcome == AuthOutcome.FAILED:
        print(f"  ❌ BAŞARISIZ")
    print()


def _step_label(policy: Policy, idx: int) -> str:
    if idx >= len(policy.steps):
        return "?"
    step = policy.steps[idx]
    parts = [item.type for item in step.items]
    if len(parts) > 1:
        return " | ".join(parts) + " (paralel)"
    return parts[0]


# ============================================================
# Entry point
# ============================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Hata: policy JSON dosyası belirtmelisin.")
        print()
        print("Örnek:")
        print("  python examples/run_policy.py policies/01_aracikurum.json")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Dosya bulunamadı: {path}")
        sys.exit(1)

    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    try:
        run(path, verbose=verbose)
    except KeyboardInterrupt:
        print("\n\n  İptal edildi.")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ⚠ Hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
