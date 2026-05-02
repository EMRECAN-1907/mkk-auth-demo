"""
Example 5: Rate Limiter & Lockout
==================================

Bu örnek **rate limiter**'ın nasıl çalıştığını gösterir:
  - Aynı kullanıcı 5 kez yanlış şifre girerse 60 saniye kilitlenir
  - Stage'in maxRetries'ı session bazlı, rate_limiter ise account bazlı

Run:  python examples/05_lockout.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory, AuthOutcome
from mkk_auth.providers.memory import (
    InMemoryCredentialStore, InMemoryRateLimiter,
)


CREDS = {
    "tckn": {
        "11111111110": ("dogrusifre", {"name": "Test Kullanıcı"}),
    },
}


def main():
    # Rate limiter: 5 başarısız → 60s kilitle
    rate_limiter = InMemoryRateLimiter(
        window_seconds=300,    # 5 dakikada
        max_failures=5,        # 5 başarısız deneme
        lockout_seconds=60,    # 60 saniye kilitle
    )

    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "03_userpass_tckn.json",
        providers={"credentials": InMemoryCredentialStore(CREDS)},
        logger=LoggerFactory.console(),
        rate_limiter=rate_limiter,
    )

    print("\n" + "=" * 60)
    print("Senaryo: Aynı TCKN ile 6 kez yanlış şifre")
    print("=" * 60)
    print("Beklenti: 5. denemeden sonra rate_limiter kilitler")
    print()

    for attempt in range(1, 7):
        state = engine.start(form_data={
            "s_0_0_u": "11111111110",
            "s_0_0_p": f"yanlis{attempt}",  # her seferinde yanlış
        })

        if state.outcome == AuthOutcome.LOCKED:
            print(f"\n  Deneme {attempt}: 🔒 LOCKED — "
                  f"{state.locked_until_seconds}s sonra dene")
            print(f"    Sebep: {state.errors[0].message}")
            break
        else:
            print(f"  Deneme {attempt}: {state.outcome.value}")

    # Şimdi doğru şifre girsek de hala kilitli
    print("\n" + "=" * 60)
    print("Şimdi doğru şifreyle deneyelim — hala kilitli olmalı")
    print("=" * 60)
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "dogrusifre",
    })
    print(f"  Sonuç: {state.outcome.value}")
    if state.outcome == AuthOutcome.LOCKED:
        print(f"  ✓ Beklendiği gibi kilitli, {state.locked_until_seconds}s daha bekle")
    elif state.is_success:
        print(f"  ⚠ Beklenmedik sonuç: kullanıcı kilitliyken giriş yapamamalıydı")


if __name__ == "__main__":
    main()
