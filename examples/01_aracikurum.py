"""
Example 1: Klasik Aracı Kurum akışı
====================================
    MERSIS Sorgu  →  Listeden Seç  →  SMS OTP

This example shows:
  - Loading a policy from a JSON file
  - Wiring up in-memory providers
  - Running the engine with form_data step by step
  - Inspecting AuthState at each step
  - Logging events to the console

Run it:  python examples/01_aracikurum.py
"""
import sys
from pathlib import Path

# Add project root to import path (so the example runs without `pip install`)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mkk_auth import AuthEngine, LoggerFactory
from mkk_auth.providers.memory import (
    InMemoryLookupProvider, InMemoryOOBChannel,
)


# ---------- Mock data (in production: comes from MERSIS API) ----------
MERSIS_DATA = {
    "0123456789012345": {
        "company_name": "Acme Aracı Kurum A.Ş.",
        "representatives": [
            {
                "tckn": "11111111110",
                "sicil": "001234",
                "name": "Emrecan Bayhan",
                "phone": "05321234567",
                "email": "emrecan@acme.com.tr",
            },
            {
                "tckn": "22222222220",
                "sicil": "005678",
                "name": "Ali Yılmaz",
                "phone": "05332345678",
                "email": "ali@acme.com.tr",
            },
        ],
    },
    "9876543210987654": {
        "company_name": "Beta Holding A.Ş.",
        "representatives": [
            {
                "tckn": "33333333330",
                "sicil": "009999",
                "name": "Veli Demir",
                "phone": "05551234567",
                "email": "veli@beta.com.tr",
            }
        ],
    },
}


def main():
    # Wire up the engine
    sms_channel = InMemoryOOBChannel(
        sink=lambda phone, code, opts: print(f"\n  📱 [SMS] {phone}: kod={code}\n")
    )
    logger = LoggerFactory.console(verbose=False)

    engine = AuthEngine.from_policy(
        Path(__file__).parent.parent / "policies" / "01_aracikurum.json",
        providers={
            "lookup": InMemoryLookupProvider(MERSIS_DATA),
            "sms": sms_channel,
        },
        logger=logger,
    )

    print("\n" + "=" * 60)
    print("STEP 1: User enters MERSIS number")
    print("=" * 60)
    state = engine.start(form_data={
        "s_0_0_in": "0123456789012345",
    })
    print_state(state)

    print("\n" + "=" * 60)
    print("STEP 2: User picks a representative")
    print("=" * 60)
    state = engine.advance_with_session(state, form_data={
        "s_1_0_selected": "11111111110",   # Emrecan Bayhan
    })
    print_state(state)

    print("\n" + "=" * 60)
    print("STEP 3: User submits the SMS OTP code")
    print("=" * 60)
    # Pull the code that was "sent" via SMS
    sent_code = sms_channel.last_code()
    state = engine.advance_with_session(state, form_data={
        "s_2_0_in": sent_code,
    })
    print_state(state)


def print_state(state):
    print(f"  outcome:           {state.outcome.value}")
    if state.current_step:
        stages = ", ".join(s.name for s in state.current_step.stages)
        print(f"  current step:      #{state.current_step.step_number} ({stages})")
    if state.context.get("identified_user"):
        u = state.context["identified_user"]
        print(f"  identified user:   {u.get('name', '?')} ({u.get('tckn', u.get('identifier', '?'))})")
    if state.errors:
        for err in state.errors:
            print(f"  error:             {err.message}")
    if state.attempts_remaining:
        for stage_type, n in state.attempts_remaining.items():
            print(f"  attempts left:     {stage_type}={n}")


# Helper that uses the session_store (matches the resume() pattern)
def _advance_with_session(self, state, form_data):
    sid = state.context["session_id"]
    return self.resume(sid, form_data=form_data)

AuthEngine.advance_with_session = _advance_with_session


if __name__ == "__main__":
    main()
