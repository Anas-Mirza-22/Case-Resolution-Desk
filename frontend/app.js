/* --- Elements ----------------------------------------------------------- */
const form = document.getElementById("case-form");
const formError = document.getElementById("form-error");
const reviewPanel = document.getElementById("review-panel");
const analyzeBtn = document.getElementById("analyze-btn");
const clearAllBtn = document.getElementById("clear-all");

/* --- Status labels ------------------------------------------------------
 * The workflow status answers "whose turn is it to act next?". It is
 * distinct from eligibility, which is the verdict on current facts.
 */
const STATUS_LABELS = {
  "Open": "Next: Coordinator",
  "Waiting for Learner": "Next: Learner",
  "Waiting for Mentor": "Next: Mentor",
  "Ready for Review": "Next: Reviewer",
  "Closed": "Done",
};

const STATUS_TOOLTIPS = {
  "Open": "Case received; awaiting coordinator triage.",
  "Waiting for Learner": "Learner must supply missing facts or a corrected submission.",
  "Waiting for Mentor": "Mentor approval is outstanding (extension or makeup).",
  "Ready for Review": "All current facts are available; a human reviewer must decide.",
  "Closed": "Coordinator has recorded the outcome.",
};

/* --- Example fixtures --------------------------------------------------- */
const EXAMPLES = {
  A: {
    learner_name: "Nadia",
    question: "Can I still receive a certificate, and can I submit my capstone one day late?",
    attendance_pct: 76,
    live_sessions: 2,
    capstone_score: null,
    submission_state: "unknown",
    extension_state: "requested_pending",
    extension_requested_at: "2026-10-07T11:00",
    medical_note: "offered_unverified",
    makeup_state: "none",
    missed_session_date: "",
    learner_notes: "A colleague sent an older policy saying 60 is enough to pass.",
  },
  B: {
    learner_name: "Hamza",
    question: "Have I passed and can I get my certificate?",
    attendance_pct: 82,
    live_sessions: 3,
    capstone_score: 78,
    submission_state: "secret_found",
    extension_state: "not_requested",
    medical_note: "none",
    makeup_state: "none",
    learner_notes: "ZIP and README submitted.",
  },
  C: {
    learner_name: "Sara",
    question: "A colleague said 60 is the passing score. Can I get a certificate?",
    attendance_pct: 85,
    live_sessions: 3,
    capstone_score: 65,
    submission_state: "safe",
    extension_state: "not_requested",
    medical_note: "none",
    makeup_state: "none",
    learner_notes: "",
  },
  D: {
    learner_name: "Unknown Learner",
    question: "Am I eligible?",
    attendance_pct: null,
    live_sessions: null,
    capstone_score: null,
    submission_state: "unknown",
    extension_state: "unknown",
    medical_note: "none",
    makeup_state: "none",
    learner_notes: "",
  },
};

/* --- Example chips ------------------------------------------------------ */
function setFormValue(name, value) {
  const el = form.elements[name];
  if (!el) return;
  el.value = value === null || value === undefined ? "" : value;
}

function clearActiveChips() {
  document.querySelectorAll(".chip--example").forEach((c) =>
    c.classList.remove("chip--active")
  );
}

document.querySelectorAll("[data-example]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const ex = EXAMPLES[btn.dataset.example];
    if (!ex) return;
    Object.entries(ex).forEach(([k, v]) => setFormValue(k, v));
    clearActiveChips();
    btn.classList.add("chip--active");
  });
});

/* --- Submit ------------------------------------------------------------- */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;
  formError.textContent = "";

  const fd = new FormData(form);
  const payload = {
    learner_name: fd.get("learner_name").trim(),
    question: fd.get("question").trim(),
    assessed_on: fd.get("assessed_on") || "2026-10-07",
    attendance_pct:
      fd.get("attendance_pct") === "" ? null : Number(fd.get("attendance_pct")),
    live_sessions:
      fd.get("live_sessions") === "" ? null : Number(fd.get("live_sessions")),
    capstone_score:
      fd.get("capstone_score") === "" ? null : Number(fd.get("capstone_score")),
    submission_state: fd.get("submission_state"),
    extension_state: fd.get("extension_state"),
    extension_requested_at: fd.get("extension_requested_at") || null,
    medical_note: fd.get("medical_note"),
    makeup_state: fd.get("makeup_state"),
    missed_session_date: fd.get("missed_session_date") || null,
    learner_notes: fd.get("learner_notes") || "",
  };
  if (
    payload.extension_requested_at &&
    !payload.extension_requested_at.includes("+") &&
    !payload.extension_requested_at.endsWith("Z")
  ) {
    payload.extension_requested_at += "+05:00";
  }

  analyzeBtn.disabled = true;
  const label = analyzeBtn.querySelector(".btn__label");
  if (label) label.textContent = "Analyzing…";

  try {
    const res = await fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      formError.textContent = data?.error?.message || "Request failed.";
      formError.hidden = false;
      return;
    }
    renderReview(data);
    loadHistory(data.id);
    reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    formError.textContent = "Network error. Please try again.";
    formError.hidden = false;
  } finally {
    analyzeBtn.disabled = false;
    if (label) label.textContent = "Analyze";
  }
});

