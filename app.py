"""
MKK Auth Demo — Flask Web Application
======================================

Çalıştırma:
    python app.py

Sonra tarayıcıda:
    http://localhost:5000              → Builder
    http://localhost:5000/execute      → Test/Login sayfası
    http://localhost:5000/test-users   → Test kullanıcıları listesi

Sayfalar:
- /              → Drag-drop policy builder
- /execute       → Policy çalıştırıcı (login simülasyonu)
- /test-users    → TEST_USERS.md render
- /api/run/start → POST: yeni session başlat
- /api/run/step  → POST: bir adım ilerlet
- /api/logs/<sid>→ SSE stream: canlı log akışı
- /api/policies  → Hazır policy listesi
- /api/policy/<name> → Belirli bir policy'yi getir
"""
from __future__ import annotations
import json
import os
import sys
import uuid
from pathlib import Path

import yaml
from flask import (
    Flask, jsonify, render_template, request, Response,
    send_from_directory, redirect, url_for,
)

# Make sure the mkk_auth package is importable
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from mkk_auth import AuthEngine, AuthOutcome, LoggerFactory, Policy
from mkk_auth.exceptions import AuthError
from mkk_auth.logging import SseLogger, sse_event_stream
from mkk_auth.logging.implementations import CompositeLogger
from mkk_auth.providers.memory import (
    InMemoryLookupProvider, InMemoryOOBChannel, InMemoryCredentialStore,
    InMemoryLdapProvider, InMemoryRateLimiter, InMemoryPushProvider,
    InMemoryExternalIdp, InMemoryESignProvider, InMemoryMobileSignProvider,
)


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False  # Türkçe karakterler için


# =====================================================================
# Test data — yüklenip provider'lara enjekte edilir
# =====================================================================

def load_test_credentials() -> dict:
    """test_credentials.yaml'i yükle."""
    path = HERE / "test_credentials.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_lookup_data(creds: dict) -> dict:
    """Tüm lookup verilerini birleştir, tek bir dict yap."""
    data = {}

    # MERSIS
    for m in creds.get("mersis", []):
        data[m["mersis"]] = {
            "company_name": m["company_name"],
            "representatives": m["representatives"],
        }

    # TCKN
    for u in creds.get("tckn", []):
        data[u["tckn"]] = {
            "tckn": u["tckn"],
            "name": u["name"],
            "phone": u.get("phone"),
            "email": u.get("email"),
        }

    # Sicil
    for u in creds.get("sicil", []):
        data[u["sicil"]] = {
            "sicil": u["sicil"],
            "name": u["name"],
            "phone": u.get("phone"),
            "email": u.get("email"),
        }

    # Passport
    for u in creds.get("passport", []):
        data[u["passport"]] = {
            "passport": u["passport"],
            "name": u["name"],
            "country": u.get("country"),
            "phone": u.get("phone"),
            "email": u.get("email"),
        }

    return data


def build_credential_store_data(creds: dict) -> dict:
    """Tüm parolaları identifier_type'a göre grupla."""
    data = {
        "username": {},
        "tckn": {},
        "vkn": {},
        "sicil": {},
        "passport": {},
        "mersis": {},
        "email": {},
        "generic": {},
    }
    for u in creds.get("usernames", []):
        data["username"][u["username"]] = (u["password"], {
            "name": u.get("name"), "phone": u.get("phone"),
            "email": u.get("email"), "role": u.get("role"),
        })
    for u in creds.get("tckn", []):
        data["tckn"][u["tckn"]] = (u["password"], {
            "name": u.get("name"), "phone": u.get("phone"),
            "email": u.get("email"),
        })
    for u in creds.get("vkn", []):
        data["vkn"][u["vkn"]] = (u["password"], {
            "company": u.get("company"),
            "phone": u.get("phone"), "email": u.get("email"),
        })
    for u in creds.get("sicil", []):
        data["sicil"][u["sicil"]] = (u["password"], {
            "name": u.get("name"), "department": u.get("department"),
            "phone": u.get("phone"), "email": u.get("email"),
        })
    for u in creds.get("passport", []):
        data["passport"][u["passport"]] = (u["password"], {
            "name": u.get("name"), "country": u.get("country"),
            "phone": u.get("phone"), "email": u.get("email"),
        })
    return data


