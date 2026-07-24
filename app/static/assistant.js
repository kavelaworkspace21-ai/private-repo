/* ── Juriscite — Universal Legal Agent Frontend ── */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let currentConvId  = null;
let isStreaming     = false;
let allConversations = [];

// Language code → display name
const LANG_NAMES = {
  hi: "Hindi", bn: "Bengali", te: "Telugu", mr: "Marathi",
  ta: "Tamil",  ur: "Urdu",   gu: "Gujarati", kn: "Kannada",
  ml: "Malayalam", or: "Odia", pa: "Punjabi", as: "Assamese",
  mai: "Maithili", sa: "Sanskrit", brx: "Bodo", sat: "Santali",
  doi: "Dogri", kok: "Konkani", mni: "Manipuri", ne: "Nepali",
  sd: "Sindhi", ks: "Kashmiri", en: "English",
};

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initNav();
  loadConversations();

  // Handle ?draft= param from Drafting Engine "Open in Chat" button
  const params = new URLSearchParams(window.location.search);
  const draftParam = params.get("draft");
  if (draftParam) {
    const decoded = decodeURIComponent(draftParam);
    const inp = document.getElementById("chat-input");
    inp.value = decoded;
    autoResize(inp);
    document.getElementById("send-btn").disabled = false;
    // Clear param from URL without reload
    window.history.replaceState({}, "", "/assistant");
    // Auto-send after brief delay so page finishes loading
    setTimeout(sendMessage, 600);
  }

  // Mobile: show sidebar toggle in header
  if (window.innerWidth <= 768) {
    document.getElementById("mob-sidebar-btn").style.display = "flex";
  }
});

// ── Mobile sidebar ─────────────────────────────────────────────────────────────
function toggleSidebar() {
  document.getElementById("ai-sidebar").classList.toggle("open");
}

// Close sidebar when clicking main area on mobile
document.addEventListener("click", (e) => {
  if (window.innerWidth > 768) return;
  const sidebar = document.getElementById("ai-sidebar");
  if (sidebar.classList.contains("open") &&
      !sidebar.contains(e.target) &&
      !e.target.closest(".sidebar-toggle-btn") &&
      !e.target.closest("#mob-sidebar-btn")) {
    sidebar.classList.remove("open");
  }
});

// ── Textarea auto-resize ───────────────────────────────────────────────────────
function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
}

// ── Input change handler ───────────────────────────────────────────────────────
function onInputChange(el) {
  autoResize(el);
  const val = el.value;
  document.getElementById("send-btn").disabled = !val.trim() || isStreaming;

  // Char count
  const cc = document.getElementById("char-count");
  cc.textContent = val.length > 300 ? `${val.length} chars` : "";

  // Live language detection
  const lang = detectLang(val);
  const ld   = document.getElementById("lang-detected");
  const lb   = document.getElementById("lang-badge");
  if (lang && lang !== "en" && val.length > 6) {
    const name = LANG_NAMES[lang] || lang;
    ld.textContent = name;
    ld.classList.add("visible");
    lb.textContent = name.toUpperCase().slice(0, 4);
  } else {
    ld.classList.remove("visible");
    lb.textContent = "EN";
  }
}

// ── Keyboard handler ──────────────────────────────────────────────────────────
function handleKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!document.getElementById("send-btn").disabled) sendMessage();
  }
}

// ── Quick prompts ─────────────────────────────────────────────────────────────
function sendQuick(text) {
  const inp = document.getElementById("chat-input");
  inp.value = text;
  autoResize(inp);
  document.getElementById("send-btn").disabled = false;
  sendMessage();
}

// ── New chat ──────────────────────────────────────────────────────────────────
function newChat() {
  currentConvId = null;
  document.getElementById("chat-title").textContent = "Universal Legal Agent";
  document.getElementById("lang-badge").textContent = "EN";
  document.getElementById("lang-detected").classList.remove("visible");

  const area = document.getElementById("messages-area");
  area.innerHTML = "";
  area.appendChild(buildWelcome());

  document.querySelectorAll(".conv-item").forEach(el => el.classList.remove("active"));
  document.getElementById("chat-input").focus();
  if (window.innerWidth <= 768) document.getElementById("ai-sidebar").classList.remove("open");
}

// ── Load conversations ────────────────────────────────────────────────────────
async function loadConversations() {
  try {
    const res = await apiFetch("/api/ai/conversations");
    if (!res.ok) return;
    allConversations = await res.json();
    renderConvList(allConversations);
  } catch (_) {}
}

