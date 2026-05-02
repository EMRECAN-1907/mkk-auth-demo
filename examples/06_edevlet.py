"""
Example 6: e-Devlet ile Giriş (External IDP redirect)
======================================================

External IDP akışını sahneliyor:
  1. Engine, kullanıcıyı e-Devlet'e yönlendirmek için redirect URL üretir
  2. Uygulama tarayıcıyı oraya gönderir
  3. Kullanıcı e-Devlet'te giriş yapar
  4. e-Devlet, callback URL'ye `code` ile döner
  5. Engine, code'u user info için exchange eder

Run:  python examples/06_edevlet.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import InMemoryExternalIdp


def main():
    # Mock e-Devlet provider — herhangi bir code'ı kabul eder
    edevlet = InMemoryExternalIdp(
        base_url="https://giris.turkiye.gov.tr/oauth2/authorize",
        fake_user={
            "tckn": "11111111110",
            "name": "Emrecan Bayhan",
            "verified_at": "edevlet",
            "verified_via": "TC Kimlik",
        },
    )

    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "05_edevlet.json",
        providers={"idp": edevlet},
        logger=LoggerFactory.console(),
    )

    print("\n=== e-Devlet ile Giriş ===\n")

    # 1) İlk çağrı: redirect URL'yi al
    print("Step 1: Engine'i başlat — kullanıcıyı e-Devlet'e yönlendir")
    state = engine.start(form_data={})
    sid = state.context["session_id"]

    redirect = state.context.get("pending_data", {}).get("redirect_url", "")
    print(f"  ↗ Tarayıcı buraya yönlendirilecek:")
    print(f"    {redirect}")

    # 2) Kullanıcı e-Devlet'te giriş yapıyor varsayalım
    print("\n  ⏱  [Kullanıcı e-Devlet sayfasında giriş yapıyor...]")
    print("    [e-Devlet, callback'e ?code=ABC123 ile döner]")

    # 3) Callback - engine code'u verirse user_info'ya çevirir
    print("\nStep 2: Callback — code'u engine'e geri ver")
    state = engine.resume(sid, form_data={"s_0_0_code": "ABC123_oauth_code_xyz"})

    if state.is_success:
        user = state.context["identified_user"]
        print(f"\n  ✅ GİRİŞ BAŞARILI!")
        print(f"     Kim: {user.get('name')}")
        print(f"     TCKN: {user.get('tckn')}")
        print(f"     Provider: {user.get('provider')}")
        print(f"     Doğrulayan: {user.get('verified_at')}")
    else:
        print(f"  ⚠ Sonuç: {state.outcome.value}")


if __name__ == "__main__":
    main()
