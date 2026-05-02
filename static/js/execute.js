/* =====================================================================
   MKK Auth — Execute Page JS (e-YATIRIMCI styled)
   ===================================================================== */

const $ = (id) => document.getElementById(id);
const state = {
  policy: null,
  sessionId: null,
  currentState: null,
  eventSource: null,
  testCreds: null,
  timerInterval: null,
};

// ---------- Init ----------
window.addEventListener("DOMContentLoaded", async () => {
  await loadTestCredentials();
  await loadPolicyList();
  loadPendingFromBuilder();

  $("policy-select").addEventListener("change", onPolicySelectChange);
  $("policy-upload").addEventListener("change", onPolicyUpload);
  $("show-json-btn").addEventListener("click", showJsonModal);
  $("json-close").addEventListener("click", () => $("json-modal").style.display = "none");
  $("reload-pending-btn").addEventListener("click", loadPendingFromBuilder);
  $("reset-btn").addEventListener("click", resetSession);
  $("clear-logs").addEventListener("click", clearLogs);
  $("toggle-test-users").addEventListener("click", toggleTestUsers);
  $("close-test-users").addEventListener("click", toggleTestUsers);
  $("toggle-logs").addEventListener("click", toggleLogs);
  $("toggle-flow").addEventListener("click", toggleFlow);
  $("download-flow-png").addEventListener("click", () => downloadAsPng("cards"));
  $("download-diagram-png").addEventListener("click", () => downloadAsPng("diagram"));
});

// ---------- Test creds ----------
async function loadTestCredentials() {
  const r = await fetch("/api/test-credentials");
  state.testCreds = await r.json();
  renderTestUsers();
}

function renderTestUsers() {
  const c = state.testCreds || {};
  const out = [];

  if (c.usernames?.length) {
    out.push(`<div class="test-user-group"><h3>Username</h3>`);
    c.usernames.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">user:</span><span class="value">${u.username}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }
  if (c.tckn?.length) {
    out.push(`<div class="test-user-group"><h3>TCKN</h3>`);
    c.tckn.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">tc:</span><span class="value">${u.tckn}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }
  if (c.vkn?.length) {
    out.push(`<div class="test-user-group"><h3>VKN</h3>`);
    c.vkn.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">vkn:</span><span class="value">${u.vkn}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }
  if (c.sicil?.length) {
    out.push(`<div class="test-user-group"><h3>Sicil</h3>`);
    c.sicil.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">sicil:</span><span class="value">${u.sicil}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }
  if (c.passport?.length) {
    out.push(`<div class="test-user-group"><h3>Passport</h3>`);
    c.passport.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">no:</span><span class="value">${u.passport}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }
  if (c.mersis?.length) {
    out.push(`<div class="test-user-group"><h3>MERSIS</h3>`);
    c.mersis.forEach(m => out.push(`
      <div class="test-user-row">
        <span class="label">no:</span><span class="value">${m.mersis}</span>
        <div style="font-size:10px;color:#999;margin-top:2px;">${m.company_name}</div>
      </div>`));
    out.push(`</div>`);
  }
  if (c.ldap?.length) {
    out.push(`<div class="test-user-group"><h3>LDAP</h3>`);
    c.ldap.forEach(u => out.push(`
      <div class="test-user-row">
        <span class="label">user:</span><span class="value">${u.username}</span>
        <span class="label" style="margin-left:8px;">pwd:</span><span class="value">${u.password}</span>
      </div>`));
    out.push(`</div>`);
  }

  out.push(`<div class="test-user-group">
    <h3>Hızlı İpuçları</h3>
    <div style="font-size:11px; color:#666; line-height:1.7;">
      • <strong>SMS/Email:</strong> Kod log panelinde gözükür<br>
      • <strong>TOTP:</strong> Herhangi 6 hane (000000 hariç)<br>
      • <strong>Captcha:</strong> Herhangi değer<br>
      • <strong>e-İmza PIN:</strong> Herhangi 4+ hane (0000 hariç)
    </div>
  </div>`);

  $("test-users-list").innerHTML = out.join("");
}

// ---------- Policy list ----------
async function loadPolicyList() {
  const r = await fetch("/api/policies");
  const list = await r.json();
  const sel = $("policy-select");
  list.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.filename;
    opt.textContent = `${p.displayName} (${p.stepCount} adım)`;
    sel.appendChild(opt);
  });
}

async function onPolicySelectChange(e) {
  const fn = e.target.value;
  if (!fn) return;
  const r = await fetch(`/api/policy/${fn}`);
  const policy = await r.json();
  loadPolicy(policy);
}

function onPolicyUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      loadPolicy(JSON.parse(ev.target.result));
    } catch (err) {
      alert("Geçersiz JSON: " + err.message);
    }
  };
  reader.readAsText(file);
}

function loadPendingFromBuilder() {
  try {
    const raw = localStorage.getItem("mkk_auth_pending_policy");
    if (raw) {
      loadPolicy(JSON.parse(raw));
      $("log-status").textContent = "✓ Builder'dan yüklendi";
    }
  } catch (e) { console.warn(e); }
}

function loadPolicy(policy) {
  state.policy = policy;
  state.sessionId = null;
  state.currentState = null;
  $("policy-title").textContent = policy.displayName || policy.policyName;
  $("policy-subtitle").textContent = `${policy.appLabel || ""} · ${policy.stages?.length || 0} adım`;
  // Show flow visualizer
  $("flow-visualizer").style.display = "block";
  renderFlowSvg(policy, 0);  // currentStep = 0 initially
  startSession();
}

// ---------- Start session ----------
async function startSession() {
  if (!state.policy) return;
  stopTimer();

  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }

  try {
    const r = await fetch("/api/run/start", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({policy: state.policy, form_data: {}}),
    });
    const data = await r.json();
    if (data.error) { renderError(data.error); return; }
    state.sessionId = data.session_id;
    state.currentState = data.state;
    connectSse(state.sessionId);
    renderState(data.state);
  } catch (e) {
    renderError("Bağlantı hatası: " + e.message);
  }
}

// ---------- SSE ----------
function connectSse(sessionId) {
  const es = new EventSource(`/api/logs/${sessionId}`);
  state.eventSource = es;
  es.onopen = () => $("log-status").textContent = "🟢 Bağlı";
  es.onerror = () => $("log-status").textContent = "🔴 Bağlantı hatası";
  es.onmessage = (msg) => {
    try { appendLog(JSON.parse(msg.data)); }
    catch (e) { console.error("Bad SSE event:", e); }
  };
}

function appendLog(event) {
  const pane = $("logs-pane");
  if (pane.querySelector(".log-empty")) pane.innerHTML = "";

  const line = document.createElement("div");
  line.className = "log-line";
  if (event.event_type?.endsWith(".success") || event.event_type === "session.success") {
    line.classList.add("highlight");
  }
  if (event.event_type?.includes("oob") && event.event_type.endsWith(".demo")) {
    line.classList.add("oob-demo");
    // Also show as toast at top of page!
    showCodeToast(event);
  }

  const ts = (event.timestamp || "").substring(11, 19);
  const meta = [];
  if (event.session_id) meta.push(`sid=${event.session_id.substring(0, 6)}`);
  if (event.stage_type) meta.push(event.stage_type);
  if (event.user_identifier) meta.push(`u=${event.user_identifier}`);

  line.innerHTML = `
    <span class="ts">${ts}</span>
    <span class="lvl-${event.level}">${event.level}</span>
    <span class="evt">${event.event_type}</span>
    <span class="msg">${escapeHtml(event.message)} ${meta.length ? `<span class="meta">[${meta.join(' | ')}]</span>` : ''}</span>
  `;
  pane.appendChild(line);
  if ($("autoscroll").checked) pane.scrollTop = pane.scrollHeight;
}