function renderConvList(convs) {
  const list = document.getElementById("conv-list");
  if (!convs.length) {
    list.innerHTML = `<div class="conv-empty">No conversations yet.<br/>Start by asking a legal question below.</div>`;
    return;
  }
  list.innerHTML = convs.map(c => {
    const date = formatRelDate(c.updated_at || c.created_at);
    const active = c.id === currentConvId ? " active" : "";
    return `
      <div class="conv-item${active}" id="conv-${c.id}" onclick="openConversation(${c.id})">
        <div class="conv-icon">&#x1F4AC;</div>
        <div class="conv-body">
          <div class="conv-title">${escHtml(c.title)}</div>
          <div class="conv-date">${date}</div>
        </div>
        <button class="conv-del" onclick="deleteConv(event,${c.id})" title="Delete">&#x2715;</button>
      </div>`;
  }).join("");
}

// Search filter
function filterConversations(query) {
  const q = query.toLowerCase().trim();
  const filtered = q ? allConversations.filter(c => c.title.toLowerCase().includes(q)) : allConversations;
  renderConvList(filtered);
}

// ── Open existing conversation ─────────────────────────────────────────────────
async function openConversation(id) {
  if (isStreaming) return;
  currentConvId = id;
  document.getElementById("ai-sidebar").classList.remove("open");
  document.querySelectorAll(".conv-item").forEach(el => el.classList.remove("active"));
  const item = document.getElementById(`conv-${id}`);
  if (item) item.classList.add("active");

  try {
    const res = await apiFetch(`/api/ai/conversations/${id}`);
    if (!res.ok) { showToast("Could not load conversation"); return; }
    const conv = await res.json();

    document.getElementById("chat-title").textContent = conv.title;

    const area = document.getElementById("messages-area");
    area.innerHTML = "";
    conv.messages.forEach(m => area.appendChild(buildMsgEl(m.role, m.content)));
    scrollBottom();
  } catch (_) { showToast("Error loading conversation"); }
}

// ── Delete conversation ────────────────────────────────────────────────────────
async function deleteConv(e, id) {
  e.stopPropagation();
  if (!confirm("Delete this conversation?")) return;
  try {
    await apiFetch(`/api/ai/conversations/${id}`, { method: "DELETE" });
    if (currentConvId === id) newChat();
    await loadConversations();
  } catch (_) { showToast("Error deleting conversation"); }
}

