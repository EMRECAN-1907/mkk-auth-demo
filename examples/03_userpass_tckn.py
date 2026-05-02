"""
Example 3: TCKN + Şifre Tek Adımlık Giriş
==========================================
    TCKN + Şifre  (tek adım)

Bu kütüphane'nin **en basit kullanım şekli**: tek bir adım, kullanıcı
TCKN ve şifresini girer, biter.

Run:  python examples/03_userpass_tckn.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import InMemoryCredentialStore


# Mock credential database - identifier_type → {identifier: (password, attrs)}
CREDS = {
    "tckn": {
        "11111111110": ("tckn1234", {
            "name": "Emrecan Bayhan",
            "phone": "05321234567",
            "email": "emrecan@example.com",
        }),
        "22222222220": ("tckn5678", {"name": "Ali Yılmaz"}),
    },
}


def main():
    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "03_userpass_tckn.json",
        providers={
            "credentials": InMemoryCredentialStore(CREDS),
        },
        logger=LoggerFactory.console(),
    )

    print("\n=== TCKN + Şifre Girişi ===\n")

    # Senaryo: Doğru bilgilerle giriş
    print("Senaryo 1: Doğru TCKN+şifre")
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "tckn1234",
    })
    print(f"  Sonuç: {state.outcome.value}")
    if state.is_success:
        print(f"  Kullanıcı: {state.context['identified_user']['name']}")

    # Senaryo: Yanlış şifre
    print("\nSenaryo 2: Yanlış şifre")
    state = engine.start(form_data={
        "s_0_0_u": "11111111110",
        "s_0_0_p": "yanlis_sifre",
    })
    print(f"  Sonuç: {state.outcome.value}")
    for err in state.errors:
        print(f"  Hata: {err.message}")
    print(f"  Kalan deneme: {state.attempts_remaining}")


if __name__ == "__main__":
    main()
