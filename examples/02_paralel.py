"""
Example 2: Paralel SMS + Email
==============================
    TCKN Sorgu  →  [SMS OTP | Email OTP]  (paralel, ikisi de gerekli)

This example shows:
  - Parallel stages in one step
  - Multiple OOB providers
  - User submitting input for both stages in one form

Run it:  python examples/02_paralel.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import (
    InMemoryLookupProvider, InMemoryOOBChannel,
)


INDIVIDUAL_DATA = {
    "11111111110": {
        "tckn": "11111111110",
        "name": "Test Bireysel Yatırımcı",
        "phone": "05321234567",
        "email": "test@example.com",
    },
}


def main():
    sms_channel = InMemoryOOBChannel(
        sink=lambda phone, code, opts: print(f"\n  📱 [SMS]   {phone}: {code}")
    )
    email_channel = InMemoryOOBChannel(
        sink=lambda email, code, opts: print(f"  ✉  [EMAIL] {email}: {code}\n")
    )

    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "02_paralel.json",
        providers={
            "lookup": InMemoryLookupProvider(INDIVIDUAL_DATA),
            "sms": sms_channel,
            "email": email_channel,
        },
        logger=LoggerFactory.console(),
    )

    print("\n=== STEP 1: TCKN Sorgu ===")
    state = engine.start(form_data={"s_0_0_in": "11111111110"})
    print(f"  outcome: {state.outcome.value}")

    print("\n=== STEP 2: SMS + Email codes are sent in parallel ===")
    print("(Both channels print their codes above; user reads both and enters them)")

    sms_code = sms_channel.last_code()
    email_code = email_channel.last_code()
    state = AuthEngine.advance_with_session(engine, state, form_data={
        "s_1_0_in": sms_code,    # SMS OTP
        "s_1_1_in": email_code,  # Email OTP
    })

    if state.is_success:
        print(f"\n✓ Login complete: {state.context['identified_user']['name']}")
    else:
        print(f"\nState: {state.outcome.value}")
        for err in state.errors:
            print(f"  error: {err.message}")


def _advance_with_session(self, state, form_data):
    return self.resume(state.context["session_id"], form_data=form_data)
AuthEngine.advance_with_session = _advance_with_session


if __name__ == "__main__":
    main()