def build_ldap_data(creds: dict) -> dict:
    data = {}
    for u in creds.get("ldap", []):
        data[u["username"]] = (u["password"], {
            "cn": u.get("cn"), "dn": u.get("dn"),
            "memberOf": u.get("memberOf", []),
        })
    return data


# Load credentials once at startup
TEST_CREDS = load_test_credentials()


# =====================================================================
# Logger setup
# =====================================================================

# One global SseLogger for all sessions; events are routed by session_id
sse_logger = SseLogger()

# Composite: console (for terminal output) + SSE (for the web UI)
console_logger = LoggerFactory.console(verbose=False)
APP_LOGGER = CompositeLogger([console_logger, sse_logger])


# =====================================================================
# Build providers (shared across all sessions)
# =====================================================================

def build_providers() -> dict:
    """Construct in-memory providers using test credentials."""
    # SMS sink: emit a special log event that the UI can highlight
    def sms_sink(phone, code, opts):
        from mkk_auth.logging.logger import LogEvent, LogLevel
        APP_LOGGER.log(LogEvent(
            event_type="oob.sms.demo",
            message=f"📱 SMS → {phone}: {code}",
            level=LogLevel.INFO,
            attributes={"phone": phone, "code": code, "channel": "sms"},
        ))

    def email_sink(addr, code, opts):
        from mkk_auth.logging.logger import LogEvent, LogLevel
        APP_LOGGER.log(LogEvent(
            event_type="oob.email.demo",
            message=f"✉ EMAIL → {addr}: {code}",
            level=LogLevel.INFO,
            attributes={"email": addr, "code": code, "channel": "email"},
        ))

    edevlet_cfg = TEST_CREDS.get("external_idp", {}).get("edevlet", {})
    gib_cfg = TEST_CREDS.get("external_idp", {}).get("gib", {})
    esign_cfg = TEST_CREDS.get("esign", {})
    mobile_sign_cfg = TEST_CREDS.get("mobile_sign", {})

    providers = {
        "lookup": InMemoryLookupProvider(build_lookup_data(TEST_CREDS)),
        "credentials": InMemoryCredentialStore(build_credential_store_data(TEST_CREDS)),
        "ldap": InMemoryLdapProvider(build_ldap_data(TEST_CREDS)),
        "sms": InMemoryOOBChannel(sink=sms_sink),
        "email": InMemoryOOBChannel(sink=email_sink),
        "push": InMemoryPushProvider(),
        "idp_edevlet": InMemoryExternalIdp(
            base_url=edevlet_cfg.get("base_url", "https://giris.turkiye.gov.tr/oauth"),
            fake_user=edevlet_cfg.get("fake_user", {"name": "e-Devlet User"}),
        ),
        "idp_gib": InMemoryExternalIdp(
            base_url=gib_cfg.get("base_url", "https://gib.gov.tr/oauth"),
            fake_user=gib_cfg.get("fake_user", {"name": "GIB User"}),
        ),
        "idp": InMemoryExternalIdp(  # generic fallback
            base_url="https://example.com/oauth",
            fake_user={"name": "Demo User", "verified_via": "external"},
        ),
        "esign": InMemoryESignProvider(
            fake_subject=esign_cfg.get("fake_subject", {"name": "Demo"})
        ),
        "mobile_sign": InMemoryMobileSignProvider(
            fake_user_attrs=mobile_sign_cfg.get("fake_user", {"name": "Demo"})
        ),
    }
    return providers


# Build providers once and share
APP_PROVIDERS = build_providers()
RATE_LIMITER = InMemoryRateLimiter(
    window_seconds=300, max_failures=5, lockout_seconds=60
)


# =====================================================================
# Engine cache — one engine per policy_hash
# =====================================================================

_engine_cache: dict[str, AuthEngine] = {}


