# Juriscite — Google Stitch UI/UX Prompt

> Paste the **Design System** block first, then generate each screen with its own block.
> Stitch works best one screen at a time; keep the Design System pinned for consistency.

---

## MASTER PROMPT (paste this first)

Design a premium, trustworthy **web app + installable PWA** called **Juriscite** — an AI‑native legal
practice operating system for **Indian advocates and small law firms**. The product helps an advocate
manage clients and matters, track court hearings in a diary, ask **cited** legal‑research questions, and
generate court drafts that a human advocate reviews before anything is final. Audience: working Indian
lawyers — calm, serious, professional, not playful. Feel: "Bloomberg Terminal meets a fine law library."

### Design system
- **Mood:** premium, confident, trustworthy, focused. Dense information shown calmly. Zero clutter.
- **Theme:** dark‑first. Deep charcoal/navy backgrounds (#0E1116 / #141A22 surfaces), soft elevation.
- **Accent:** legal gold (#E9C46A → #F2C94C gradient) used sparingly for primary actions, active state,
  and numerals. Success green, warning amber, danger red — muted, not neon.
- **Glassmorphism:** cards are subtly translucent with soft blur, 1px hairline border (white @ 8%),
  gentle shadow. Slight 3D depth and a small lift + glow on hover.
- **Typography:** display/headings in a refined serif (**Fraunces**); body/UI in a clean geometric sans
  (**Plus Jakarta Sans**). Generous line‑height, comfortable reading measure.
- **Brand mark:** the word‑mark "Juris·cite" with "cite" in shimmering gold; an icon of a gold "§"
  (section sign) on a glass tile, optionally a slow‑rotating 3D cube on the dashboard hero.
- **Layout:** left vertical sidebar nav (collapsible), slim top bar (search, notifications bell, user
  menu), main content area with breathing room. 12‑col responsive grid; fully responsive to mobile.
- **Components:** glass cards, stat tiles with gold gradient numerals, data tables with sticky headers
  and row hover, tabs, modals/drawers, pill badges, toasts, skeleton loaders, empty states with a line
  illustration + one clear CTA.
- **Motion:** subtle, 150–250ms ease; hover lift, button sheen, fade‑in on load. Never gratuitous.
- **Accessibility:** WCAG AA contrast, visible focus rings, keyboard navigable, screen‑reader labels.
- **Trust cues everywhere the AI appears:** confidence badge (HIGH=green / MEDIUM=amber / LOW=red),
  "Sources consulted" with clickable citations, and an "AI‑generated — verify before relying" note.

---

## SCREENS

### 1. Auth — Login / Register / 2FA
Split layout: left = brand panel (dark glass, rotating gold "§" cube, tagline "Cite the law. Trust the
draft."); right = form card. **Login** (email, password, "Sign in" gold button, forgot‑password link).
**2FA step** (6‑digit code input, "Verify"). **Register** (full name, firm name → creates the firm/tenant,
email, password, role selector). A consent checkbox with link to privacy policy. Minimal, reassuring.

### 2. Dashboard
Top: greeting "Good morning, Adv. <name>" + date, and a small 3D gold "§" cube hero. A 7‑day **court‑diary
strip** (each day a glass tile, today highlighted gold, shows hearing count). Row of **stat tiles**:
Today's Hearings, Open Tasks, Pending Deadlines, Active Matters — big gold‑gradient numerals. An
**onboarding checklist** card (add first client → matter → hearing → ask AI → generate draft) with a
progress bar. A **"Latest from the courts"** feed (recent judgments: title, court, date, link). A **Cases
Overview** card (counts by status) and a **Recent Cases** table. Floating "Install Juriscite" button.

### 3. Clients
Searchable table (name, contact, matters count, last activity) + "Add client" gold button. Row click →
**Client detail drawer**: contact info, list of linked matters, notes. Add/edit client modal.

### 4. Matters / Cases
Master list with search + filters (status, court, advocate). "Create matter" → modal (title, client,
court, case number, case type, opposite party, advocate assigned). **Matter detail** = header (title,
status pill, court/case meta) + tabs: **Overview** (notes, parties), **Hearings**, **Tasks**,
**Deadlines**, **Documents**, **Drafts**. Sortable columns; calm density.

### 5. Court Diary
Daily and weekly views of hearings. Each hearing card: date, court, matter, purpose, **next date**.
"Add hearing" modal (manual entry). Buttons: **Export to calendar (.ics)** and a flagged, read‑only
**eCourts sync** toggle. Reminders indicator. A month mini‑calendar for navigation.

### 6. Tasks & Deadlines
Kanban or list of tasks (assignee, due date, status: To‑do / In‑progress / Done) and a deadlines list
with countdown chips (overdue = red). Quick‑add. Filter by matter or assignee.

### 7. Fee Ledger
Per‑matter fees: agreed, received, balance — with a small bar/donut. Add payment entry. Totals summary
card. Export. (No payment processing — record‑keeping only.)

### 8. AI Research Assistant (flagship screen)
Three‑pane chat workspace. **Left:** conversation history (new chat button, searchable). **Center:** the
chat — user bubbles + assistant answers that show a **confidence badge** at the top, the answer in clean
prose, and a **"📚 Sources consulted"** block listing **Provisions** (Act, section, title, source link)
and **Judgments** (case name, court, date, link). A composer at the bottom with a **language selector**
(22 Indian languages), a **microphone** voice‑input button, and quick‑prompt suggestion chips. **Right:**
a **statute/source viewer** that opens the cited section's verbatim text. Always show a small "AI‑generated
— verify before relying" line. If no source is found, show a clean "No verified source — I won't guess"
state, not an answer.

### 9. Drafting Engine
**Template gallery** (cards): Legal Notice, Bail Application, Anticipatory Bail, Vakalatnama, Affidavit,
Divorce Petition, Writ Petition, + **Custom Document**. Selecting one opens a **guided form** (parties,
facts, jurisdiction…). Output opens in a **draft editor** with a prominent amber banner
**"DRAFT — for advocate review"**, an **Approve** action (advocate‑only), **version history** with a
side‑by‑side **diff**, and **Export DOCX / PDF**. Every draft ends with the review disclaimer.

### 10. Documents
Upload area (drag‑drop), document list with versions, preview, download. Version badges.

### 11. Account / Settings
Tabs: **Profile**, **Security** (change password, enable/disable **2FA** with QR), **Privacy & Data**
(view consent records, **Export my data**, **Delete my account** — DPDP rights), **Report misuse**.
Calm forms, clear save states.

### 12. Admin (Firm Admin / Super Admin)
**Audit log** table (who/what/when, tenant‑scoped, filterable), **Backups** (list + trigger), **Member
management** (roles), **Advocate verification** approvals. Restrained, data‑dense.

### Global
- Collapsible sidebar with icons: Dashboard, Clients, Matters, Court Diary, Tasks, Fees, AI Assistant,
  Drafting, Documents, Admin, Account.
- Top bar: global search, notifications bell (with unread dot), user avatar menu, install‑PWA chip.
- Toaster notifications, command‑palette (⌘K) optional, skeleton loaders, empty states, 404.
- Mobile: sidebar becomes a bottom tab bar / hamburger drawer; tables become stacked cards.

### Hard product rules to reflect visually
- The AI **never** answers law without showing sources; show the confidence badge + citations every time.
- Drafts are **never** "final" until an advocate approves; keep the amber review banner until then.
- Tenant isolation: a user only ever sees their own firm's data.
- No "win prediction"/outcome‑guarantee UI anywhere (legally prohibited).
