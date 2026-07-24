/* ── Juriscite — Drafting Engine JS ── */

/* ── WB-07: edit mode + blank entry + review-own-draft ── */
function _editorEl() { return document.getElementById("output-editor"); }

function enterEditMode() {
  const ta = _editorEl();
  ta.value = generatedText || "";
  document.getElementById("output-body").style.display = "none";
  ta.style.display = "";
  document.getElementById("edit-toolbar").style.display = "flex";
  document.getElementById("btn-edit").style.display = "none";
  ta.addEventListener("input", () => { generatedText = ta.value; });
  ta.focus();
}

function startBlankDocument() {
  closeReviewMode();
  selectedDocType = { id: "blank_document", label: "Blank Document" };
  generatedText = "";
  const out = document.getElementById("draft-output");
  if (out) out.classList.add("visible");
  document.getElementById("output-badge").textContent = "Blank — yours to write";
  enterEditMode();
  toast("Blank document — write freely, then Save for review.");
}

async function applyEdit(action) {
  const ta = _editorEl();
  const start = ta.selectionStart, end = ta.selectionEnd;
  if (end - start < 4) { toast("Select the passage to transform first.", "error"); return; }
  let instruction = "";
  if (action === "tone") {
    instruction = prompt("Tone? (e.g. firmer, more conciliatory, plain-English)") || "";
    if (!instruction) return;
  }
  if (action === "add_clause") {
    instruction = prompt("Describe the clause to add:") || "";
    if (!instruction) return;
  }
  const hint = document.getElementById("edit-hint");
  hint.textContent = "transforming…";
  try {
    const r = await apiFetch("/api/drafting/edit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action, instruction,
        selection: ta.value.slice(start, end),
        context: ta.value.slice(Math.max(0, start - 1500), Math.min(ta.value.length, end + 1500)),
      }),
    });
    const body = await r.json();
    if (!r.ok) { toast(body.detail || "Edit failed — nothing changed.", "error"); return; }
    ta.value = ta.value.slice(0, start) + body.replacement + ta.value.slice(end);
    generatedText = ta.value;
    ta.setSelectionRange(start, start + body.replacement.length);
    ta.focus();
    toast("Applied — review the change; saving keeps full version history.");
  } catch (_) { toast("Network error — nothing changed.", "error"); }
  finally { hint.textContent = "select text below, then choose an action"; }
}

let lastReview = null;
function openReviewMode() {
  document.getElementById("draft-form").style.display = "none";
  const out = document.getElementById("draft-output");
  if (out) out.classList.remove("visible");
  document.getElementById("review-panel").style.display = "";
}
function closeReviewMode() {
  document.getElementById("review-panel").style.display = "none";
  document.getElementById("draft-form").style.display = "";
}
async function runOwnDraftReview() {
  const content = document.getElementById("review-input").value.trim();
  if (content.length < 50) { toast("Paste at least 50 characters of draft.", "error"); return; }
  const btn = document.getElementById("review-run");
  btn.disabled = true; btn.textContent = "Reviewing…";
  try {
    const r = await apiFetch("/api/drafting/review-draft", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    const body = await r.json();
    if (!r.ok) {
      const d = body.detail || {};
      toast(d.message || (typeof d === "string" ? d : "Review failed."), "error");
      if (d.upgrade_url) setTimeout(() => location.href = d.upgrade_url, 1600);
      return;
    }
    lastReview = body;
    document.getElementById("review-body").textContent = body.review;
    document.getElementById("review-cites").textContent = body.verified_citations.length
      ? "Verified citations: " + body.verified_citations.map(c => "s." + c).join(", ")
      : "No statutory citations verified";
    document.getElementById("review-result").style.display = "";
  } finally { btn.disabled = false; btn.textContent = "Run review"; }
}
async function saveReviewToQueue() {
  if (!lastReview) return;
  const r = await apiFetch("/api/drafts/", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_type: "draft_review",
                           title: "Own-draft review — " + new Date().toLocaleDateString("en-IN"),
                           content: lastReview.review }),
  });
  if (r.ok) { toast("Saved — opening Drafts…"); setTimeout(() => location.href = "/drafts", 1100); }
  else toast("Save failed.", "error");
}