// ── Send message ──────────────────────────────────────────────────────────────
async function sendMessage() {
  if (isStreaming) return;
  const inp  = document.getElementById("chat-input");
  const text = inp.value.trim();
  if (!text) return;

  // Clear input
  inp.value = "";
  autoResize(inp);
  document.getElementById("send-btn").disabled = true;
  document.getElementById("lang-detected").classList.remove("visible");

  const area = document.getElementById("messages-area");
  // Remove welcome screen
  const welcome = area.querySelector(".welcome");
  if (welcome) welcome.remove();

  // User bubble
  area.appendChild(buildMsgEl("user", text));
  scrollBottom();

  // Thinking indicator
  const thinkEl = buildThinking();
  area.appendChild(thinkEl);
  scrollBottom();

  // Update header badge
  setStreamingBadge(true);
  isStreaming = true;

  let aiBubble   = null;
  let aiMsgEl    = null;
  let accText    = "";
  let convIdSent = false;
  let confBadge  = null;   // confidence pill; synced to the model's own stated label
  let isDraftMsg = false;  // chat drafting mode (draft_status event received)
  let draftLabel = null;   // matched format label, if any
  const stripConfidence = (s) =>
    s.replace(/^\s*Confidence:\s*(HIGH|MEDIUM|LOW)\b[^\n]*\r?\n+/i, "");

  try {
    const res = await apiFetch("/api/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, conversation_id: currentConvId }),
    });

    if (!res.ok) {
      thinkEl.remove();
      area.appendChild(buildMsgEl("ai", "**Connection error.** Could not reach the server. Please try again."));
      scrollBottom();
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

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

          // First event: conversation ID
          if (payload.conversation_id && !convIdSent) {
            currentConvId = payload.conversation_id;
            convIdSent = true;
          }

          // Chat drafting mode: review-status badge + format chip above the document
          if (payload.draft_status || payload.format_used) {
            if (!aiBubble) {
              thinkEl.remove();
              aiMsgEl  = buildMsgEl("ai", "");
              aiBubble = aiMsgEl.querySelector(".msg-bubble");
              area.appendChild(aiMsgEl);
            }
            if (payload.draft_status) {
              isDraftMsg = true;
              const b = document.createElement("div");
              b.className = "confidence-badge";
              b.style.cssText =
                "display:inline-flex;align-items:center;gap:.35rem;font-size:.66rem;" +
                "font-weight:700;letter-spacing:.04em;padding:.15rem .5rem;border-radius:20px;" +
                "margin-bottom:.5rem;margin-right:.4rem;color:#F59E0B;background:rgba(245,158,11,.12)";
              b.textContent = "DRAFT — FOR ADVOCATE REVIEW";
              aiBubble.parentElement.insertBefore(b, aiBubble);
            }
            if (payload.format_used) {
              draftLabel = payload.format_used;
              const chip = document.createElement("div");
              chip.className = "format-chip";
              chip.style.marginBottom = ".5rem";
              chip.style.display = "inline-block";
              chip.textContent = "Format: " + payload.format_used;
              aiBubble.parentElement.insertBefore(chip, aiBubble);
            }
          }

          // Confidence label (safety doctrine 2.5) — show a badge above the answer
          if (payload.confidence) {
            if (!aiBubble) {
              thinkEl.remove();
              aiMsgEl  = buildMsgEl("ai", "");
              aiBubble = aiMsgEl.querySelector(".msg-bubble");
              area.appendChild(aiMsgEl);
            }
            const c = String(payload.confidence).toUpperCase();
            const colors = { HIGH: "#10B981", MEDIUM: "#F59E0B", LOW: "#DC4C64" };
            const badge = document.createElement("div");
            badge.className = "confidence-badge";
            badge.style.cssText =
              `display:inline-flex;align-items:center;gap:.35rem;font-size:.66rem;` +
              `font-weight:700;letter-spacing:.04em;padding:.15rem .5rem;border-radius:20px;` +
              `margin-bottom:.5rem;color:${colors[c]||"#6b7280"};` +
              `background:${(colors[c]||"#6b7280")}1a`;
            badge.textContent = `CONFIDENCE: ${c}`;
            aiBubble.parentElement.insertBefore(badge, aiBubble);
            confBadge = badge;
          }

          // Content delta
          if (payload.content) {
            if (!aiBubble) {
              thinkEl.remove();
              aiMsgEl  = buildMsgEl("ai", "");
              aiBubble = aiMsgEl.querySelector(".msg-bubble");
              area.appendChild(aiMsgEl);
            }
            accText += payload.content;
            // Sync the badge to the model's own "Confidence: X" line, then hide that
            // duplicate line from the prose so there is one consistent indicator.
            const cm = accText.match(/^\s*Confidence:\s*(HIGH|MEDIUM|LOW)\b/i);
            if (cm && confBadge) {
              const mc = cm[1].toUpperCase();
              const cc = { HIGH: "#10B981", MEDIUM: "#F59E0B", LOW: "#DC4C64" }[mc] || "#6b7280";
              confBadge.textContent = `CONFIDENCE: ${mc}`;
              confBadge.style.color = cc;
              confBadge.style.background = cc + "1a";
            }
            aiBubble.innerHTML = renderMarkdown(stripConfidence(accText)) + `<span class="cursor">&#x258C;</span>`;
            scrollBottom();
          }

          // Error
          if (payload.error) {
            thinkEl.remove();
            if (!aiBubble) {
              area.appendChild(buildMsgEl("ai", `**Error:** ${escHtml(payload.error)}`));
            } else {
              aiBubble.innerHTML = renderMarkdown(stripConfidence(accText) + `\n\n*Error: ${payload.error}*`);
            }
            scrollBottom();
          }

          // Done
          if (payload.done) {
            if (aiBubble && accText) {
              // Final render: markdown + citation highlighting
              const finalText = stripConfidence(accText);
              aiBubble.innerHTML = highlightCitations(renderMarkdown(finalText));
              // Attach action buttons
              attachMsgActions(aiMsgEl, finalText);
              // Chat-drafted document → same review/export loop as the Drafting Engine
              const draftProse = finalText.split(/\n+---\n+### 📚 Sources consulted/)[0].trim();
              if (isDraftMsg && draftProse.length > 400 && !/hit a problem/.test(draftProse)) {
                attachDraftActions(aiMsgEl, draftProse, draftLabel);
              }
              // Related judgments (live, verifiable) — non-blocking
              appendCaseLaw(aiMsgEl, text);
            }
            // Refresh sidebar
            await loadConversations();
            // Mark active
            if (currentConvId) {
              document.querySelectorAll(".conv-item").forEach(el => el.classList.remove("active"));
              const ci = document.getElementById(`conv-${currentConvId}`);
              if (ci) {
                ci.classList.add("active");
                document.getElementById("chat-title").textContent =
                  ci.querySelector(".conv-title")?.textContent || "Conversation";
              }
            }
            scrollBottom();
            break;
          }
        } catch (_) {}
      }
    }
  } catch (err) {
    thinkEl.remove();
    if (!aiBubble) area.appendChild(buildMsgEl("ai", "**Network error.** Please check your connection and try again."));
  } finally {
    isStreaming = false;
    setStreamingBadge(false);
    document.getElementById("send-btn").disabled = false;
    inp.focus();
    // Remove blinking cursor
    if (aiBubble) { const cur = aiBubble.querySelector(".cursor"); if (cur) cur.remove(); }
  }
}