def get_or_build_engine(policy_dict: dict) -> AuthEngine:
    """Cache engines by policy content hash so we don't rebuild per request."""
    key = json.dumps(policy_dict, sort_keys=True)
    if key in _engine_cache:
        return _engine_cache[key]

    policy = Policy.from_dict(policy_dict)
    engine = AuthEngine(
        policy=policy,
        providers=APP_PROVIDERS,
        logger=APP_LOGGER,
        rate_limiter=RATE_LIMITER,
    )
    _engine_cache[key] = engine
    return engine


# =====================================================================
# Routes — Pages
# =====================================================================

@app.route("/")
def builder_page():
    """Drag-drop builder."""
    return render_template("builder.html")


@app.route("/execute")
def execute_page():
    """Policy çalıştırıcı / test sayfası."""
    return render_template("execute.html")


@app.route("/dashboard")
def dashboard_page():
    """e-Yatırımcı dashboard simülasyonu (login sonrası)."""
    return render_template("dashboard.html")


@app.route("/test-users")
def test_users_page():
    """Test kullanıcıları (TEST_USERS.md render)."""
    md_path = HERE / "TEST_USERS.md"
    md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return render_template("test_users.html", md_text=md_text)


# =====================================================================
# Routes — API
# =====================================================================

@app.route("/api/policies")
def list_policies():
    """List built-in policy JSONs."""
    policies_dir = HERE / "policies"
    items = []
    if policies_dir.exists():
        for f in sorted(policies_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                items.append({
                    "filename": f.name,
                    "policyName": data.get("policyName", f.stem),
                    "displayName": data.get("displayName", f.stem),
                    "appLabel": data.get("appLabel", ""),
                    "description": data.get("description", ""),
                    "stepCount": len(data.get("stages", [])),
                })
            except Exception:
                pass
    return jsonify(items)


@app.route("/api/policy/<filename>")
def get_policy(filename):
    """Return one policy JSON."""
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    path = HERE / "policies" / safe
    if not path.exists() or not path.is_file():
        return jsonify({"error": "not found"}), 404
    return Response(path.read_text(encoding="utf-8"), mimetype="application/json")


@app.route("/api/test-credentials")
def get_test_credentials():
    """Expose test credentials for the execute page sidebar."""
    return jsonify(TEST_CREDS)


@app.route("/api/run/start", methods=["POST"])
def run_start():
    """
    Start a new auth run.
    Body: { "policy": {...JSON...}, "form_data": {...} }
    Returns: { "session_id": "...", "state": {...} }
    """
    data = request.get_json(force=True)
    policy_dict = data.get("policy")
    form_data = data.get("form_data", {})

    if not policy_dict:
        return jsonify({"error": "policy required"}), 400

    try:
        engine = get_or_build_engine(policy_dict)
    except Exception as e:
        return jsonify({"error": f"Engine build failed: {e}"}), 400

    try:
        state = engine.start(
            form_data=form_data,
            request_metadata={
                "ip": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", ""),
            },
        )
    except AuthError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "session_id": state.context.get("session_id"),
        "state": _serialize_state(state),
    })


@app.route("/api/run/step", methods=["POST"])
def run_step():
    """
    Advance an existing session.
    Body: { "policy": {...}, "session_id": "...", "form_data": {...} }
    """
    data = request.get_json(force=True)
    policy_dict = data.get("policy")
    sid = data.get("session_id")
    form_data = data.get("form_data", {})

    if not policy_dict or not sid:
        return jsonify({"error": "policy and session_id required"}), 400

    engine = get_or_build_engine(policy_dict)
    try:
        state = engine.resume(sid, form_data=form_data)
    except AuthError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "session_id": sid,
        "state": _serialize_state(state),
    })