/* ── Draft from matter: pre-fill fields from an existing case ── */
let matters = [], clientNames = {}, selectedMatter = null;

async function loadMatters() {
  try {
    const [cRes, clRes] = await Promise.all([apiFetch("/api/cases/"), apiFetch("/api/clients/")]);
    matters = cRes.ok ? await cRes.json() : [];
    (clRes.ok ? await clRes.json() : []).forEach(c => { clientNames[c.id] = c.full_name; });
    const sel = document.getElementById("matter-select");
    if (!sel || !matters.length) return;
    matters.forEach(m => {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.title.length > 34 ? m.title.slice(0, 33) + "…" : m.title;
      sel.appendChild(o);
    });
  } catch (_) {}
}

function onMatterChange() {
  const id = document.getElementById("matter-select").value;
  selectedMatter = matters.find(m => String(m.id) === id) || null;
  if (selectedDocType) applyMatterPrefill();
}

function matterParties() {
  // "A vs B" / "A v. B" in the matter title → (party, opposite party)
  const t = selectedMatter?.title || "";
  const m = t.split(/\s+(?:vs\.?|v\.|versus)\s+/i);
  const partyA = (m[0] || "").trim(), partyB = (m[1] || "").trim();
  return {
    party: clientNames[selectedMatter?.client_id] || partyA,
    opposite: partyB,
  };
}

function applyMatterPrefill() {
  if (!selectedMatter) return;
  const { party, opposite } = matterParties();
  const factsText = `Matter: ${selectedMatter.title}.` +
    (selectedMatter.description ? ` ${selectedMatter.description}` : "");
  document.querySelectorAll("#form-fields input, #form-fields textarea").forEach(el => {
    if (el.value.trim()) return;                     // never overwrite what the advocate typed
    const k = (el.name || "").toLowerCase();
    if (/address/.test(k)) return;   // matters carry no addresses — leave for the advocate
    let v = "";
    if (/client|applicant|complainant|payee|petitioner|plaintiff|deponent|party_name|sender/.test(k)) v = party;
    else if (/opposite|respondent|defendant|drawer|accused|recipient|noticee/.test(k)) v = opposite;
    else if (/facts|instructions|parties_and_facts|brief|cause_of_action|subject/.test(k)) v = factsText;
    if (v) { el.value = v; el.dispatchEvent(new Event("input", { bubbles: true })); }
  });
  if (typeof validateForm === "function") validateForm();
}