// ── DOM builders ───────────────────────────────────────────────────────────────
function buildMsgEl(role, content) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role === "user" ? "user" : "ai"}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "Y" : "⚖";

  const right = document.createElement("div");
  right.className = "msg-right";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (role === "user") {
    bubble.textContent = content;
  } else {
    bubble.innerHTML = content ? highlightCitations(renderMarkdown(content)) : "";
  }

  right.appendChild(bubble);

  // Action buttons for AI messages with content
  if (role === "ai" && content) {
    attachMsgActions(wrap, content, right);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(right);
  return wrap;
}

/* ── Chat-drafted documents: Save for review + DOCX/PDF export ── */
let _draftCases = null;   // lazy cache of the advocate's matters (for linking)
async function _loadDraftCases() {
  if (_draftCases !== null) return _draftCases;
  try {
    const r = await apiFetch("/api/cases/");
    _draftCases = r.ok ? await r.json() : [];
  } catch (_) { _draftCases = []; }
  return _draftCases;
}

function attachDraftActions(msgEl, prose, formatLabel) {
  const bubble = msgEl.querySelector(".msg-bubble");
  if (!bubble || msgEl.querySelector(".draft-actions")) return;
  const bar = document.createElement("div");
  bar.className = "draft-actions";
  bar.style.cssText = "display:flex;gap:.45rem;margin-top:.55rem;flex-wrap:wrap;align-items:center;";

  // Optional matter link — the saved draft attaches to the chosen case
  const caseSel = document.createElement("select");
  caseSel.style.cssText = "background:var(--surface-2);border:1px solid var(--border);" +
    "border-radius:7px;color:var(--text-3);font-family:inherit;font-size:.72rem;" +
    "padding:.3rem .45rem;max-width:180px;";
  caseSel.innerHTML = '<option value="">No matter (unlinked)</option>';
  _loadDraftCases().then(cs => cs.forEach(c => {
    const o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.title.length > 26 ? c.title.slice(0, 25) + "…" : c.title;
    caseSel.appendChild(o);
  }));
  bar.appendChild(caseSel);
  const mk = (label, fn) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.style.cssText = "background:var(--surface-2);border:1px solid var(--border);" +
      "border-radius:7px;color:var(--text-2);font-family:inherit;font-size:.72rem;" +
      "font-weight:600;padding:.32rem .7rem;cursor:pointer;";
    b.onmouseenter = () => { b.style.borderColor = "var(--gold-border)"; };
    b.onmouseleave = () => { b.style.borderColor = "var(--border)"; };
    b.onclick = () => fn(b);
    return b;
  };
  const title = (formatLabel || "Chat draft") + " — " + new Date().toLocaleDateString("en-IN");

  bar.appendChild(mk("💾 Save for review", async (b) => {
    b.disabled = true; b.textContent = "Saving…";
    try {
      const r = await apiFetch("/api/drafts/", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_type: "chat_draft", title: title, content: prose,
                               case_id: caseSel.value ? parseInt(caseSel.value, 10) : null }),
      });
      if (r.ok) { b.textContent = "✓ Saved — see Drafts"; toast("Draft saved for advocate review."); }
      else { b.textContent = "Save failed"; b.disabled = false; toast("Could not save draft.", "error"); }
    } catch (_) { b.textContent = "Save failed"; b.disabled = false; }
  }));

  const exporter = (fmt) => async (b) => {
    b.disabled = true; const orig = b.textContent; b.textContent = "Exporting…";
    try {
      const r = await apiFetch("/api/drafting/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_type: "chat_draft", content: prose, format: fmt }),
      });
      if (!r.ok) throw new Error();
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "juriscite_draft." + fmt;
      a.click(); URL.revokeObjectURL(a.href);
      b.textContent = orig; b.disabled = false;
    } catch (_) { b.textContent = "Export failed"; b.disabled = false; }
  };
  bar.appendChild(mk("Word (.docx)", exporter("docx")));
  bar.appendChild(mk("PDF", exporter("pdf")));

  bubble.parentElement.insertBefore(bar, bubble.nextSibling);
}

