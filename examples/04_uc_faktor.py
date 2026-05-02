"""
Example 4: 3 Faktörlü Tam Doğrulama
====================================
    TCKN+Şifre  →  SMS OTP  →  Push Onay

Hassas işlemler için klasik 3 faktör:
  - Bildiğin (şifre)
  - Sahip olduğun (telefondaki SMS)
  - Olduğun (push onayı + biyometrik)

Bu örnek 4 senaryo gösterir:
  1. Tüm doğru → SUCCESS
  2. Yanlış şifre → FAILED
  3. Yanlış SMS kodu → FAILED
  4. Push reddet → FAILED

Run:  python examples/04_uc_faktor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import (
    InMemoryCredentialStore, InMemoryOOBChannel, InMemoryPushProvider,
)


CREDS = {
    "tckn": {
        "11111111110": ("test1234", {
            "name": "Emrecan Bayhan",
            "phone": "05321234567",
            "email": "emrecan@example.com",
        }),
    },
}


def make_engine():
    sms = InMemoryOOBChannel()
    push = InMemoryPushProvider()
    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "04_uc_faktor.json",
        providers={
            "credentials": InMemoryCredentialStore(CREDS),
            "sms": sms,
            "push": push,
        },
        logger=LoggerFactory.console(),
    )
    return engine, sms, push


def scenario_1_success():
    print("\n" + "=" * 60)
    print("Senaryo 1: Tüm faktörler doğru → SUCCESS")
    print("=" * 60)

    engine, sms, push = make_engine()

    # Step 1: TCKN+şifre
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "test1234",
    })
    sid = state.context["session_id"]
    print(f"  Step 1: {state.outcome.value} → next: {state.current_step.stages[0].name}")

    # Step 2: SMS OTP - kütüphane kodu ürettiyse al
    sms_code = sms.last_code()
    print(f"  💬 [SMS sent: {sms_code}]")
    state = engine.resume(sid, form_data={"s_1_0_in": sms_code})
    print(f"  Step 2: {state.outcome.value} → next: {state.current_step.stages[0].name}")

    # Step 3: Push - kullanıcı telefonda onaylar
    request_id = list(push._requests.keys())[-1]
    push.approve(request_id)
    print(f"  📲 [User approved push on phone]")
    state = engine.resume(sid, form_data={})
    print(f"  Step 3: {state.outcome.value}")

    if state.is_success:
        print(f"\n  ✅ Tam yetkili giriş: {state.context['identified_user']['name']}")


def scenario_2_wrong_password():
    print("\n" + "=" * 60)
    print("Senaryo 2: Yanlış şifre → FAILED at step 1")
    print("=" * 60)

    engine, _, _ = make_engine()
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "wrongpass",
    })
    print(f"  Step 1: {state.outcome.value}")
    for err in state.errors:
        print(f"  Hata: {err.message}")


def scenario_3_wrong_sms():
    print("\n" + "=" * 60)
    print("Senaryo 3: Yanlış SMS → FAILED at step 2")
    print("=" * 60)

    engine, sms, _ = make_engine()
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "test1234",
    })
    sid = state.context["session_id"]
    state = engine.resume(sid, form_data={"s_1_0_in": "000000"})  # wrong
    print(f"  Step 2 (wrong code): {state.outcome.value}")
    for err in state.errors:
        print(f"  Hata: {err.message}")
    print(f"  Kalan deneme: {state.attempts_remaining}")


def scenario_4_push_rejected():
    print("\n" + "=" * 60)
    print("Senaryo 4: Push reddedildi → FAILED at step 3")
    print("=" * 60)

    engine, sms, push = make_engine()

    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "test1234",
    })
    sid = state.context["session_id"]
    sms_code = sms.last_code()
    state = engine.resume(sid, form_data={"s_1_0_in": sms_code})

    # Step 3: User REJECTS the push
    request_id = list(push._requests.keys())[-1]
    push.reject(request_id)
    print(f"  📲 [User REJECTED push on phone]")
    state = engine.resume(sid, form_data={})
    print(f"  Step 3: {state.outcome.value}")
    for err in state.errors:
        print(f"  Hata: {err.message}")


def main():
    scenario_1_success()
    scenario_2_wrong_password()
    scenario_3_wrong_sms()
    scenario_4_push_rejected()
    print("\n" + "=" * 60)
    print("Tüm senaryolar bitti.")
    print("=" * 60)


if __name__ == "__main__":
    main()