@app.route("/api/logs/<session_id>")
def stream_logs(session_id):
    """SSE log stream for a specific session."""
    return Response(
        sse_event_stream(sse_logger, session_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@app.route("/api/logs/global")
def stream_logs_global():
    """SSE stream of ALL events (admin view)."""
    return Response(
        sse_event_stream(sse_logger, None),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/push/respond", methods=["POST"])
def push_respond():
    """
    Demo: simulate user tapping the push notification.
    Body: { "request_id": "...", "response": "approved"|"rejected" }
    """
    data = request.get_json(force=True)
    req_id = data.get("request_id")
    response = data.get("response", "approved")
    push = APP_PROVIDERS.get("push")
    if not push or not req_id:
        return jsonify({"error": "missing data"}), 400
    if response == "approved":
        push.approve(req_id)
    else:
        push.reject(req_id)
    return jsonify({"ok": True})


@app.route("/api/captcha-code/<session_id>")
def get_captcha_code(session_id):
    """
    Demo helper — returns the captcha code that was generated.
    In production this never exists; we'd render the image instead.
    Used by the UI to display the captcha as text.
    """
    import pickle
    # Find the engine that owns this session
    for engine in _engine_cache.values():
        raw = engine.session_store.load(session_id)
        if raw:
            ctx = pickle.loads(raw)
            codes = getattr(ctx, "_captcha_codes", {})
            return jsonify({"codes": codes})
    return jsonify({"codes": {}})


@app.route("/api/oob-codes/<session_id>")
def get_oob_codes(session_id):
    """
    Demo helper — returns the active OOB codes (SMS/email) for the
    current session, so the "✨ Doldur" button can pull them on-demand
    rather than relying on a stale SSE-cached value.
    """
    import pickle
    for engine in _engine_cache.values():
        raw = engine.session_store.load(session_id)
        if raw:
            ctx = pickle.loads(raw)
            otp_codes = getattr(ctx, "_otp_codes", {}) or {}
            policy = engine.policy
            latest_sms = None
            latest_email = None

            # Walk main steps
            for step_idx, step in enumerate(policy.steps):
                for col_idx, item in enumerate(step.items):
                    key = f"{step_idx}_{col_idx}"
                    if key in otp_codes:
                        if item.type == "sms_oob":
                            latest_sms = otp_codes[key]
                        elif item.type == "email_oob":
                            latest_email = otp_codes[key]

            # Walk sub-steps if any. Engine uses step_idx = 100 + injected_step_index
            # for sub-flow stages.
            for step_idx, step in enumerate(policy.steps):
                for col_idx, item in enumerate(step.items):
                    if item.sub_steps:
                        for sub_idx, sub_step in enumerate(item.sub_steps):
                            virtual_step_idx = 100 + sub_idx
                            for sub_col_idx, sub_item in enumerate(sub_step.items):
                                key = f"{virtual_step_idx}_{sub_col_idx}"
                                if key in otp_codes:
                                    if sub_item.type == "sms_oob":
                                        latest_sms = otp_codes[key]
                                    elif sub_item.type == "email_oob":
                                        latest_email = otp_codes[key]

            return jsonify({"sms": latest_sms, "email": latest_email})
    return jsonify({"sms": None, "email": None})


# =====================================================================
# Helpers
# =====================================================================

def _serialize_state(state) -> dict:
    """Serialize an AuthState for JSON response."""
    cs = state.current_step
    return {
        "outcome": state.outcome.value,
        "is_pending": state.outcome == AuthOutcome.PENDING_INPUT,
        "is_success": state.outcome == AuthOutcome.SUCCESS,
        "is_terminal": state.is_terminal,
        "context": state.context,
        "errors": [
            {"message": e.message, "field": e.field, "status": e.status.value}
            for e in state.errors
        ],
        "attempts_remaining": state.attempts_remaining,
        "locked_until_seconds": state.locked_until_seconds,
        "timer_deadline_unix": state.timer_deadline_unix,
        "current_step": {
            "step_number": cs.step_number,
            "parallel": cs.parallel,
            "timing_mode": cs.timing_mode,
            "shared_timeout": cs.shared_timeout,
            "semantics": cs.semantics,
            "stages": [
                {
                    "type": s.type,
                    "category": s.category,
                    "name": s.name,
                    "config": s.config,
                }
                for s in cs.stages
            ],
        } if cs else None,
    }


# =====================================================================
# Main
# =====================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MKK Auth Demo — Flask Starting")
    print("=" * 60)
    print(f"  Builder:     http://localhost:5000/")
    print(f"  Execute:     http://localhost:5000/execute")
    print(f"  Test Users:  http://localhost:5000/test-users")
    print("=" * 60)
    # threaded=True is REQUIRED for SSE to work alongside other requests
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