function showCodeToast(event) {
  // Build a floating, copyable toast at top-right showing the code
  const attrs = event.attributes || {};
  const code = attrs.code;
  const channel = attrs.channel;
  const recipient = attrs.phone || attrs.email || "";
  if (!code) return;

  // Remember last code for autofillCode
  if (channel === "sms") lastCodes.sms = code;
  if (channel === "email") lastCodes.email = code;

  let container = $("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${channel}`;
  toast.innerHTML = `
    <div class="toast-header">
      <span class="toast-icon">${channel === "sms" ? "📱" : "✉"}</span>
      <span class="toast-title">${channel === "sms" ? "SMS" : "Email"} Kodu Geldi</span>
      <button class="toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
    </div>
    <div class="toast-body">
      <div class="toast-recipient">${escapeHtml(recipient)}</div>
      <div class="toast-code" onclick="navigator.clipboard.writeText('${code}'); this.textContent='✓ Kopyalandı'; setTimeout(()=>this.textContent='${code}',1500);" title="Tıkla, kopyala">${code}</div>
      <div class="toast-actions">
        <button class="toast-btn" onclick="autofillCode('${channel}', '${code}')">✨ Forma Doldur</button>
        <span class="toast-hint">veya tıkla kopyala</span>
      </div>
    </div>
  `;
  container.appendChild(toast);

  // Auto-remove after 60 seconds (longer to give time to use)
  setTimeout(() => toast.remove(), 60000);
}

// Find the right SMS/Email input on the page and fill it
function autofillCode(channel, code) {
  const stageType = channel === "sms" ? "sms_oob" : "email_oob";
  // Find any input with name s_*_*_in inside a parallel-stage with right category
  // Simpler: look at the policy to find which step/col is the matching stage
  const policy = state.policy;
  if (!policy) return;
  const cs = state.currentState?.current_step;
  if (!cs) return;
  const stepIdx = cs.step_number - 1;
  cs.stages.forEach((s, colIdx) => {
    if (s.type === stageType) {
      const el = document.querySelector(`[name="s_${stepIdx}_${colIdx}_in"]`);
      if (el) {
        el.value = code;
        el.classList.add("autofilled");
        setTimeout(() => el.classList.remove("autofilled"), 1500);
        showAutofillToast(`${channel.toUpperCase()} kodu dolduruldu`, code);
      }
    }
  });
}

function escapeHtml(s) {
  if (!s) return "";
  return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
}

// Inline captcha widget (used by stages with requireCaptcha=true)
function inlineCaptcha(stepIdx, colIdx) {
  const id = `captcha-inline-${stepIdx}-${colIdx}`;
  return `
    <div class="captcha-recaptcha" style="margin-top:8px;">
      <label class="captcha-recaptcha-label">
        <input type="checkbox" id="${id}-cb"
               onchange="document.getElementById('${id}-h').value = this.checked ? 'verified' : '';">
        <span class="captcha-checkbox-visual"></span>
        <span class="captcha-recaptcha-text">Ben robot değilim</span>
      </label>
      <div class="captcha-recaptcha-logo">
        <div class="recaptcha-icon">🔄</div>
        <div class="recaptcha-brand">reCAPTCHA</div>
        <div class="recaptcha-tos">Gizlilik · Şartlar</div>
      </div>
    </div>
    <input type="hidden" name="s_${stepIdx}_${colIdx}_captcha" id="${id}-h">
  `;
}

function maskPhone(p) {
  if (!p || p.length < 6) return p || "***";
  return p.substring(0, 3) + "*".repeat(p.length - 5) + p.substring(p.length - 2);
}

function maskEmail(e) {
  if (!e || !e.includes("@")) return e || "***";
  const [local, domain] = e.split("@");
  if (local.length <= 2) return e;
  return local[0] + "*".repeat(local.length - 2) + local[local.length - 1] + "@" + domain;
}

// ---------- Render state ----------
function renderState(authState) {
  state.currentState = authState;
  stopTimer();

  // Update flow visualizer with current step highlight (wrapped in try - never block UI)
  try {
    if (state.policy) {
      let activeStep = 0;
      if (authState.current_step) {
        activeStep = authState.current_step.step_number - 1;
      } else if (authState.outcome === "success") {
        activeStep = state.policy.stages.length;
      }
      renderFlowSvg(state.policy, activeStep, authState.outcome);
    }
  } catch (e) {
    console.error("Flow visualizer error:", e);
  }

  $("empty-msg")?.remove();
  const container = $("login-form-container");
  const html = [];

  // Success
  if (authState.outcome === "success") {
    const user = authState.context?.identified_user || {};
    const userName = user.name || user.identifier || "Kullanıcı";
    const userId = user.tckn || user.identifier || user.username || "—";
    
    // Determine which auth methods were used by walking the policy stages
    const authMethods = [];
    (state.policy?.stages || []).forEach(step => {
      (step.items || []).forEach(item => {
        const name = STAGE_DEFS[item.type]?.name || item.type;
        if (!authMethods.includes(name)) authMethods.push(name);
      });
    });
    const authMethod = authMethods.join(" → ");
    const sid = authState.context?.session_id || "—";
    
    const dashUrl = `/dashboard?user=${encodeURIComponent(userName)}&id=${encodeURIComponent(userId)}&auth=${encodeURIComponent(authMethod)}&sid=${encodeURIComponent(sid)}`;
    
    html.push(`
      <h2 class="ey-title">Giriş Başarılı</h2>
      <div class="status-banner success">
        <span class="status-icon">✅</span>
        <div>
          <strong>Hoş geldiniz, ${escapeHtml(userName)}!</strong><br>
          ${user.tckn ? `TCKN: ${user.tckn}` : (user.identifier ? `ID: ${user.identifier}` : "")}
        </div>
      </div>
      <div style="text-align:center;padding:8px 0 16px;font-size:12px;color:#999;">
        <span id="auto-redirect-text">Hesabınıza yönlendiriliyor (<span id="redirect-counter">3</span> saniye)...</span>
      </div>
      <button class="ey-btn ey-btn-edevlet" onclick="window.location.href='${dashUrl}'" style="background: var(--ey-pink);">
        🏛 Hesabıma Git (e-Yatırımcı Sayfası)
      </button>
      <button class="ey-btn ey-btn-primary" onclick="cancelRedirect(); startSession();" style="width:100%;margin-top:8px;background:rgba(0,0,0,0.05);color:#333;">🔄 Tekrar Test Et</button>
    `);
    container.innerHTML = html.join("");
    
    // Auto-redirect to dashboard after 3 seconds
    state.redirectCountdown = 3;
    state.redirectTarget = dashUrl;
    state.redirectInterval = setInterval(() => {
      state.redirectCountdown--;
      const counter = document.getElementById("redirect-counter");
      if (counter) counter.textContent = state.redirectCountdown;
      if (state.redirectCountdown <= 0) {
        clearInterval(state.redirectInterval);
        window.location.href = state.redirectTarget;
      }
    }, 1000);
    return;
  }

  if (authState.outcome === "locked") {
    const sec = authState.locked_until_seconds || 0;
    html.push(`
      <h2 class="ey-title">Hesap Kilitlendi</h2>
      <div class="status-banner locked">
        <span class="status-icon">🔒</span>
        <div>${sec > 0 ? `${sec} saniye sonra tekrar dene` : 'Çok fazla başarısız deneme'}</div>
      </div>
      <button class="ey-btn ey-btn-primary" onclick="startSession()" style="width:100%;">🔄 Yeni Session</button>
    `);
    container.innerHTML = html.join("");
    return;
  }

  if (authState.outcome === "expired") {
    html.push(`
      <h2 class="ey-title">Süre Doldu</h2>
      <div class="status-banner warning">
        <span class="status-icon">⏱</span>
        <div>İşleminiz için ayrılan süre doldu</div>
      </div>
      <button class="ey-btn ey-btn-primary" onclick="startSession()" style="width:100%;">🔄 Tekrar Başlat</button>
    `);
    container.innerHTML = html.join("");
    return;
  }

  // Pending
  const step = authState.current_step;
  if (!step) {
    container.innerHTML = `<div class="ey-empty-state"><p>Beklenmeyen durum: ${authState.outcome}</p></div>`;
    return;
  }

  // Title
  html.push(`<h2 class="ey-title">Giriş Yapınız</h2>`);

  // Errors banner
  if (authState.errors?.length > 0) {
    const errMsgs = authState.errors.map(e => e.message).join("; ");
    html.push(`
      <div class="status-banner error">
        <span class="status-icon">⚠</span>
        <div>${escapeHtml(errMsgs)}</div>
      </div>
    `);
  }

  // Step header
  const totalSteps = state.policy?.stages?.length || 1;
  const isAlt = step.semantics === "any" && step.stages.length > 1;
  html.push(`
    <div class="ey-step-header">
      <span class="ey-step-num">${step.step_number}</span>
      <div style="flex:1;">
        <div class="ey-step-title">Adım ${step.step_number} / ${totalSteps}</div>
        <div class="ey-step-meta">
          ${isAlt ? `🔀 alternatif · ${step.stages.length} seçenek` : (step.parallel ? '⚡ paralel · ' + step.stages.length + ' stage' : '➡ ardışık')}
          ${step.shared_timeout ? ` · ⏱ paylaşılan ${step.shared_timeout}s` : ''}
        </div>
      </div>
    </div>
  `);

  // Big timer bar (only if there's a deadline)
  html.push(`<div class="ey-timer-bar" id="ey-timer-bar" style="display:none;">
    <div class="ey-timer-bar-label">
      <span>⏱ Kalan Süre</span>
      <strong id="ey-timer-text">--:--</strong>
    </div>
    <div class="ey-timer-bar-track"><div class="ey-timer-bar-fill" id="ey-timer-fill"></div></div>
  </div>`);

  // Render stages
  const stagesCount = step.stages.length;
  const isAlternative = step.semantics === "any" && stagesCount > 1;
  // When shared timeout active, per-stage timers are meaningless — hide them
  const isSharedTiming = step.timing_mode === "shared" && step.shared_timeout;

  if (isAlternative) {
    // OR semantics — e-Nabız tarzı: kullanıcı birini seçer
    html.push(`<div class="alternative-row">`);
    html.push(`<div class="alternative-hint">
      🔀 <strong>Alternatif giriş yöntemleri</strong><br>
      <small>Aşağıdakilerden <strong>birini</strong> kullanarak giriş yapın.</small>
    </div>`);
    step.stages.forEach((stage, i) => {
      const stepIdx = step.step_number - 1;
      const t = stage.config?.timeout;
      const stageTimerId = `stage-timer-${i}`;
      const af = needsAutofill(stage.type) ? `<button class="autofill-btn" onclick="autofillStage('${stage.type}', ${stepIdx}, ${i})">✨ Doldur</button>` : '';
      const showStageTimer = t && !isSharedTiming;
      html.push(`<div class="alternative-card cat-${stage.category}">
        <div class="alternative-card-header">
          <span class="alternative-card-title">${stage.name}</span>
          <span class="stage-cat-badge ${stage.category}">${stage.category}</span>
          ${af}
          ${showStageTimer ? `<span class="stage-timer-mini" id="${stageTimerId}" data-deadline="${Date.now()/1000 + t}">⏱ ${formatTime(t)}</span>` : ''}
        </div>
        <div class="alternative-card-body">
          ${renderStageInputs(stage, stepIdx, i, authState)}
          <button class="ey-btn ey-btn-primary alternative-submit" onclick="submitForm()">Bu yöntemle Giriş ➡</button>
        </div>
      </div>`);
      if (i < stagesCount - 1) {
        html.push(`<div class="alternative-divider"><span>VEYA</span></div>`);
      }
    });
    html.push(`</div>`);
  } else if (stagesCount > 1) {
    // AND semantics — paralel: hepsi gerekli
    html.push(`<div class="parallel-row">`);
    step.stages.forEach((stage, i) => {
      const stageTimerId = `stage-timer-${i}`;
      const t = stage.config?.timeout;
      const stepIdx = step.step_number - 1;
      const af = needsAutofill(stage.type) ? `<button class="autofill-btn" onclick="autofillStage('${stage.type}', ${stepIdx}, ${i})" title="Test kullanıcısı bilgisini otomatik doldur">✨ Doldur</button>` : '';
      const showStageTimer = t && !isSharedTiming;
      html.push(`<div class="parallel-stage cat-${stage.category}">
        <div class="parallel-stage-title">
          <span>${stage.name}</span>
          <span class="stage-cat-badge ${stage.category}">${stage.category}</span>
          ${af}
          ${showStageTimer ? `<span class="stage-timer-mini" id="${stageTimerId}" data-deadline="${Date.now()/1000 + t}">⏱ ${formatTime(t)}</span>` : ''}
        </div>
        ${renderStageInputs(stage, stepIdx, i, authState)}
      </div>`);
    });
    html.push(`</div>`);
  } else {
    const stage = step.stages[0];
    const t = stage.config?.timeout;
    const stepIdx = step.step_number - 1;
    const af = needsAutofill(stage.type) ? `<button class="autofill-btn" onclick="autofillStage('${stage.type}', ${stepIdx}, 0)">✨ Doldur</button>` : '';
    const showStageTimer = t && !isSharedTiming;
    html.push(`<div style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:8px;">
      ${af}
      ${showStageTimer ? `<span class="stage-timer-mini" id="stage-timer-0" data-deadline="${Date.now()/1000 + t}">⏱ ${formatTime(t)}</span>` : ''}
    </div>`);
    html.push(renderStageInputs(stage, stepIdx, 0, authState));
  }

  // Submit button (only if there are inputs to submit AND it's not alternative step)
  const hasInputs = step.stages.some(s => stageHasInput(s.type));
  if (hasInputs && !isAlternative) {
    html.push(`
      <div class="ey-row-buttons" style="grid-template-columns: 1fr;">
        <button class="ey-btn ey-btn-primary" onclick="submitForm()">DEVAM ➡</button>
      </div>
    `);
  }

  container.innerHTML = html.join("");

  // Start the BIG step timer (shared_timeout), if any
  if (authState.timer_deadline_unix) {
    startTimer(authState.timer_deadline_unix);
  }
  // Always start per-stage mini timers (each stage has its own countdown)
  startStageMiniTimers();
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
}

function startStageMiniTimers() {
  // Stop previous mini-timer interval if any
  if (state.miniTimerInterval) {
    clearInterval(state.miniTimerInterval);
    state.miniTimerInterval = null;
  }

  const update = () => {
    const els = document.querySelectorAll(".stage-timer-mini");
    if (els.length === 0) {
      // Nothing to update, stop
      clearInterval(state.miniTimerInterval);
      state.miniTimerInterval = null;
      return;
    }
    const now = Date.now() / 1000;
    els.forEach(el => {
      const deadline = parseFloat(el.dataset.deadline);
      const remaining = Math.max(0, deadline - now);
      el.textContent = `⏱ ${formatTime(remaining)}`;
      el.classList.remove("warn", "danger");
      if (remaining < 10) el.classList.add("danger");
      else if (remaining < 30) el.classList.add("warn");
    });
  };

  update();
  state.miniTimerInterval = setInterval(update, 1000);
}

// ---------- Live countdown timer ----------
function startTimer(deadlineUnix) {
  const bar = $("ey-timer-bar");
  const fill = $("ey-timer-fill");
  const text = $("ey-timer-text");
  if (!bar || !fill || !text) return;

  bar.style.display = "block";
  const totalDuration = deadlineUnix - Date.now() / 1000;
  if (totalDuration <= 0) return;

  const update = () => {
    const now = Date.now() / 1000;
    const remaining = Math.max(0, deadlineUnix - now);
    const mins = Math.floor(remaining / 60);
    const secs = Math.floor(remaining % 60);
    text.textContent = `${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;

    const pct = Math.max(0, Math.min(100, (remaining / totalDuration) * 100));
    fill.style.width = `${pct}%`;

    bar.classList.remove("warn", "danger");
    if (remaining < 10) bar.classList.add("danger");
    else if (remaining < 30) bar.classList.add("warn");

    if (remaining <= 0) {
      stopTimer();
      setTimeout(() => submitForm(), 500);
    }
  };

  update();
  state.timerInterval = setInterval(update, 1000);
}

function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
  if (state.miniTimerInterval) {
    clearInterval(state.miniTimerInterval);
    state.miniTimerInterval = null;
  }
}

function stageHasInput(t) {
  return !["push_approve"].includes(t);
}

// ---------- Render stage inputs ----------
function renderStageInputs(stage, stepIdx, colIdx, authState) {
  const t = stage.type;
  const cfg = stage.config || {};
  const fname = (s) => `s_${stepIdx}_${colIdx}_${s}`;
  const html = [];

  switch (t) {
    case "mersis_lookup":
      html.push(textInput(fname("in"), cfg.inputLabel || "MERSIS Numarası", "16 haneli MERSIS no"));
      if (cfg.requirePassword) html.push(passwordInput(fname("p"), cfg.passwordLabel || "Şifre"));
      if (cfg.requireCaptcha) html.push(inlineCaptcha(stepIdx, colIdx));
      break;

    case "tckn_standalone":
      html.push(textInput(fname("in"), cfg.inputLabel || "TC Kimlik No", "11 haneli TC No"));
      if (cfg.requirePassword) html.push(passwordInput(fname("p"), cfg.passwordLabel || "Şifre"));
      if (cfg.requireCaptcha) html.push(inlineCaptcha(stepIdx, colIdx));
      break;

    case "generic_lookup":
      html.push(textInput(fname("in"), cfg.inputLabel || "Değer"));
      if (cfg.requirePassword) html.push(passwordInput(fname("p"), cfg.passwordLabel || "Şifre"));
      if (cfg.requireCaptcha) html.push(inlineCaptcha(stepIdx, colIdx));
      break;

    case "userpass":
      // The hero: e-Yatirimci style
      const idType = cfg.identifierType || "username";
      const placeholder = {
        "username": "Kullanıcı Adı",
        "tckn": "TC Kimlik No",
        "vkn": "Vergi No (10 hane)",
        "sicil": "Sicil No",
        "passport": "Pasaport No",
        "uye_no": "Üye No",
        "yatirimci_no": "Yatırımcı No",
      }[idType] || "Kullanıcı bilgisi";
      html.push(`<div class="field">
        <input type="text" class="field-input" name="${fname("u")}" placeholder="${cfg.inputLabel || placeholder}" autocomplete="off">
      </div>`);
      html.push(`<div class="field">
        <input type="password" class="field-input" name="${fname("p")}" placeholder="${cfg.passwordLabel || 'Şifre'}" autocomplete="off">
      </div>`);
      if (cfg.requireCaptcha) html.push(inlineCaptcha(stepIdx, colIdx));
      html.push(`<div class="ey-help-link">Şifremi Nasıl Oluştururum?</div>`);
      html.push(`<label class="ey-checkbox"><input type="checkbox"> Beni Hatırla</label>`);
      break;

    case "ldap":
      html.push(textInput(fname("u"), cfg.inputLabel || "Kullanıcı adı", "AD/LDAP kullanıcı adı"));
      html.push(passwordInput(fname("p"), cfg.passwordLabel || "Şifre"));
      if (cfg.requireCaptcha) html.push(inlineCaptcha(stepIdx, colIdx));
      break;

    case "field_match":
      html.push(textInput(fname("in"), cfg.inputLabel || "Değer"));
      break;

    case "representative_select":
      const reps = authState.context?.mersis_data?.representatives || [];
      if (reps.length === 0) {
        html.push(`<div class="status-banner warning">Listede temsilci yok</div>`);
      } else {
        html.push(`<label class="field-label">Temsilci seç</label>`);
        reps.forEach((r, i) => {
          html.push(`
            <label style="display:block;padding:12px;border:1px solid #d2d2d7;border-radius:8px;margin:6px 0;cursor:pointer;">
              <input type="radio" name="${fname("selected")}" value="${r.tckn}" ${i === 0 ? 'checked' : ''}>
              <strong>${escapeHtml(r.name)}</strong>
              <span style="color:#999;font-size:11px;margin-left:8px;">TCKN: ${r.tckn}</span>
            </label>
          `);
        });
      }
      break;

    case "captcha":
      html.push(`
        <div class="captcha-recaptcha">
          <label class="captcha-recaptcha-label">
            <input type="checkbox" name="${fname("checkbox_helper")}" id="recaptcha-${stepIdx}-${colIdx}">
            <span class="captcha-checkbox-visual"></span>
            <span class="captcha-recaptcha-text">Ben robot değilim</span>
          </label>
          <div class="captcha-recaptcha-logo">
            <div class="recaptcha-icon">🔄</div>
            <div class="recaptcha-brand">reCAPTCHA</div>
            <div class="recaptcha-tos">Gizlilik · Şartlar</div>
          </div>
        </div>
        <input type="hidden" name="${fname("in")}" id="captcha-hidden-${stepIdx}-${colIdx}">
      `);
      // Wire the checkbox to fill the actual input
      setTimeout(() => {
        const cb = document.getElementById(`recaptcha-${stepIdx}-${colIdx}`);
        const hidden = document.getElementById(`captcha-hidden-${stepIdx}-${colIdx}`);
        if (cb && hidden) {
          cb.addEventListener("change", () => {
            hidden.value = cb.checked ? "verified" : "";
          });
        }
      }, 50);
      break;

    case "image_captcha":
      html.push(`<div id="captcha-display-${stepIdx}-${colIdx}" class="captcha-display">YÜKLENİYOR...</div>`);
      html.push(textInput(fname("in"), "Yukarıdaki kodu gir"));
      setTimeout(() => loadCaptchaDisplay(stepIdx, colIdx), 100);
      break;

    case "sms_oob":
      const hasUserForSms = authState.context?.identified_user?.phone;
      if (!hasUserForSms) {
        html.push(`<div class="parallel-stage-pending-msg">
          ⏳ <strong>Telefon numarası bilinmiyor.</strong><br>
          <small>SMS göndermek için kullanıcı belirlenmeli (örn. listeden seçim, TCKN sorgu).</small>
        </div>`);
      } else {
        html.push(`
          <div style="background: rgba(0, 122, 255, 0.06); padding: 12px; border-radius: 8px; margin-bottom: 12px; font-size: 12px; color: #555;">
            📱 SMS gönderildi → <strong>${maskPhone(hasUserForSms)}</strong><br>
            Kodu <strong>aşağıdaki log panelinden</strong> kopyala.
          </div>
        `);
        html.push(textInput(fname("in"), "SMS Kodu (6 hane)"));
      }
      break;

    case "email_oob":
      const hasUserForEmail = authState.context?.identified_user?.email;
      if (!hasUserForEmail) {
        html.push(`<div class="parallel-stage-pending-msg">
          ⏳ <strong>Email adresi bilinmiyor.</strong><br>
          <small>Email göndermek için kullanıcı belirlenmeli (örn. listeden seçim, TCKN sorgu).</small>
        </div>`);
      } else {
        html.push(`
          <div style="background: rgba(175, 82, 222, 0.06); padding: 12px; border-radius: 8px; margin-bottom: 12px; font-size: 12px; color: #555;">
            ✉ Email gönderildi → <strong>${maskEmail(hasUserForEmail)}</strong><br>
            Kodu <strong>aşağıdaki log panelinden</strong> kopyala.
          </div>
        `);
        html.push(textInput(fname("in"), "Email Kodu (6 hane)"));
      }
      break;

    case "totp":
      html.push(textInput(fname("in"), "TOTP Kodu (6 hane)"));
      html.push(`<div style="font-size:11px;color:#999;margin-top:-12px;margin-bottom:12px;">Demo: 000000 dışında herhangi 6 hane</div>`);
      break;

    case "esign":
      html.push(passwordInput(fname("in"), "e-İmza PIN"));
      html.push(`<div style="font-size:11px;color:#999;margin-top:-12px;margin-bottom:12px;">Demo: 0000 dışında 4+ hane</div>`);
      break;

    case "mobile_authenticator":
      const challenge = authState.context?.pending_data?.challenge || "????";
      html.push(`
        <div style="background: rgba(52, 199, 89, 0.06); padding: 16px; border-radius: 8px; margin-bottom: 12px; text-align:center;">
          📱 Telefonda gözüken numara:<br>
          <strong style="font-size: 24px; color: var(--apple-green);">${challenge}</strong>
        </div>
      `);
      html.push(textInput(fname("in"), "Numarayı gir"));
      break;

    case "mobile_sign":
      html.push(`
        <div style="background: rgba(255, 149, 0, 0.06); padding: 16px; border-radius: 8px; text-align:center;">
          📲 Mobil imza isteği gönderildi.<br>
          <small style="color:#999;">(Demo'da otomatik onaylanır, "Devam" tuşuna bas)</small>
        </div>
      `);
      break;

    case "push_approve":
      const reqId = authState.context?.pending_data?.request_id;
      html.push(`
        <div class="push-card">
          <div class="push-icon">📲</div>
          <div style="font-weight:600;margin: 12px 0;font-size:15px;">Telefonuna push gönderildi</div>
          <div style="font-size:12px;color:#999;">Telefondan onaylaman bekleniyor</div>
          <div class="push-buttons">
            <button class="ey-btn ey-btn-success" onclick="respondPush('${reqId}', 'approved')">✓ Onayla</button>
            <button class="ey-btn ey-btn-danger" onclick="respondPush('${reqId}', 'rejected')">✕ Reddet</button>
          </div>
        </div>
      `);
      break;

    case "external_idp":
      const provider = authState.context?.pending_data?.provider || cfg.provider || "external";
      const redirect = authState.context?.pending_data?.redirect_url || "";
      // SPECIAL: e-Devlet rendered as the iconic red button with Turkish flag style
      if (provider === "edevlet") {
        html.push(`
          <div style="text-align:center;margin:24px 0;">
            <div style="font-size:13px;color:#666;margin-bottom:16px;">
              🌐 <strong>e-Devlet</strong> üzerinden güvenli giriş
            </div>
            <button class="ey-btn-edevlet-real" onclick="simulateIdpCallback('${fname("code")}')">
              <svg viewBox="0 0 60 60" width="32" height="32" style="vertical-align:middle;margin-right:10px;">
                <circle cx="30" cy="30" r="28" fill="white"/>
                <path d="M 22 16 A 16 16 0 1 0 22 44" fill="none" stroke="#E30A17" stroke-width="6"/>
                <path d="M 36 22 L 33 26 L 38 26 L 39 30 L 38 34 L 33 34 L 36 38 L 32 35 L 28 38 L 30 33 L 26 30 L 30 27 L 28 22 L 32 25 Z" fill="#E30A17"/>
              </svg>
              <span>e-Devlet ile Giriş</span>
            </button>
            <details style="margin-top:12px;font-size:11px;color:#999;">
              <summary style="cursor:pointer;">Yönlendirme adresini göster</summary>
              <div style="font-family:monospace;word-break:break-all;margin-top:6px;background:#f5f5f7;padding:8px;border-radius:6px;">${escapeHtml(redirect)}</div>
            </details>
          </div>
        `);
      } else if (provider === "gib") {
        html.push(`
          <div style="text-align:center;margin:24px 0;">
            <div style="font-size:13px;color:#666;margin-bottom:16px;">
              🏛 <strong>GİB</strong> (Gelir İdaresi Başkanlığı) üzerinden giriş
            </div>
            <button class="ey-btn-gib-real" onclick="simulateIdpCallback('${fname("code")}')">
              <span style="font-size:18px;">🏛</span>
              <span>GİB ile Giriş</span>
            </button>
          </div>
        `);
      } else {
        html.push(`
          <div class="idp-redirect-card">
            <div class="idp-icon">🌐</div>
            <strong>${provider}</strong> sayfasına yönlendiriliyor
            <div class="idp-url">${escapeHtml(redirect)}</div>
            <button class="ey-btn ey-btn-primary" onclick="simulateIdpCallback('${fname("code")}')">▶ ${provider}'te giriş yapmış say</button>
          </div>
        `);
      }
      break;

    default:
      html.push(`<div style="color:var(--apple-red);font-size:12px;">Stage tipi tanınmadı: ${t}</div>`);
  }

  return html.join("");
}

function textInput(name, label, placeholder) {
  return `<div class="field">
    <input type="text" class="field-input" name="${name}" placeholder="${escapeHtml(placeholder || label)}" autocomplete="off">
  </div>`;
}

function passwordInput(name, label) {
  return `<div class="field">
    <input type="password" class="field-input" name="${name}" placeholder="${escapeHtml(label)}" autocomplete="off">
  </div>`;
}

async function loadCaptchaDisplay(stepIdx, colIdx) {
  if (!state.sessionId) return;
  try {
    const r = await fetch(`/api/captcha-code/${state.sessionId}`);
    const data = await r.json();
    const code = (data.codes || {})[`${stepIdx}_${colIdx}`];
    if (code) {
      const el = $(`captcha-display-${stepIdx}-${colIdx}`);
      if (el) el.textContent = code.toUpperCase();
    }
  } catch (e) { console.warn(e); }
}

// ---------- Submit ----------
async function submitForm() {
  const inputs = document.querySelectorAll(".field-input, [type=radio]:checked");
  const formData = {};
  inputs.forEach(input => {
    if (input.type === "radio" || input.value !== "") {
      formData[input.name] = input.value;
    }
  });

  try {
    const r = await fetch("/api/run/step", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        policy: state.policy,
        session_id: state.sessionId,
        form_data: formData,
      }),
    });
    const data = await r.json();
    if (data.error) { renderError(data.error); return; }
    renderState(data.state);
  } catch (e) {
    renderError("Bağlantı hatası: " + e.message);
  }
}

async function respondPush(requestId, response) {
  await fetch("/api/push/respond", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({request_id: requestId, response}),
  });
  const r = await fetch("/api/run/step", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({policy: state.policy, session_id: state.sessionId, form_data: {}}),
  });
  renderState((await r.json()).state);
}

async function simulateIdpCallback(fieldName) {
  const formData = {};
  formData[fieldName] = "demo_oauth_code_xyz";
  const r = await fetch("/api/run/step", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({policy: state.policy, session_id: state.sessionId, form_data: formData}),
  });
  renderState((await r.json()).state);
}

function renderError(msg) {
  $("login-form-container").innerHTML = `
    <h2 class="ey-title">Hata</h2>
    <div class="status-banner error">
      <span class="status-icon">⚠</span>
      <div>${escapeHtml(msg)}</div>
    </div>
  `;
}

function showJsonModal() {
  if (!state.policy) { alert("Aktif policy yok"); return; }
  $("json-display").textContent = JSON.stringify(state.policy, null, 2);
  $("json-modal").style.display = "flex";
}

function resetSession() {
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
  stopTimer();
  state.sessionId = null;
  state.currentState = null;
  if (state.policy) startSession();
}

function clearLogs() {
  $("logs-pane").innerHTML = '<div class="log-empty">Loglar temizlendi.</div>';
}

function toggleTestUsers() {
  $("test-users-panel").classList.toggle("open");
}

function toggleLogs() {
  const pane = $("logs-pane");
  const btn = $("toggle-logs");
  pane.classList.toggle("collapsed");
  btn.textContent = pane.classList.contains("collapsed") ? "▲ Göster" : "▼ Gizle";
}

function toggleFlow() {
  const c = $("flow-svg-container");
  const btn = $("toggle-flow");
  c.classList.toggle("collapsed");
  btn.textContent = c.classList.contains("collapsed") ? "▲ Göster" : "▼ Gizle";
}

// =====================================================================
// FLOW VISUALIZATION — render policy as SVG with active step highlight
// =====================================================================

const STAGE_DEFS = {
  mersis_lookup:        {category: "identify", name: "MERSIS Sorgu",         icon: "🏛", desc: "Maliye'den şirket+temsilci"},
  tckn_standalone:      {category: "identify", name: "TCKN Sorgu",           icon: "🆔", desc: "MKK dizininde TCKN ara"},
  generic_lookup:       {category: "identify", name: "Generic Lookup",       icon: "🔎", desc: "Konfigüre edilebilir dış sorgu"},
  field_match:          {category: "verify",   name: "Alan Eşleşme",         icon: "🎯", desc: "Listede alan kontrolü"},
  representative_select:{category: "verify",   name: "Listeden Seç",         icon: "📋", desc: "Temsilci seçimi"},
  captcha:              {category: "verify",   name: "Captcha",              icon: "🤖", desc: "Bot kontrolü"},
  image_captcha:        {category: "verify",   name: "Resim Captcha",        icon: "🖼", desc: "Resimden kod oku"},
  sms_oob:              {category: "deliver",  name: "SMS OTP",              icon: "📱", desc: "SMS ile kod gönder"},
  email_oob:            {category: "deliver",  name: "Email OTP",            icon: "✉",  desc: "Email ile kod gönder"},
  userpass:             {category: "auth",     name: "Identifier+Şifre",     icon: "🔐", desc: "Kullanıcı adı ve şifre"},
  ldap:                 {category: "auth",     name: "LDAP Bind",            icon: "🌐", desc: "Active Directory"},
  totp:                 {category: "auth",     name: "TOTP",                 icon: "🔢", desc: "Authenticator kodu"},
  esign:                {category: "auth",     name: "e-İmza",               icon: "✍",  desc: "USB token ile imza"},
  mobile_sign:          {category: "auth",     name: "Mobil İmza",           icon: "📲", desc: "Operatör mobil imza"},
  push_approve:         {category: "auth",     name: "Push Onay",            icon: "🔔", desc: "Telefondan onayla"},
  mobile_authenticator: {category: "auth",     name: "Mobil Authenticator",  icon: "📞", desc: "Tap-the-number"},
  external_idp:         {category: "auth",     name: "Harici IDP",           icon: "🚪", desc: "e-Devlet, GIB, vs"},
};

function renderFlowSvg(policy, activeStepIdx, outcome) {
  const svg = generateFlowSvg(policy, activeStepIdx, outcome);
  $("flow-svg-container").innerHTML = svg;
}

function generateFlowSvg(policy, activeStepIdx, outcome) {
  const colorBg = {
    identify: "#FFF4E5", verify: "#EEEEFB", deliver: "#E8F8EC", auth: "#E5F1FF",
  };
  const colorFg = {
    identify: "#FF9500", verify: "#5856D6", deliver: "#34C759", auth: "#007AFF",
  };
  const catLabel = {
    identify: "TANIMLAMA", verify: "DOĞRULAMA", deliver: "TESLİMAT", auth: "KİMLİK",
  };

  const cardW = 260, cardH = 100, gap = 16, rowGap = 32;
  const padX = 36, padY = 80;
  const stages = policy.stages || [];

  if (stages.length === 0) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="120">
      <text x="200" y="60" font-family="sans-serif" text-anchor="middle" fill="#666">Akış boş</text>
    </svg>`;
  }

  // Calculate dimensions
  let maxRowWidth = cardW;
  stages.forEach(step => {
    const items = step.items || [];
    const w = items.length * cardW + (items.length - 1) * gap;
    if (w > maxRowWidth) maxRowWidth = w;
  });
  const totalW = Math.max(maxRowWidth + padX * 2 + 80, 600);
  const totalH = padY + stages.length * (cardH + rowGap) + 60;

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}">
    <defs>
      <style>
        .title { font-family: -apple-system, 'Segoe UI', sans-serif; font-weight: 700; font-size: 20px; fill: #1c1c1e; }
        .subtitle { font-family: -apple-system, sans-serif; font-size: 12px; fill: rgba(60,60,67,0.6); }
        .stepNum { font-family: -apple-system, sans-serif; font-weight: 600; font-size: 12px; fill: white; text-anchor: middle; }
        .stageName { font-family: -apple-system, sans-serif; font-weight: 600; font-size: 13px; fill: #1c1c1e; }
        .stageDesc { font-family: -apple-system, sans-serif; font-size: 11px; fill: rgba(60,60,67,0.65); }
        .catTag { font-family: -apple-system, sans-serif; font-weight: 600; font-size: 9px; letter-spacing: 0.5px; }
        .badge { font-family: 'SF Mono', Menlo, monospace; font-weight: 600; font-size: 10px; fill: #b56500; }
        .rowLabel { font-family: -apple-system, sans-serif; font-weight: 600; font-size: 10px; fill: rgba(60,60,67,0.55); letter-spacing: 0.5px; }
        .arrow { font-size: 20px; fill: rgba(60,60,67,0.35); }
        .footer { font-family: -apple-system, sans-serif; font-size: 11px; fill: rgba(60,60,67,0.5); }
        .activeBadge { font-family: -apple-system, sans-serif; font-weight: 700; font-size: 10px; fill: white; letter-spacing: 0.5px; }
      </style>
    </defs>
    <rect width="${totalW}" height="${totalH}" fill="white"/>`;

  // Header
  const title = policy.displayName || policy.policyName || "Login Flow";
  svg += `<text x="${padX}" y="32" class="title">${escapeXml(title)}</text>`;
  if (policy.appLabel) svg += `<text x="${padX}" y="52" class="subtitle">${escapeXml(policy.appLabel)}</text>`;

  // Status indicator on top right
  let statusBadge = null;
  if (outcome === "success") statusBadge = {text: "✅ TAMAMLANDI", color: "#34C759"};
  else if (outcome === "locked") statusBadge = {text: "🔒 KİLİTLENDİ", color: "#FF9500"};
  else if (outcome === "expired") statusBadge = {text: "⏱ ZAMAN DOLDU", color: "#FF3B30"};
  else if (outcome === "pending_input") statusBadge = {text: "▶ ÇALIŞIYOR", color: "#007AFF"};
  if (statusBadge) {
    const sw = 130;
    svg += `<rect x="${totalW - padX - sw}" y="20" width="${sw}" height="22" rx="11" fill="${statusBadge.color}" fill-opacity="0.15" stroke="${statusBadge.color}" stroke-opacity="0.4"/>
            <text x="${totalW - padX - sw/2}" y="35" class="activeBadge" fill="${statusBadge.color}" text-anchor="middle">${statusBadge.text}</text>`;
  }

  // Rows
  let y = padY;
  stages.forEach((step, rowIdx) => {
    const items = step.items || [];
    const rowW = items.length * cardW + (items.length - 1) * gap;
    const rowX = (totalW - rowW) / 2;

    const isActive = rowIdx === activeStepIdx && outcome !== "success";
    const isPast = rowIdx < activeStepIdx || (outcome === "success" && rowIdx < stages.length);
    const isFuture = rowIdx > activeStepIdx;

    // Row label
    let rowLabelText = `ADIM ${rowIdx + 1}`;
    if (items.length > 1) {
      rowLabelText += `   ⇆ ${items.length} PARALEL`;
      if (step.timing?.mode === "shared") rowLabelText += `   ⏱ ORTAK ${step.timing.sharedTimeout}s`;
    }
    if (isActive) rowLabelText += "   ◆ AKTİF";
    if (isPast) rowLabelText += "   ✓ TAMAM";
    svg += `<text x="${rowX}" y="${y - 8}" class="rowLabel" fill="${isActive ? '#007AFF' : (isPast ? '#34C759' : 'rgba(60,60,67,0.55)')}">${rowLabelText}</text>`;

    // Step number circle
    const circleColor = isActive ? "#007AFF" : (isPast ? "#34C759" : "#3c3c43");
    svg += `<circle cx="${rowX - 22}" cy="${y + cardH/2}" r="13" fill="${circleColor}"/>
            <text x="${rowX - 22}" y="${y + cardH/2 + 4}" class="stepNum">${isPast ? "✓" : (rowIdx + 1)}</text>`;

    items.forEach((stage, colIdx) => {
      const def = STAGE_DEFS[stage.type] || {category: "auth", name: stage.type, icon: "❓", desc: ""};
      const x = rowX + colIdx * (cardW + gap);

      // Card opacity for past/future
      const opacity = isFuture ? 0.5 : 1;
      const strokeColor = isActive ? colorFg[def.category] : "rgba(60,60,67,0.18)";
      const strokeWidth = isActive ? 2 : 0.5;

      // Card with shadow
      svg += `<rect x="${x + 1}" y="${y + 2}" width="${cardW}" height="${cardH}" rx="11" fill="rgba(0,0,0,0.04)" opacity="${opacity}"/>
              <rect x="${x}" y="${y}" width="${cardW}" height="${cardH}" rx="11"
              fill="white" stroke="${strokeColor}" stroke-width="${strokeWidth}" opacity="${opacity}"/>`;

      // Category strip on left
      svg += `<rect x="${x}" y="${y}" width="3" height="${cardH}" rx="1.5" fill="${colorFg[def.category]}" opacity="${opacity}"/>`;

      // Icon box
      const iconX = x + 16, iconY = y + 14;
      svg += `<rect x="${iconX}" y="${iconY}" width="32" height="32" rx="8" fill="${colorBg[def.category]}" opacity="${opacity}"/>
              <text x="${iconX + 16}" y="${iconY + 22}" font-size="16" text-anchor="middle" opacity="${opacity}">${def.icon}</text>`;

      // Name + desc
      const textX = x + 60;
      svg += `<text x="${textX}" y="${y + 26}" class="stageName" opacity="${opacity}">${escapeXml(def.name)}</text>`;
      const maxDescChars = Math.floor((cardW - 76) / 6);
      const desc = def.desc.length > maxDescChars ? def.desc.slice(0, maxDescChars - 1) + "…" : def.desc;
      svg += `<text x="${textX}" y="${y + 42}" class="stageDesc" opacity="${opacity}">${escapeXml(desc)}</text>`;

      // Category tag top-right
      const catW = 70;
      svg += `<rect x="${x + cardW - catW - 12}" y="${y + 14}" width="${catW}" height="16" rx="4" fill="${colorBg[def.category]}" opacity="${opacity}"/>
              <text x="${x + cardW - catW/2 - 12}" y="${y + 25}" class="catTag" fill="${colorFg[def.category]}" text-anchor="middle" opacity="${opacity}">${catLabel[def.category]}</text>`;

      // Limit badges (bottom)
      const t = stage.config?.timeout, mr = stage.config?.maxRetries;
      let bx = x + 16, by = y + cardH - 24;
      if (t !== null && t !== undefined) {
        const bw = 48;
        svg += `<rect x="${bx}" y="${by}" width="${bw}" height="16" rx="4" fill="rgba(255,149,0,0.10)" stroke="rgba(255,149,0,0.25)" stroke-width="0.5" opacity="${opacity}"/>
                <text x="${bx + bw/2}" y="${by + 11}" class="badge" text-anchor="middle" opacity="${opacity}">⏱ ${t}s</text>`;
        bx += bw + 4;
      }
      if (mr !== null && mr !== undefined) {
        const bw = 38;
        svg += `<rect x="${bx}" y="${by}" width="${bw}" height="16" rx="4" fill="rgba(255,149,0,0.10)" stroke="rgba(255,149,0,0.25)" stroke-width="0.5" opacity="${opacity}"/>
                <text x="${bx + bw/2}" y="${by + 11}" class="badge" text-anchor="middle" opacity="${opacity}">🔁 ${mr}×</text>`;
      }

      // Active step indicator (pulsing ring)
      if (isActive) {
        svg += `<rect x="${x - 4}" y="${y - 4}" width="${cardW + 8}" height="${cardH + 8}" rx="13" fill="none" stroke="${colorFg[def.category]}" stroke-width="2" stroke-dasharray="6 3" opacity="0.6">
                  <animate attributeName="stroke-dashoffset" from="0" to="18" dur="1.5s" repeatCount="indefinite"/>
                </rect>`;
      }
    });

    y += cardH + rowGap;
    if (rowIdx < stages.length - 1) {
      svg += `<text x="${totalW/2}" y="${y - 10}" class="arrow" text-anchor="middle">↓</text>`;
    }
  });

  // Footer
  const date = new Date().toLocaleDateString("tr-TR");
  svg += `<text x="${padX}" y="${totalH - 14}" class="footer">MKK Auth — ${escapeXml(title)} · ${date}</text>`;
  svg += `</svg>`;
  return svg;
}

function escapeXml(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&apos;"}[c]));
}

// Download SVG as PNG via canvas
async function downloadAsPng(kind) {
  if (!state.policy) { alert("Önce policy yükle"); return; }
  const svg = $("flow-svg-container").querySelector("svg");
  if (!svg) { alert("Render edilmiş SVG yok"); return; }

  const svgString = new XMLSerializer().serializeToString(svg);
  const svgBlob = new Blob([svgString], {type: "image/svg+xml;charset=utf-8"});
  const url = URL.createObjectURL(svgBlob);

  const img = new Image();
  img.onload = () => {
    const scale = 2; // 2x for retina
    const canvas = document.createElement("canvas");
    canvas.width = svg.viewBox.baseVal.width * scale;
    canvas.height = svg.viewBox.baseVal.height * scale;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    canvas.toBlob((blob) => {
      const dlUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const name = (state.policy.policyName || "flow").replace(/[^a-z0-9_-]/gi, "_");
      a.href = dlUrl;
      a.download = `${name}_${kind}.png`;
      a.click();
      URL.revokeObjectURL(dlUrl);
    }, "image/png");
  };
  img.onerror = () => alert("PNG dönüşümünde hata");
  img.src = url;
}

function cancelRedirect() {
  if (state.redirectInterval) {
    clearInterval(state.redirectInterval);
    state.redirectInterval = null;
  }
  const t = document.getElementById("auto-redirect-text");
  if (t) t.style.display = "none";
}

// =====================================================================
// AUTOFILL — One-click form filling with test credentials
// =====================================================================

function needsAutofill(stageType) {
  return [
    "mersis_lookup", "tckn_standalone", "generic_lookup",
    "field_match", "userpass", "ldap", "totp", "esign",
    "captcha", "image_captcha",
    "sms_oob", "email_oob",
  ].includes(stageType);
}

// Auto-paste OOB codes from sent messages (SMS/Email kept track of)
const lastCodes = { sms: null, email: null };

async function autofillStage(stageType, stepIdx, colIdx) {
  const c = state.testCreds || {};
  const fname = (s) => `s_${stepIdx}_${colIdx}_${s}`;
  const setField = (suffix, value) => {
    const el = document.querySelector(`[name="${fname(suffix)}"]`);
    if (el) {
      el.value = value;
      el.classList.add("autofilled");
      setTimeout(() => el.classList.remove("autofilled"), 1500);
    }
  };

  // Helper: also fill the inline captcha if the stage has requireCaptcha
  const fillInlineCaptcha = () => {
    const cb = document.getElementById(`captcha-inline-${stepIdx}-${colIdx}-cb`);
    const h = document.getElementById(`captcha-inline-${stepIdx}-${colIdx}-h`);
    if (cb && h) {
      cb.checked = true;
      h.value = "verified";
      cb.classList.add("autofilled");
      setTimeout(() => cb.classList.remove("autofilled"), 1500);
    }
  };

  // Find the current stage's config to know identifierType etc.
  const policy = state.policy;
  const step = policy?.stages?.[stepIdx];
  const stage = step?.items?.[colIdx];
  const cfg = stage?.config || {};

  switch (stageType) {
    case "mersis_lookup": {
      const m = (c.mersis || [])[0];
      if (!m) { alert("Test MERSIS yok"); return; }
      setField("in", m.mersis);
      if (cfg.requirePassword) {
        // Find matching credential
        const cred = (c.mersis || []).find(x => x.mersis === m.mersis);
        // mersis password lives under credentials.mersis
        // simpler: just write a placeholder valid password
        setField("p", "mersis12");
      }
      fillInlineCaptcha();
      showAutofillToast("MERSIS dolduruldu", `${m.mersis} (${m.company_name})`);
      break;
    }
    case "tckn_standalone": {
      const t = (c.tckn || [])[0];
      if (!t) { alert("Test TCKN yok"); return; }
      setField("in", t.tckn);
      if (cfg.requirePassword) setField("p", t.password);
      fillInlineCaptcha();
      showAutofillToast("TCKN dolduruldu", `${t.tckn} (${t.name})`);
      break;
    }
    case "generic_lookup": {
      // Use first VKN as fallback
      const v = (c.vkn || [])[0];
      if (!v) { alert("Test VKN yok"); return; }
      setField("in", v.vkn);
      if (cfg.requirePassword) setField("p", v.password);
      fillInlineCaptcha();
      showAutofillToast("Veri dolduruldu", v.vkn);
      break;
    }
    case "field_match": {
      // Use mersis_data's first representative TCKN
      const ms = state.currentState?.context?.mersis_data;
      if (ms?.representatives?.length) {
        const rep = ms.representatives[0];
        const matchField = cfg.inputField || "tckn";
        const value = rep[matchField] || rep.tckn;
        setField("in", value);
        showAutofillToast("Field Match dolduruldu", `${rep.name} (${value})`);
      } else {
        const t = (c.tckn || [])[0];
        if (t) {
          setField("in", t.tckn);
          showAutofillToast("Field Match dolduruldu", t.tckn);
        }
      }
      break;
    }
    case "userpass": {
      const idType = cfg.identifierType || "username";
      // Pick the right test user for this identifier type
      let user, pwd, label;
      if (idType === "tckn" && c.tckn?.length) {
        user = c.tckn[0]; pwd = user.password; label = `${user.tckn} / ${user.name}`;
        setField("u", user.tckn); setField("p", pwd);
      } else if (idType === "vkn" && c.vkn?.length) {
        user = c.vkn[0]; pwd = user.password; label = `${user.vkn} / ${user.company}`;
        setField("u", user.vkn); setField("p", pwd);
      } else if (idType === "sicil" && c.sicil?.length) {
        user = c.sicil[0]; pwd = user.password; label = `${user.sicil} / ${user.name}`;
        setField("u", user.sicil); setField("p", pwd);
      } else if (idType === "passport" && c.passport?.length) {
        user = c.passport[0]; pwd = user.password; label = `${user.passport} / ${user.name}`;
        setField("u", user.passport); setField("p", pwd);
      } else if (c.usernames?.length) {
        user = c.usernames[0]; pwd = user.password; label = `${user.username} / ${user.name}`;
        setField("u", user.username); setField("p", pwd);
      } else { alert("Bu tip için test kullanıcı yok"); return; }
      fillInlineCaptcha();
      showAutofillToast(`${idType} + Şifre dolduruldu`, label);
      break;
    }
    case "ldap": {
      const l = (c.ldap || [])[0];
      if (!l) { alert("Test LDAP yok"); return; }
      setField("u", l.username); setField("p", l.password);
      fillInlineCaptcha();
      showAutofillToast("LDAP dolduruldu", `${l.username} (${l.cn})`);
      break;
    }
    case "totp": {
      // Any 6-digit non-000000
      const code = String(Math.floor(100000 + Math.random() * 900000));
      setField("in", code);
      showAutofillToast("TOTP dolduruldu", code);
      break;
    }
    case "esign": {
      setField("in", "1234");
      showAutofillToast("e-İmza PIN dolduruldu", "1234");
      break;
    }
    case "captcha": {
      // Check the reCAPTCHA-style checkbox if present
      const cb = document.getElementById(`recaptcha-${stepIdx}-${colIdx}`);
      const hidden = document.getElementById(`captcha-hidden-${stepIdx}-${colIdx}`);
      if (cb && hidden) {
        cb.checked = true;
        hidden.value = "verified";
        cb.classList.add("autofilled");
        setTimeout(() => cb.classList.remove("autofilled"), 1500);
      } else {
        setField("in", "demo");
      }
      showAutofillToast("Captcha doğrulandı", "✓ Ben robot değilim");
      break;
    }
    case "image_captcha": {
      // Read the displayed code from the page
      const el = document.querySelector(`#captcha-display-${stepIdx}-${colIdx}`);
      if (el && el.textContent && el.textContent !== "YÜKLENİYOR...") {
        setField("in", el.textContent);
        showAutofillToast("Captcha dolduruldu", el.textContent);
      } else {
        alert("Captcha henüz yüklenmedi");
      }
      break;
    }
    case "sms_oob": {
      let code = lastCodes.sms;
      if (!code && state.sessionId) {
        // Fetch from server (SSE may be slow, fall back to direct GET)
        try {
          const r = await fetch(`/api/oob-codes/${state.sessionId}`);
          const data = await r.json();
          if (data.sms) {
            code = data.sms;
            lastCodes.sms = code;
          }
        } catch (e) { console.warn(e); }
      }
      if (!code) {
        alert("Henüz SMS kodu gönderilmedi.\n\nÖnce kullanıcının belirlenmesi (TCKN/MERSIS sorgu) ve SMS'in tetiklenmesi gerek.");
        return;
      }
      setField("in", code);
      showAutofillToast("SMS kodu dolduruldu", code);
      break;
    }
    case "email_oob": {
      let code = lastCodes.email;
      if (!code && state.sessionId) {
        try {
          const r = await fetch(`/api/oob-codes/${state.sessionId}`);
          const data = await r.json();
          if (data.email) {
            code = data.email;
            lastCodes.email = code;
          }
        } catch (e) { console.warn(e); }
      }
      if (!code) {
        alert("Henüz Email kodu gönderilmedi.\n\nÖnce kullanıcının belirlenmesi (TCKN/MERSIS sorgu) ve Email'in tetiklenmesi gerek.");
        return;
      }
      setField("in", code);
      showAutofillToast("Email kodu dolduruldu", code);
      break;
    }
  }
}

// Tiny status toast at bottom-right
function showAutofillToast(title, value) {
  let container = $("autofill-toasts");
  if (!container) {
    container = document.createElement("div");
    container.id = "autofill-toasts";
    container.className = "autofill-toasts";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = "autofill-toast";
  toast.innerHTML = `<strong>✨ ${escapeHtml(title)}</strong><div>${escapeHtml(value)}</div>`;
  container.appendChild(toast);
  setTimeout(() => toast.style.opacity = "0", 2000);
  setTimeout(() => toast.remove(), 2500);
}

window.startSession = startSession;
window.submitForm = submitForm;
window.respondPush = respondPush;
window.simulateIdpCallback = simulateIdpCallback;
window.cancelRedirect = cancelRedirect;
window.autofillStage = autofillStage;
window.autofillCode = autofillCode;