/* --- Helpers ------------------------------------------------------------ */
function eligibilityClass(v) {
  if (v === "eligible") return "is-eligible";
  if (v === "ineligible") return "is-ineligible";
  return "is-pending";
}

function setBadge(id, cls, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = "badge " + cls;
  el.textContent = text;
}

function formatValue(v, suffix = "") {
  if (v === null || v === undefined) return "unknown";
  if (typeof v === "number") return v + suffix;
  return v + suffix;
}

/* --- Metric tile populator --------------------------------------------- */
function setMetric(tileId, value, state) {
  const tile = document.getElementById(tileId);
  if (!tile) return;
  tile.classList.remove("is-met", "is-miss", "is-unk");
  tile.classList.add(
    state === "met" ? "is-met" : state === "miss" ? "is-miss" : "is-unk"
  );
  const span = tile.querySelector("[data-metric]");
  if (span) span.textContent = value;
}

function populateMetrics(c) {
  const reqs = Object.fromEntries(
    (c.outcome.requirement_results || []).map((r) => [r.name, r])
  );

  const att = reqs["attendance"];
  setMetric(
    "metric-attendance",
    formatValue(c.inputs.attendance_pct, "%"),
    att ? (att.met === true ? "met" : att.met === false ? "miss" : "unk") : "unk"
  );

  const ses = reqs["live_sessions"];
  setMetric(
    "metric-sessions",
    formatValue(c.inputs.live_sessions),
    ses ? (ses.met === true ? "met" : ses.met === false ? "miss" : "unk") : "unk"
  );

  const cap = reqs["capstone"];
  setMetric(
    "metric-capstone",
    formatValue(c.inputs.capstone_score, "/100"),
    cap ? (cap.met === true ? "met" : cap.met === false ? "miss" : "unk") : "unk"
  );

  const sub = reqs["submission"];
  const submissionLabel =
    c.outcome.submission_hold === "none"
      ? "safe"
      : c.outcome.submission_hold.replace(/_/g, " ");
  setMetric(
    "metric-submission",
    submissionLabel,
    sub ? (sub.met === true ? "met" : sub.met === false ? "miss" : "unk") : "unk"
  );
}

/* --- Review renderer ---------------------------------------------------- */
function renderReview(c) {
  reviewPanel.hidden = false;
  document.getElementById("review-learner").textContent =
    c.inputs?.learner_name ? `${c.inputs.learner_name}` : "";

  const elig = c.outcome.eligibility;

  const ribbon = document.getElementById("verdict-ribbon");
  ribbon.style.setProperty("--ribbon-x", "18%");
  ribbon.style.setProperty(
    "--ribbon-glow",
    elig === "eligible"
      ? "rgba(53,210,154,0.16)"
      : elig === "ineligible"
      ? "rgba(255,107,107,0.16)"
      : "rgba(247,185,85,0.16)"
  );

  const orb = document.getElementById("verdict-orb");
  orb.className = "verdict-ribbon__orb " + eligibilityClass(elig);

  document.getElementById("verdict-value").textContent = elig;
  document.getElementById("verdict-next").textContent =
    STATUS_LABELS[c.status] || c.status;

  setBadge("badge-eligibility", eligibilityClass(elig), elig);
  setBadge(
    "badge-hold",
    c.outcome.submission_hold === "none" ? "is-info" : "is-ineligible",
    "hold: " + c.outcome.submission_hold
  );
  setBadge("badge-status", "is-info", STATUS_LABELS[c.status] || c.status);

  populateMetrics(c);

  const llmError = document.getElementById("llm-error");
  if (c.llm_error) {
    llmError.hidden = false;
    llmError.textContent = c.llm_error;
  } else {
    llmError.hidden = true;
  }

  document.getElementById("answer").textContent =
    c.answer || "(Explanation unavailable — see error above.)";

  const cites = document.getElementById("citations");
  cites.innerHTML = "";
  if (!c.citations || c.citations.length === 0) {
    const li = document.createElement("li");
    li.textContent = "None";
    cites.appendChild(li);
  } else {
    c.citations.forEach((cit) => {
      const li = document.createElement("li");
      if (cit.superseded) li.classList.add("is-superseded");
      li.appendChild(document.createTextNode(`${cit.doc_id} ${cit.version}`));
      cites.appendChild(li);
    });
  }

  const missing = document.getElementById("missing");
  missing.innerHTML = "";
  const missingItems =
    c.missing_facts && c.missing_facts.length ? c.missing_facts : ["None"];
  missingItems.forEach((m) => {
    const li = document.createElement("li");
    li.textContent = m;
    missing.appendChild(li);
  });

  document.getElementById("next-action").textContent = c.next_action || "";
  const othersWrap = document.getElementById("other-actions-wrap");
  const others = document.getElementById("other-actions");
  others.innerHTML = "";
  if (c.other_actions && c.other_actions.length) {
    othersWrap.hidden = false;
    c.other_actions.forEach((a) => {
      const li = document.createElement("li");
      li.textContent = a;
      others.appendChild(li);
    });
  } else {
    othersWrap.hidden = true;
  }

  document.getElementById("case-note").textContent = c.case_note || "";
}

