/* Firm workspace — member management (firm-admin only) */

let MY_ID = null;

document.addEventListener("DOMContentLoaded", async () => {
  initNav();
  try { MY_ID = (await api.get("/api/auth/me")).id; } catch (_) {}
  loadMembers();
});

async function loadMembers() {
  const view = document.getElementById("firm-view");
  let members;
  try {
    members = await api.get("/api/firm/members");
  } catch (e) {
    view.innerHTML = `<div class="muted">${String(e.message).includes("403")
      ? "Only a Firm Admin can manage members." : "Could not load members."}</div>`;
    return;
  }
  const rows = members.map(m => {
    const roleCls = m.role === "clerk" ? "role-pill clerk" : "role-pill";
    const status = m.is_active ? "" : " inactive";
    const isSelf = m.id === MY_ID;
    return `<tr class="${status}">
      <td>${esc(m.full_name)}${isSelf ? " <span style='color:var(--text-3);font-size:.7rem'>(you)</span>" : ""}</td>
      <td style="color:var(--text-3)">${esc(m.email)}</td>
      <td><span class="${roleCls}">${esc(m.role.replace("_"," "))}</span>${m.is_2fa_enabled ? " 🔐" : ""}</td>
      <td>${m.is_active ? "Active" : "Inactive"}</td>
      <td style="text-align:right">${isSelf ? "" : `
        <button class="mbtn" onclick="changeRole(${m.id},'${m.role}')">Role</button>
        ${m.is_active ? `<button class="mbtn" onclick="deactivate(${m.id})">Deactivate</button>` : ""}`}</td>
    </tr>`;
  }).join("");
  view.innerHTML = `<table class="mtable">
    <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

async function doInvite() {
  const name = document.getElementById("iv-name").value.trim();
  const email = document.getElementById("iv-email").value.trim();
  const role = document.getElementById("iv-role").value;
  const res = document.getElementById("iv-result");
  const btn = document.getElementById("iv-go");
  if (!name || !email) { res.innerHTML = "<span style='color:#DC4C64'>Name and email required.</span>"; return; }
  btn.disabled = true; btn.textContent = "Inviting…";
  try {
    const r = await api.post("/api/firm/members", { full_name: name, email, role });
    if (r.dev_invite_token) {
      res.innerHTML = `<div style="color:#059669">Invited. Email isn't configured, so share this set-password link:</div>
        <div class="invite-link">/reset-password?token=${esc(r.dev_invite_token)}</div>`;
    } else {
      res.innerHTML = `<span style="color:#059669">Invite emailed to ${esc(email)}.</span>`;
    }
    document.getElementById("iv-name").value = "";
    document.getElementById("iv-email").value = "";
    loadMembers();
  } catch (e) {
    const msg = String(e.message || "");
    res.innerHTML = `<span style="color:#DC4C64">${msg.includes("400") ? "Email exists or seat limit reached." : "Invite failed."}</span>`;
  } finally { btn.disabled = false; btn.textContent = "Send invite"; }
}

async function changeRole(id, current) {
  const next = prompt("New role (advocate / associate / clerk / firm_admin):", current);
  if (!next || next === current) return;
  try { await api.patch(`/api/firm/members/${id}`, { role: next }); toast("Role updated.", "success"); loadMembers(); }
  catch (e) { toast(String(e.message).includes("400") ? "Cannot remove the last admin." : "Update failed.", "error"); }
}

async function deactivate(id) {
  if (!confirm("Deactivate this member? They will lose access immediately.")) return;
  try { await api.del(`/api/firm/members/${id}`); toast("Member deactivated.", "success"); loadMembers(); }
  catch (e) { toast(String(e.message).includes("400") ? "Cannot remove the last admin." : "Failed.", "error"); }
}
