const fmt = new Intl.NumberFormat("vi-VN");
let adminState = null;

function byId(id) {
  return document.getElementById(id);
}

function money(value) {
  return fmt.format(Number(value || 0));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

async function loadSnapshot() {
  const response = await fetch("/api/admin/snapshot", { cache: "no-store" });
  const data = await response.json();
  if (data.ok) {
    unlock();
    renderAll(data);
  }
}

function unlock() {
  byId("keyForm").classList.remove("locked");
}

function renderAll(data) {
  adminState = data;
  byId("statKeys").textContent = money(data.keys.length);
  byId("statUsers").textContent = money(data.users.length);
  byId("statRequests").textContent = money((data.topups || []).length + (data.rentals || []).length);
  renderKeys(data.keys || []);
  renderUsers(data.users || []);
  renderRequests(data.topups || [], data.rentals || []);
}

function renderKeys(keys) {
  const tbody = byId("keysTable");
  if (!keys.length) {
    tbody.innerHTML = `<tr><td colspan="6">Chưa có key.</td></tr>`;
    return;
  }
  tbody.innerHTML = keys.map((key) => `
    <tr>
      <td>
        <strong>${escapeHtml(key.key)}</strong>
        <div class="muted">${escapeHtml(key.note || "không ghi chú")}</div>
      </td>
      <td>${escapeHtml(key.status)}</td>
      <td>
        ${escapeHtml(key.expires_at || "không hạn")}
        <div class="muted">${money(key.duration_days)} ngày</div>
      </td>
      <td>${money(key.used_guilds)}/${money(key.max_guilds)}</td>
      <td>${escapeHtml(key.used_by || "chưa có")}</td>
      <td>
        <div class="actions">
          <button data-key-action="lock" data-key="${escapeHtml(key.key)}">Khóa</button>
          <button class="cyan" data-key-action="unlock" data-key="${escapeHtml(key.key)}">Mở</button>
          <button class="ghost" data-key-action="extend" data-key="${escapeHtml(key.key)}">+30 ngày</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderUsers(users) {
  const tbody = byId("usersTable");
  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="5">Chưa có user login.</td></tr>`;
    return;
  }
  tbody.innerHTML = users.map((user) => `
    <tr>
      <td>
        <strong>${escapeHtml(user.username)}</strong>
        <div class="muted">${escapeHtml(user.discord_user_id)}</div>
      </td>
      <td>${escapeHtml(user.role)}</td>
      <td>
        ${escapeHtml(user.status)}
        ${user.banned_at ? `<div class="muted">ban: ${escapeHtml(user.banned_at)}</div>` : ""}
        ${user.reset_at ? `<div class="muted">reset: ${escapeHtml(user.reset_at)}</div>` : ""}
      </td>
      <td>
        ${money(user.login_count)}
        <div class="muted">${escapeHtml(user.last_login_at || "")}</div>
      </td>
      <td>
        <div class="actions">
          <button data-user-action="ban" data-user="${escapeHtml(user.discord_user_id)}">Ban</button>
          <button class="cyan" data-user-action="unban" data-user="${escapeHtml(user.discord_user_id)}">Unban</button>
          <button class="pink" data-user-action="role" data-role="admin" data-user="${escapeHtml(user.discord_user_id)}">Admin</button>
          <button class="ghost" data-user-action="role" data-role="user" data-user="${escapeHtml(user.discord_user_id)}">User</button>
          <button class="ghost" data-user-action="reset" data-user="${escapeHtml(user.discord_user_id)}">Reset</button>
        </div>
      </td>
    </tr>
  `).join("");
}

function renderRequests(topups, rentals) {
  byId("topupList").innerHTML = topups.length
    ? topups.map((item) => `
      <div class="item">
        <strong>${escapeHtml(item.discord_username)}</strong>
        <div>${money(item.amount)} VNĐ · ${escapeHtml(item.status)}</div>
        <div class="muted">${escapeHtml(item.created_at)}</div>
      </div>
    `).join("")
    : "Chưa có dữ liệu.";

  byId("rentalList").innerHTML = rentals.length
    ? rentals.map((item) => `
      <div class="item">
        <strong>${escapeHtml(item.discord_username)}</strong>
        <div>${escapeHtml(item.guild_name)} · ${money(item.months)} tháng · ${escapeHtml(item.status)}</div>
        <div class="muted">${escapeHtml(item.created_at)}</div>
      </div>
    `).join("")
    : "Chưa có dữ liệu.";
}

async function adminLogin(event) {
  event.preventDefault();
  const data = await postJson("/api/admin/login", { password: byId("adminPassword").value });
  if (!data.ok) {
    alert(data.message);
    return;
  }
  unlock();
  renderAll(data);
}

async function createKey(event) {
  event.preventDefault();
  const data = await postJson("/api/admin/keys", {
    note: byId("keyNote").value,
    amount: byId("keyAmount").value,
    max_guilds: byId("keyMaxGuilds").value,
    duration_days: byId("keyDurationDays").value,
  });
  if (!data.ok) {
    alert(data.message);
    return;
  }
  renderAll(data);
}

async function handleAction(event) {
  if (!(event.target instanceof Element)) return;
  const keyButton = event.target.closest("[data-key-action]");
  if (keyButton) {
    const action = keyButton.dataset.keyAction;
    const key = keyButton.dataset.key;
    const data = await postJson("/api/admin/key-action", { key, action, days: 30 });
    if (!data.ok) alert(data.message);
    else renderAll(data);
    return;
  }

  const userButton = event.target.closest("[data-user-action]");
  if (userButton) {
    const action = userButton.dataset.userAction;
    const user_id = userButton.dataset.user;
    const role = userButton.dataset.role || "user";
    const data = await postJson("/api/admin/user-action", { user_id, action, role });
    if (!data.ok) alert(data.message);
    else renderAll(data);
  }
}

byId("adminLogin").addEventListener("submit", adminLogin);
byId("keyForm").addEventListener("submit", createKey);
document.addEventListener("click", handleAction);
loadSnapshot();