// Document type metadata (mirrors backend catalogue)
const DOC_TYPES = [
  {
    id: "custom_document",
    icon: "pen-line",
    label: "Custom Document",
    sub: "Describe anything to draft",
    fields: [
      { key: "document_title",    label: "Document Title / Type",                type: "text",     span: true,  placeholder: "e.g. Rent Agreement, Reply to Notice, Partnership Deed" },
      { key: "instructions",      label: "Instructions — what it must achieve",  type: "textarea", span: true  },
      { key: "parties_and_facts", label: "Parties / Facts / Details",            type: "textarea", span: true  },
    ],
  },
  {
    id: "crpc_application",
    icon: "scale",
    label: "Criminal Misc. Application",
    sub: "Any BNSS / CrPC section",
    fields: [
      { key: "court_name",     label: "Court",                     type: "text",     span: true  },
      { key: "case_number",    label: "Pending Case / FIR No.",    type: "text",     span: false },
      { key: "applicant_name", label: "Applicant Name",            type: "text",     span: false },
      { key: "applicant_role", label: "Applicant's Role",          type: "text",     span: false, placeholder: "accused / complainant / victim" },
      { key: "opposite_party", label: "Opposite Party / State",    type: "text",     span: false },
      { key: "provision",      label: "Provision Invoked",         type: "text",     span: true,  placeholder: "e.g. Section 349 BNSS (recall witness — old s.311 CrPC)" },
      { key: "purpose",        label: "Purpose of Application",    type: "text",     span: true  },
      { key: "facts",          label: "Relevant Facts",            type: "textarea", span: true  },
      { key: "grounds",        label: "Grounds",                   type: "textarea", span: true  },
      { key: "relief_sought",  label: "Relief Sought",             type: "textarea", span: true  },
    ],
  },
  {
    id: "cpc_application",
    icon: "clipboard-list",
    label: "Civil Misc. Application (I.A.)",
    sub: "Any CPC Order / Section",
    fields: [
      { key: "court_name",     label: "Court",                     type: "text",     span: true  },
      { key: "case_number",    label: "Pending Suit / Case No.",   type: "text",     span: false },
      { key: "applicant_name", label: "Applicant Name",            type: "text",     span: false },
      { key: "applicant_role", label: "Applicant's Role",          type: "text",     span: false, placeholder: "plaintiff / defendant" },
      { key: "opposite_party", label: "Opposite Party",            type: "text",     span: false },
      { key: "provision",      label: "Provision Invoked",         type: "text",     span: true,  placeholder: "e.g. Order VI Rule 17 CPC / Order XXVI Rule 9 / s.151 CPC" },
      { key: "purpose",        label: "Purpose of Application",    type: "text",     span: true  },
      { key: "facts",          label: "Relevant Facts",            type: "textarea", span: true  },
      { key: "grounds",        label: "Grounds",                   type: "textarea", span: true  },
      { key: "relief_sought",  label: "Relief Sought",             type: "textarea", span: true  },
    ],
  },
  {
    id: "legal_notice_cpc",
    icon: "file-text",
    label: "Legal Notice",
    sub: "Section 80 CPC",
    fields: [
      { key: "sender_name",       label: "Sender / Advocate Name",      type: "text",     span: false },
      { key: "sender_address",    label: "Sender's Address",             type: "textarea", span: false },
      { key: "recipient_name",    label: "Recipient / Opposite Party",   type: "text",     span: false },
      { key: "recipient_address", label: "Recipient's Address",          type: "textarea", span: false },
      { key: "subject_matter",    label: "Subject / Nature of Dispute",  type: "text",     span: true  },
      { key: "amount_or_relief",  label: "Amount / Relief Claimed",      type: "text",     span: false },
      { key: "cause_of_action",   label: "Cause of Action (brief facts)",type: "textarea", span: true  },
      { key: "demand_period_days",label: "Notice Period (days)",          type: "text",     span: false, placeholder: "e.g. 30" },
    ],
  },
  {
    id: "cheque_dishonour",
    icon: "banknote",
    label: "Cheque Dishonour Notice",
    sub: "Section 138 NI Act",
    fields: [
      { key: "payee_name",        label: "Payee / Complainant Name",   type: "text",     span: false },
      { key: "payee_address",     label: "Payee's Address",            type: "textarea", span: false },
      { key: "drawer_name",       label: "Drawer / Accused Name",      type: "text",     span: false },
      { key: "drawer_address",    label: "Drawer's Address",           type: "textarea", span: false },
      { key: "cheque_number",     label: "Cheque Number",              type: "text",     span: false },
      { key: "cheque_date",       label: "Cheque Date",                type: "date",     span: false },
      { key: "cheque_amount",     label: "Cheque Amount (₹)",          type: "text",     span: false, placeholder: "e.g. 2,50,000" },
      { key: "bank_name",         label: "Bank & Branch",              type: "text",     span: false },
      { key: "dishonour_date",    label: "Date of Dishonour",          type: "date",     span: false },
      { key: "dishonour_reason",  label: "Reason for Dishonour",       type: "text",     span: false, placeholder: "e.g. Funds Insufficient" },
      { key: "underlying_liability", label: "Underlying Debt / Liability", type: "textarea", span: true },
    ],
  },
  {
    id: "anticipatory_bail",
    icon: "scale",
    label: "Anticipatory Bail Application",
    sub: "Section 482 BNSS / 438 CrPC",
    fields: [
      { key: "court_name",         label: "Court Name",                   type: "text",     span: true  },
      { key: "applicant_name",     label: "Applicant's Full Name",        type: "text",     span: false },
      { key: "applicant_address",  label: "Applicant's Address",          type: "textarea", span: false },
      { key: "fir_number",         label: "FIR Number",                   type: "text",     span: false },
      { key: "police_station",     label: "Police Station",               type: "text",     span: false },
      { key: "offences_alleged",   label: "Offences Alleged (sections)",  type: "text",     span: true,  placeholder: "e.g. BNS s.318, s.61" },
      { key: "brief_facts",        label: "Brief Facts of the Case",      type: "textarea", span: true  },
      { key: "grounds_for_bail",   label: "Grounds for Bail",             type: "textarea", span: true  },
    ],
  },
  {
    id: "regular_bail",
    icon: "lock-open",
    label: "Bail Application",
    sub: "Section 480 BNSS / 437 CrPC",
    fields: [
      { key: "court_name",         label: "Court Name",                   type: "text",     span: true  },
      { key: "applicant_name",     label: "Accused's Full Name",          type: "text",     span: false },
      { key: "applicant_address",  label: "Accused's Address",            type: "textarea", span: false },
      { key: "case_number",        label: "Case / FIR Number",            type: "text",     span: false },
      { key: "police_station",     label: "Police Station",               type: "text",     span: false },
      { key: "date_of_arrest",     label: "Date of Arrest",               type: "date",     span: false },
      { key: "days_in_custody",    label: "Days in Custody",              type: "text",     span: false, placeholder: "e.g. 14" },
      { key: "offences_alleged",   label: "Offences Charged (sections)",  type: "text",     span: true  },
      { key: "brief_facts",        label: "Brief Facts",                  type: "textarea", span: true  },
      { key: "grounds_for_bail",   label: "Grounds for Bail",             type: "textarea", span: true  },
    ],
  },
  {
    id: "affidavit",
    icon: "pen-line",
    label: "Affidavit",
    sub: "Sworn Statement",
    fields: [
      { key: "deponent_name",       label: "Deponent's Full Name",     type: "text",     span: false },
      { key: "deponent_age",        label: "Age",                      type: "text",     span: false, placeholder: "e.g. 35" },
      { key: "deponent_address",    label: "Deponent's Address",       type: "textarea", span: false },
      { key: "deponent_occupation", label: "Occupation",               type: "text",     span: false },
      { key: "purpose_of_affidavit",label: "Purpose of Affidavit",    type: "text",     span: true,  placeholder: "e.g. For submission to District Collector regarding land records" },
      { key: "facts_to_state",      label: "Facts to Depose",         type: "textarea", span: true  },
      { key: "place_of_swearing",   label: "Place of Swearing",       type: "text",     span: false, placeholder: "e.g. Mumbai" },
    ],
  },
  {
    id: "rti_application",
    icon: "search",
    label: "RTI Application",
    sub: "RTI Act, 2005",
    fields: [
      { key: "applicant_name",    label: "Applicant's Full Name",        type: "text",     span: false },
      { key: "applicant_address", label: "Applicant's Address",          type: "textarea", span: false },
      { key: "applicant_contact", label: "Phone / Email",                type: "text",     span: false },
      { key: "public_authority",  label: "Public Authority / Department",type: "text",     span: false },
      { key: "pio_designation",   label: "PIO's Designation",           type: "text",     span: false, placeholder: "e.g. Public Information Officer, Municipal Corporation" },
      { key: "information_sought",label: "Information Sought",           type: "textarea", span: true  },
      { key: "period_of_information", label: "Period of Information",    type: "text",     span: false, placeholder: "e.g. April 2022 – March 2024" },
      { key: "purpose",           label: "Purpose / Context",            type: "textarea", span: true  },
    ],
  },
  {
    id: "consumer_complaint",
    icon: "shopping-cart",
    label: "Consumer Complaint",
    sub: "Consumer Protection Act, 2019",
    fields: [
      { key: "forum",                label: "Forum",                      type: "select",   span: true,
        options: ["District Consumer Disputes Redressal Commission", "State Consumer Disputes Redressal Commission", "National Consumer Disputes Redressal Commission (NCDRC)"] },
      { key: "complainant_name",     label: "Complainant's Name",         type: "text",     span: false },
      { key: "complainant_address",  label: "Complainant's Address",      type: "textarea", span: false },
      { key: "opposite_party_name",  label: "Opposite Party (Brand/Company)", type: "text", span: false },
      { key: "opposite_party_address", label: "Opposite Party's Address", type: "textarea", span: false },
      { key: "product_or_service",   label: "Product / Service",          type: "text",     span: false },
      { key: "date_of_purchase",     label: "Date of Purchase / Transaction", type: "date", span: false },
      { key: "amount_paid",          label: "Amount Paid (₹)",            type: "text",     span: false },
      { key: "deficiency_or_defect", label: "Deficiency of Service / Defect in Goods", type: "textarea", span: true },
      { key: "relief_sought",        label: "Relief Sought",              type: "textarea", span: true  },
    ],
  },
  {
    id: "vakalatnama",
    icon: "clipboard-list",
    label: "Vakalatnama",
    sub: "Memo of Appearance",
    fields: [
      { key: "court_name",          label: "Court Name",               type: "text",     span: true  },
      { key: "case_title",          label: "Case Title",               type: "text",     span: true,  placeholder: "e.g. Ramesh Kumar v. State of Maharashtra" },
      { key: "case_number",         label: "Case / Suit Number",       type: "text",     span: false },
      { key: "client_name",         label: "Client's Full Name",       type: "text",     span: false },
      { key: "client_address",      label: "Client's Address",         type: "textarea", span: false },
      { key: "party_capacity",      label: "Party Capacity",           type: "select",   span: false,
        options: ["Petitioner", "Respondent", "Plaintiff", "Defendant", "Appellant", "Applicant", "Complainant", "Accused"] },
      { key: "advocate_name",       label: "Advocate's Full Name",     type: "text",     span: false },
      { key: "advocate_enrollment", label: "Enrollment Number",        type: "text",     span: false },
      { key: "bar_council",         label: "Bar Council",              type: "text",     span: false, placeholder: "e.g. Bar Council of Maharashtra & Goa" },
    ],
  },
  {
    id: "writ_petition",
    icon: "landmark",
    label: "Writ Petition",
    sub: "Article 226 / 32",
    fields: [
      { key: "court_name",           label: "Court Name",                  type: "text",     span: true,  placeholder: "e.g. High Court of Delhi" },
      { key: "petitioner_name",      label: "Petitioner's Full Name",      type: "text",     span: false },
      { key: "petitioner_address",   label: "Petitioner's Address",        type: "textarea", span: false },
      { key: "respondent_authority", label: "Respondent Authority / State",type: "text",     span: true  },
      { key: "rights_violated",      label: "Rights / Provisions Violated",type: "text",     span: true,  placeholder: "e.g. Article 21 (right to shelter)" },
      { key: "brief_facts",          label: "Brief Facts",                 type: "textarea", span: true  },
      { key: "relief_sought",        label: "Relief Sought",               type: "textarea", span: true  },
    ],
  },
  {
    id: "divorce_petition",
    icon: "heart-crack",
    label: "Divorce Petition",
    sub: "Matrimonial",
    fields: [
      { key: "court_name",         label: "Court Name",           type: "text",     span: true,  placeholder: "e.g. Family Court, Bandra" },
      { key: "applicable_law",     label: "Applicable Law",       type: "text",     span: true,  placeholder: "e.g. Section 13, Hindu Marriage Act 1955" },
      { key: "petitioner_name",    label: "Petitioner's Full Name", type: "text",   span: false },
      { key: "respondent_name",    label: "Respondent's Full Name", type: "text",   span: false },
      { key: "marriage_date",      label: "Date of Marriage",     type: "date",     span: false },
      { key: "place_of_marriage",  label: "Place of Marriage",    type: "text",     span: false },
      { key: "ground_for_divorce", label: "Ground for Divorce",   type: "text",     span: true,  placeholder: "e.g. cruelty / desertion / mutual consent" },
      { key: "brief_facts",        label: "Brief Facts",          type: "textarea", span: true  },
      { key: "relief_sought",      label: "Relief Sought",        type: "textarea", span: true  },
    ],
  },
];

