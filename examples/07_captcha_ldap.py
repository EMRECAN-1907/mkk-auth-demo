"""
Example 7: Captcha + LDAP
==========================

Bu örnek iki kritik özelliği gösteriyor:
  1. Image captcha — kütüphane kodu üretir, uygulama image'a çevirir
  2. LDAP entegrasyonu — corporate AD/LDAP üzerinden auth

Run:  python examples/07_captcha_ldap.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import InMemoryLdapProvider


# Mock LDAP/AD
LDAP_DATA = {
    "demo": ("ldap1234", {
        "cn": "Demo User",
        "dn": "cn=demo,ou=users,dc=mkk,dc=local",
        "memberOf": ["users", "developers"],
    }),
}


def main():
    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "06_captcha_ldap.json",
        providers={"ldap": InMemoryLdapProvider(LDAP_DATA)},
        logger=LoggerFactory.console(),
    )

    print("\n=== Image Captcha + LDAP ===\n")

    # Step 1: İlk çağrı - captcha kodu üretilir
    print("Step 1: Engine'i başlat — captcha kodu üret")
    state = engine.start(form_data={})
    sid = state.context["session_id"]
    print(f"  Outcome: {state.outcome.value}")
    print(f"  Şu an: {state.current_step.stages[0].name}")
    print(f"  (Gerçek uygulamada burada captcha resmi render edilirdi)")

    # Geliştirme modunda kütüphanenin ürettiği kodu okuyalım
    # (Production'da uygulama kodu image olarak render edip kullanıcıya gösterir)
    # Bu test için kütüphane'nin internal state'ine bakacağız:
    import pickle
    raw = engine.session_store.load(sid)
    ctx = pickle.loads(raw)
    captcha_code = ctx._captcha_codes.get("0_0", "")
    print(f"\n  💡 [Kütüphane şu kodu üretti: '{captcha_code}']")

    # Step 1 devam: Kullanıcı kodu girer
    print(f"\nStep 1 (devam): Kullanıcı kodu girer")
    state = engine.resume(sid, form_data={"s_0_0_in": captcha_code})
    print(f"  Outcome: {state.outcome.value}")
    if state.current_step:
        print(f"  Sonraki: {state.current_step.stages[0].name}")

    # Step 2: LDAP bind
    print(f"\nStep 2: LDAP bind")
    state = engine.resume(sid, form_data={
        "s_1_0_u": "demo",
        "s_1_0_p": "ldap1234",
    })

    if state.is_success:
        user = state.context["identified_user"]
        print(f"\n  ✅ GİRİŞ BAŞARILI!")
        print(f"     CN: {user.get('cn')}")
        print(f"     DN: {user.get('dn')}")
        print(f"     Member of: {user.get('memberOf')}")
    else:
        print(f"  ⚠ Sonuç: {state.outcome.value}")


if __name__ == "__main__":
    main()