function attachMsgActions(msgEl, rawText, rightEl) {
  // Remove existing actions if any
  const existing = (rightEl || msgEl.querySelector(".msg-right"))?.querySelector(".msg-actions");
  if (existing) existing.remove();

  const target = rightEl || msgEl.querySelector(".msg-right");
  if (!target) return;

  const actions = document.createElement("div");
  actions.className = "msg-actions";

  // Copy
  const copyBtn = document.createElement("button");
  copyBtn.className = "msg-btn";
  copyBtn.textContent = "Copy";
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(rawText).then(() => {
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1600);
    });
  };

  // Send to Drafting Engine
  const draftBtn = document.createElement("button");
  draftBtn.className = "msg-btn gold";
  draftBtn.textContent = "Draft ↗";
  draftBtn.title = "Open in Drafting Engine";
  draftBtn.onclick = () => {
    const snippet = rawText.length > 2000 ? rawText.slice(0, 2000) + "..." : rawText;
    window.location.href = "/drafting";
  };

  // Download as text
  const dlBtn = document.createElement("button");
  dlBtn.className = "msg-btn";
  dlBtn.textContent = "Save .txt";
  dlBtn.onclick = () => {
    const blob = new Blob([rawText], { type: "text/plain;charset=utf-8" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = "legalserver_ai_response.txt"; a.click();
    URL.revokeObjectURL(url);
  };

  actions.appendChild(copyBtn);
  actions.appendChild(draftBtn);
  actions.appendChild(dlBtn);
  target.appendChild(actions);
}

function buildThinking() {
  const wrap = document.createElement("div");
  wrap.className = "thinking";

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  // Sapphire = "the AI is working" (Midnight Executive AI identity)
  avatar.style.cssText = "background:rgba(59,130,246,.10);border:1px solid rgba(59,130,246,.35);color:#3B82F6;font-size:1rem;";
  avatar.textContent = "⚖";

  const bubble = document.createElement("div");
  bubble.className = "thinking-bubble";
  bubble.innerHTML = `<div class="thinking-dot"></div><div class="thinking-dot"></div><div class="thinking-dot"></div>`;

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  return wrap;
}

function buildWelcome() {
  // Clone the welcome screen HTML (simpler than rebuilding it every time)
  const div = document.createElement("div");
  div.innerHTML = document.getElementById("welcome-screen")?.outerHTML || "";
  const clone = div.firstElementChild;
  if (clone) clone.id = "";
  return clone || div;
}

// ── Citation highlighter ───────────────────────────────────────────────────────
// Wraps "Section X of the [Act Name]" and "s.NNN [Act]" patterns in a gold span
function highlightCitations(html) {
  // Match: Section 138 of the Negotiable Instruments Act / s.138 NI Act / Article 21 of the Constitution
  return html
    .replace(
      /\b(Section\s+[\dA-Z]+[A-Z]?(?:\([a-z\d]+\))?)\s+of\s+(the\s+)?([A-Z][^,.<\n]{4,60?}(?:Act|Code|Sanhita|Adhiniyam|Constitution)(?:\s*,?\s*\d{4})?)/gi,
      (_, sec, the, actName) =>
        `<span class="legal-cite" title="${actName.trim()}">${sec} of ${the || ""}${actName}</span>`
    )
    .replace(
      /\b(Article\s+\d+[A-Z]?(?:\([a-z\d]+\))?)\s+of\s+(the\s+)?(Constitution[^,.<\n]{0,30})/gi,
      (_, art, the, rest) =>
        `<span class="legal-cite" title="Constitution of India">${art} of ${the || ""}${rest}</span>`
    )
    .replace(
      /\b(s\.\s*\d+[A-Z]?(?:\([a-z\d]\))?)\s+((?:BNS|BNSS|BSA|IPC|CrPC|CPC|NI Act|RTI|POCSO|RERA|HMA|HSA|TPA|IT Act|DV Act)[^\s,.<]{0,20})/g,
      (_, s, act) => `<span class="legal-cite" title="${act}">${s} ${act}</span>`
    );
}

// ── Lightweight Markdown renderer ─────────────────────────────────────────────
function renderMarkdown(md) {
  if (!md) return "";

  let h = escHtml(md);

  // Fenced code blocks
  h = h.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) =>
    `<pre><code>${code.trim()}</code></pre>`);
  // Inline code
  h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");

  // Bold + italic
  h = h.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  h = h.replace(/\*\*(.+?)\*\*/g,     "<strong>$1</strong>");
  h = h.replace(/\*([^*\n]+)\*/g,     "<em>$1</em>");

  // Headings
  h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  h = h.replace(/^## (.+)$/gm,  "<h2>$1</h2>");
  h = h.replace(/^# (.+)$/gm,   "<h1>$1</h1>");

  // Horizontal rule
  h = h.replace(/^---+$/gm, "<hr/>");

  // Blockquote
  h = h.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // Tables (simple GFM)
  h = h.replace(/((?:^\|.+\|\n)+)/gm, (tableBlock) => {
    const rows = tableBlock.trim().split("\n").filter(r => !/^\|[-:| ]+\|$/.test(r));
    if (rows.length < 1) return tableBlock;
    const makeRow = (row, tag) =>
      "<tr>" + row.split("|").slice(1, -1).map(c => `<${tag}>${c.trim()}</${tag}>`).join("") + "</tr>";
    const head = makeRow(rows[0], "th");
    const body = rows.slice(1).map(r => makeRow(r, "td")).join("");
    return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  });

  // Unordered lists
  h = h.replace(/((?:^[*\-•] .+\n?)+)/gm, (block) => {
    const items = block.trim().split("\n")
      .map(l => `<li>${l.replace(/^[*\-•] /, "")}</li>`).join("");
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  h = h.replace(/((?:^\d+\. .+\n?)+)/gm, (block) => {
    const items = block.trim().split("\n")
      .map(l => `<li>${l.replace(/^\d+\. /, "")}</li>`).join("");
    return `<ol>${items}</ol>`;
  });

  // Paragraph breaks
  h = h.replace(/\n\n+/g, "<br/><br/>");
  h = h.replace(/\n/g,     "<br/>");

  return h;
}

// ── Language detection (Unicode range scan) ───────────────────────────────────
function detectLang(text) {
  if (!text || text.length < 4) return "en";
  const counts = {};
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp >= 0x0900 && cp <= 0x097F) counts.hi  = (counts.hi  || 0) + 1; // Devanagari
    else if (cp >= 0x0980 && cp <= 0x09FF) counts.bn  = (counts.bn  || 0) + 1; // Bengali
    else if (cp >= 0x0A00 && cp <= 0x0A7F) counts.pa  = (counts.pa  || 0) + 1; // Gurmukhi
    else if (cp >= 0x0A80 && cp <= 0x0AFF) counts.gu  = (counts.gu  || 0) + 1; // Gujarati
    else if (cp >= 0x0B00 && cp <= 0x0B7F) counts.or  = (counts.or  || 0) + 1; // Odia
    else if (cp >= 0x0B80 && cp <= 0x0BFF) counts.ta  = (counts.ta  || 0) + 1; // Tamil
    else if (cp >= 0x0C00 && cp <= 0x0C7F) counts.te  = (counts.te  || 0) + 1; // Telugu
    else if (cp >= 0x0C80 && cp <= 0x0CFF) counts.kn  = (counts.kn  || 0) + 1; // Kannada
    else if (cp >= 0x0D00 && cp <= 0x0D7F) counts.ml  = (counts.ml  || 0) + 1; // Malayalam
    else if (cp >= 0x0600 && cp <= 0x06FF) counts.ur  = (counts.ur  || 0) + 1; // Arabic (Urdu)
    else if (cp >= 0xABC0 && cp <= 0xABFF) counts.mni = (counts.mni || 0) + 1; // Meitei
  }
  const dominant = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return dominant ? dominant[0] : "en";
}

// ── Streaming badge ───────────────────────────────────────────────────────────
function setStreamingBadge(on) {
  const rag = document.getElementById("rag-badge");
  if (on) {
    rag.textContent = "Generating...";
    rag.classList.add("streaming");
    rag.classList.remove("rag");
  } else {
    rag.textContent = "✦ RAG Active";
    rag.classList.remove("streaming");
    rag.classList.add("rag");
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function scrollBottom() {
  const area = document.getElementById("messages-area");
  requestAnimationFrame(() => { area.scrollTop = area.scrollHeight; });
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatRelDate(iso) {
  if (!iso) return "";
  const d   = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60)     return "just now";
  if (diff < 3600)   return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400)  return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

// apiFetch fallback (utils.js should define it)
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

/* ── Related judgments (live from Indian Kanoon, verifiable) ── */
async function appendCaseLaw(msgEl, query) {
  if (!msgEl || !query) return;
  let cards = [];
  try { cards = await api.get(`/api/research/cases?q=${encodeURIComponent(query.slice(0, 200))}`); }
  catch (_) { return; }
  if (!cards || !cards.length) return;

  const wrap = document.createElement("div");
  wrap.style.cssText = "margin-top:.75rem;border-top:1px solid var(--border);padding-top:.6rem";
  const head = `<div style="font-size:.7rem;font-weight:800;letter-spacing:.05em;color:var(--text-3);text-transform:uppercase;margin-bottom:.5rem">
    <i class="ti ti-gavel"></i> Related judgments &amp; provisions (verify via link)</div>`;
  const items = cards.slice(0, 5).map(c => {
    const tid = (c.url || "").split("/doc/")[1]?.replace("/", "") || "";
    const meta = [c.court, c.date, c.citation].filter(Boolean).join(" · ");
    const cited = (c.cited_by && /^\d+$/.test(c.cited_by)) ? ` · cited by ${c.cited_by}` : "";
    return `<div style="background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:.55rem .7rem;margin-bottom:.4rem">
      <div style="font-size:.82rem;font-weight:600;color:var(--text)">${esc(c.title)}</div>
      <div style="font-size:.68rem;color:var(--text-3);margin-top:.15rem">${esc(meta)}${cited}</div>
      ${c.snippet ? `<div style="font-size:.72rem;color:var(--text-2);margin-top:.3rem;font-style:italic">"${esc(c.snippet.slice(0,160))}"</div>` : ""}
      <div style="display:flex;gap:.5rem;margin-top:.45rem">
        <a href="${esc(c.url)}" target="_blank" rel="noopener" style="font-size:.72rem;color:var(--gold,#C8A96A);font-weight:700;text-decoration:none">Read full ↗</a>
        ${tid ? `<button onclick="summariseJudgment('${tid}', this)" style="font-size:.72rem;border:1px solid var(--border);background:transparent;color:var(--text-2);border-radius:6px;padding:.15rem .55rem;cursor:pointer;font-weight:700">Summarise</button>` : ""}
      </div>
      <div class="jsum"></div>
    </div>`;
  }).join("");
  const caveat = `<div style="font-size:.68rem;color:var(--text-3);margin-top:.4rem;font-style:italic">
    &#x26A0; Good-law status unverified — a judgment may have been overruled or reversed; check its subsequent history before relying on it.</div>`;
  wrap.innerHTML = head + items + caveat;
  (msgEl.querySelector(".msg-bubble") || msgEl).appendChild(wrap);
  scrollBottom();
}

async function summariseJudgment(tid, btn) {
  const slot = btn.parentElement.parentElement.querySelector(".jsum");
  const orig = btn.textContent;
  btn.textContent = "Summarising…"; btn.disabled = true;
  try {
    const r = await api.get(`/api/research/cases/${tid}/summary`);
    slot.innerHTML = `<div style="margin-top:.5rem;background:rgba(200,169,106,.06);border:1px solid rgba(200,169,106,.18);border-radius:7px;padding:.55rem .7rem;font-size:.76rem;line-height:1.55;color:var(--text)">
      ${esc(r.summary)}<div style="font-size:.66rem;color:var(--text-3);margin-top:.35rem">${esc(r.disclaimer)}</div></div>`;
  } catch (_) {
    slot.innerHTML = `<div style="margin-top:.5rem;font-size:.72rem;color:var(--text-3)">Could not summarise — open the link to read it.</div>`;
  } finally { btn.textContent = orig; btn.disabled = false; }
}