// ── State ──────────────────────────────────────────────────────────────────
let selectedDocType = null;
let isGenerating    = false;
let generatedText   = "";

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initNav();
  renderDocTypeGrid();
  loadMatters();
});

// ── Render document type cards ─────────────────────────────────────────────
function renderDocTypeGrid() {
  const grid = document.getElementById("doc-type-grid");
  grid.innerHTML = DOC_TYPES.map(dt => `
    <div class="doc-type-card" id="dtc-${dt.id}" onclick="selectDocType('${dt.id}')">
      <div class="dtc-icon"><svg class="lc" aria-hidden="true"><use href="/static/lucide.svg#lc-${dt.icon}"/></svg></div>
      <div class="dtc-label">${dt.label}</div>
      <div class="dtc-sub">${dt.sub}</div>
    </div>
  `).join("");
}

// ── Select document type ───────────────────────────────────────────────────
function selectDocType(id) {
  selectedDocType = DOC_TYPES.find(d => d.id === id);
  if (!selectedDocType) return;

  // Update card selection state
  document.querySelectorAll(".doc-type-card").forEach(c => c.classList.remove("selected"));
  document.getElementById(`dtc-${id}`).classList.add("selected");

  // Update form title
  document.getElementById("form-title").textContent = selectedDocType.label;

  // Build fields
  buildFormFields(selectedDocType.fields);
  applyMatterPrefill();   // pre-fill from the selected matter, if any

  // Show form, hide output
  document.getElementById("draft-form").classList.add("visible");
  document.getElementById("draft-output").classList.remove("visible");
  document.getElementById("gen-indicator").classList.remove("visible");
  document.getElementById("output-body").textContent = "";
  generatedText = "";

  // Check if form is valid
  validateForm();

  // Scroll to form
  document.getElementById("draft-form").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── Build form fields dynamically ─────────────────────────────────────────
function buildFormFields(fields) {
  const container = document.getElementById("form-fields");
  container.innerHTML = fields.map(f => {
    const cls = `form-group${f.span ? " span-2" : ""}`;
    const label = f.label.replace(/_/g, " ");
    let input = "";

    if (f.type === "textarea") {
      input = `<textarea id="ff-${f.key}" name="${f.key}" placeholder="${f.placeholder || label}" oninput="validateForm()" rows="3"></textarea>`;
    } else if (f.type === "select") {
      const opts = f.options.map(o => `<option value="${o}">${o}</option>`).join("");
      input = `<select id="ff-${f.key}" name="${f.key}" onchange="validateForm()"><option value="">— Select —</option>${opts}</select>`;
    } else {
      input = `<input type="${f.type}" id="ff-${f.key}" name="${f.key}" placeholder="${f.placeholder || label}" oninput="validateForm()"/>`;
    }

    return `<div class="${cls}"><label class="form-label" for="ff-${f.key}">${f.label}</label>${input}</div>`;
  }).join("");
}

// ── Validate form (enable/disable generate button) ─────────────────────────
function validateForm() {
  if (!selectedDocType) return;
  const allFilled = selectedDocType.fields.every(f => {
    const el = document.getElementById(`ff-${f.key}`);
    return el && el.value.trim().length > 0;
  });
  document.getElementById("generate-btn").disabled = !allFilled || isGenerating;
}

// ── Collect form data ──────────────────────────────────────────────────────
function collectFields() {
  const data = {};
  selectedDocType.fields.forEach(f => {
    const el = document.getElementById(`ff-${f.key}`);
    data[f.key] = el ? el.value.trim() : "";
  });
  return data;
}

// ── Generate document (SSE streaming) ─────────────────────────────────────
async function generateDocument() {
  if (!selectedDocType || isGenerating) return;

  const fields = collectFields();
  const hasEmpty = Object.values(fields).some(v => !v);
  if (hasEmpty) { showToast("Please fill in all fields."); return; }

  isGenerating = true;
  generatedText = "";
  document.getElementById("generate-btn").disabled = true;
  document.getElementById("generate-btn").textContent = "Generating…";

  // Show output area
  const outputEl = document.getElementById("draft-output");
  const bodyEl   = document.getElementById("output-body");
  const genInd   = document.getElementById("gen-indicator");

  outputEl.classList.add("visible");
  bodyEl.textContent = "";
  bodyEl.style.display = "";
  _editorEl().style.display = "none";
  document.getElementById("edit-toolbar").style.display = "none";
  document.getElementById("btn-edit").style.display = "none";
  genInd.classList.add("visible");
  const oldChip = document.getElementById("format-chip");
  if (oldChip) oldChip.remove();
  document.getElementById("output-title").textContent = selectedDocType.label;
  document.getElementById("output-badge").textContent = "Generating…";

  outputEl.scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const res = await apiFetch("/api/drafting/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_type: selectedDocType.id, fields }),
    });

    if (!res.ok) {
      bodyEl.textContent = "Error: Could not reach the server.";
      genInd.classList.remove("visible");
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";
    let   started = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const payload = JSON.parse(line.slice(6));

          if (payload.format_used) {
            // Show which authentic drafting skeleton guided this draft
            const chip = document.createElement("div");
            chip.id = "format-chip";
            chip.className = "format-chip";
            chip.textContent = "Format: " + payload.format_used;
            const badge = document.getElementById("output-badge");
            badge.parentElement.insertBefore(chip, badge);
          }

          if (payload.content) {
            if (!started) {
              genInd.classList.remove("visible");
              started = true;
            }
            generatedText += payload.content;
            bodyEl.innerHTML = escHtml(generatedText) + `<span class="out-cursor">▋</span>`;
            bodyEl.scrollTop = bodyEl.scrollHeight;
          }

          if (payload.error) {
            bodyEl.textContent = `Error: ${payload.error}`;
            genInd.classList.remove("visible");
          }

          if (payload.done) {
            bodyEl.textContent = generatedText;
            if (generatedText.trim()) document.getElementById("btn-edit").style.display = "";
            document.getElementById("output-badge").textContent = "Ready";
            genInd.classList.remove("visible");
            loadDraftRefs(fields);   // AI references panel (retrieved, never generated)
          }
        } catch (_) {}
      }
    }
  } catch (err) {
    bodyEl.textContent = "Connection error. Please try again.";
    genInd.classList.remove("visible");
  } finally {
    isGenerating = false;
    document.getElementById("generate-btn").disabled = false;
    document.getElementById("generate-btn").textContent = "✦ Generate Document";
    // Remove cursor
    const cur = bodyEl.querySelector(".out-cursor");
    if (cur) cur.remove();
    validateForm();
  }
}