/* --- Delete one case ---------------------------------------------------- */
async function deleteCase(caseId, ev) {
  ev.stopPropagation();
  if (!window.confirm(`Delete case #${caseId}? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/api/cases/${caseId}`, { method: "DELETE" });
    if (res.status !== 204 && res.status !== 404) {
      window.alert("Could not delete the case.");
      return;
    }
    await loadHistory();
  } catch {
    window.alert("Network error while deleting the case.");
  }
}

/* --- Clear all cases ---------------------------------------------------- */
if (clearAllBtn) {
  clearAllBtn.addEventListener("click", async () => {
    if (!window.confirm("Delete every saved case? This cannot be undone.")) return;
    try {
      const res = await fetch("/api/cases");
      const rows = await res.json();
      await Promise.all(
        rows.map((row) => fetch(`/api/cases/${row.id}`, { method: "DELETE" }))
      );
      await loadHistory();
      reviewPanel.hidden = true;
    } catch {
      window.alert("Network error while clearing cases.");
    }
  });
}

/* --- History (sidebar case log) ---------------------------------------- */
async function loadHistory(highlightId = null) {
  const list = document.getElementById("history");
  list.innerHTML = "";

  try {
    const res = await fetch("/api/cases");
    const rows = await res.json();

    if (!rows.length) {
      const li = document.createElement("li");
      li.className = "case-log__empty";
      li.textContent = "No cases yet.";
      list.appendChild(li);
      return;
    }

    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "case-log__item " + eligibilityClass(row.eligibility);
      if (highlightId && row.id === highlightId) li.classList.add("is-active");

      li.addEventListener("click", async () => {
        document
          .querySelectorAll(".case-log__item")
          .forEach((el) => el.classList.remove("is-active"));
        li.classList.add("is-active");
        const detail = await fetch(`/api/cases/${row.id}`).then((r) => r.json());
        renderReview(detail);
        reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      });

      const top = document.createElement("div");
      top.className = "case-log__top";

      const idSpan = document.createElement("span");
      idSpan.className = "case-log__id";
      idSpan.textContent = `#${row.id}`;
      top.appendChild(idSpan);

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "case-log__delete";
      delBtn.title = `Delete case #${row.id}`;
      delBtn.setAttribute("aria-label", `Delete case #${row.id}`);
      delBtn.textContent = "×";
      delBtn.addEventListener("click", (ev) => deleteCase(row.id, ev));
      top.appendChild(delBtn);

      const nameDiv = document.createElement("div");
      nameDiv.className = "case-log__name";
      nameDiv.textContent = row.learner_name;

      const pills = document.createElement("div");
      pills.className = "case-log__pills";

      const eligPill = document.createElement("span");
      eligPill.className = "badge " + eligibilityClass(row.eligibility);
      eligPill.textContent = row.eligibility;
      pills.appendChild(eligPill);

      const statusPill = document.createElement("span");
      statusPill.className = "badge is-info";
      statusPill.textContent = STATUS_LABELS[row.status] || row.status;
      statusPill.title = STATUS_TOOLTIPS[row.status] || "";
      pills.appendChild(statusPill);

      li.append(top, nameDiv, pills);
      list.appendChild(li);
    });
  } catch {
    list.innerHTML = "";
    const li = document.createElement("li");
    li.className = "case-log__empty";
    li.textContent = "Could not load history.";
    list.appendChild(li);
  }
}

loadHistory();