// ── AI references panel (right pane) ───────────────────────────────────────
// Shows RETRIEVED material only: verified provisions from the corpus + live
// judgments with Kanoon links. Nothing here is generated — it is looked up.
async function loadDraftRefs(fields) {
  const provEl = document.getElementById("dw-provisions");
  const caseEl = document.getElementById("dw-cases");
  if (!provEl || !caseEl || !selectedDocType) return;
  // Build a compact retrieval query from the template + the most telling fields
  const fieldText = Object.values(fields || {}).filter(Boolean).join(" ").slice(0, 120);
  const q = `${selectedDocType.label} ${fieldText}`.trim().slice(0, 160);
  provEl.innerHTML = caseEl.innerHTML = '<div class="dw-empty">Looking up…</div>';
  try {
    const r = await apiFetch(`/api/research/provisions?q=${encodeURIComponent(q)}`);
    const provisions = r.ok ? await r.json() : [];
    provEl.innerHTML = provisions.length
      ? provisions.slice(0, 5).map(p => `
          <div class="dw-ref">
            <b>${escHtml(p.act)}${p.year ? ` (${escHtml(p.year)})` : ""} · s.${escHtml(p.section)}</b>
            <small>${escHtml(p.title)}</small>
            ${p.url ? ` <a href="${escHtml(p.url)}" target="_blank" rel="noopener">source ↗</a>` : ""}
          </div>`).join("")
      : '<div class="dw-empty">No matching provisions found in the verified corpus.</div>';
  } catch (_) {
    provEl.innerHTML = '<div class="dw-empty">Provisions unavailable.</div>';
  }
  try {
    const r = await apiFetch(`/api/research/cases?q=${encodeURIComponent(q)}`);
    const cases = r.ok ? await r.json() : [];
    caseEl.innerHTML = cases.length
      ? cases.slice(0, 4).map(c => `
          <div class="dw-ref">
            <b>${escHtml(c.title || "")}</b>
            <small>${escHtml([c.court, c.date].filter(Boolean).join(" · "))}</small>
            ${c.url ? ` <a href="${escHtml(c.url)}" target="_blank" rel="noopener">Kanoon ↗</a>` : ""}
          </div>`).join("") +
        '<div class="dw-empty" style="margin-top:.4rem;">Good-law status unverified — confirm before relying.</div>'
      : '<div class="dw-empty">No related judgments found.</div>';
  } catch (_) {
    caseEl.innerHTML = '<div class="dw-empty">Case references unavailable.</div>';
  }
}

// ── Copy document ──────────────────────────────────────────────────────────
function copyDocument() {
  if (!generatedText) { showToast("Nothing to copy yet."); return; }
  navigator.clipboard.writeText(generatedText).then(() => {
    showToast("Document copied to clipboard.");
  });
}

// ── Download as .txt ───────────────────────────────────────────────────────
function downloadDocument() {
  if (!generatedText) { showToast("Nothing to download yet."); return; }
  const filename = (selectedDocType?.label || "document").replace(/\s+/g, "_").toLowerCase() + ".txt";
  const blob = new Blob([generatedText], { type: "text/plain;charset=utf-8" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ── Save the generated draft for advocate review ───────────────────────────
async function saveForReview() {
  if (!generatedText) { showToast("Generate a document first."); return; }
  const btn = document.getElementById("btn-save");
  const orig = btn ? btn.textContent : "";
  if (btn) { btn.textContent = "Saving…"; btn.disabled = true; }
  try {
    const res = await apiFetch("/api/drafts/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_type: selectedDocType?.id || "document",
        title: selectedDocType?.label || "Draft",
        case_id: selectedMatter ? selectedMatter.id : null,
        content: generatedText,
      }),
    });
    if (res.status === 403) { showToast("Your role cannot save drafts."); return; }
    if (!res.ok) { showToast("Could not save draft."); return; }
    showToast("Saved for advocate review. See Drafts.");
  } catch (_) {
    showToast("Save error. Please try again.");
  } finally {
    if (btn) { btn.textContent = orig; btn.disabled = false; }
  }
}

// ── Export as PDF / DOCX (server-rendered) ─────────────────────────────────
async function exportDocument(format) {
  if (!generatedText) { showToast("Generate a document first."); return; }
  const btn = document.getElementById(format === "pdf" ? "btn-pdf" : "btn-docx");
  const orig = btn ? btn.textContent : "";
  if (btn) { btn.textContent = "Exporting…"; btn.disabled = true; }
  try {
    const res = await apiFetch("/api/drafting/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_type: selectedDocType?.id || "document",
        content: generatedText,
        format,
      }),
    });
    if (!res.ok) {
      const msg = await res.text();
      showToast("Export failed: " + msg.slice(0, 80));
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^"]+)"?/);
    const filename = m ? m[1]
      : (selectedDocType?.label || "document").replace(/\s+/g, "_").toLowerCase() + "." + format;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
    showToast(format.toUpperCase() + " downloaded.");
  } catch (err) {
    showToast("Export error. Please try again.");
  } finally {
    if (btn) { btn.textContent = orig; btn.disabled = false; }
  }
}

// ── Open in AI Chat ────────────────────────────────────────────────────────
function sendToChat() {
  if (!generatedText) { showToast("Generate a document first."); return; }
  const truncated = generatedText.length > 3000 ? generatedText.slice(0, 3000) + "…" : generatedText;
  const prompt = encodeURIComponent(`Review and improve this drafted ${selectedDocType?.label || "document"}:\n\n${truncated}`);
  window.location.href = `/assistant?draft=${prompt}`;
}

// ── Helpers ────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

if (typeof apiFetch === "undefined") {
  window.apiFetch = async (url, opts = {}) => {
    const token = localStorage.getItem("access_token");
    opts.headers = { ...(opts.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };
    const res = await fetch(url, opts);
    if (res.status === 401) {          // session expired -> clean sign-out, no dead UI
      localStorage.removeItem("access_token");
      localStorage.removeItem("current_user");
      window.location.href = "/login";
    }
    return res;
  };
}
