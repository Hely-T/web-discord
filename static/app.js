const fmt = new Intl.NumberFormat("vi-VN");
let currentSummary = null;
let currentMe = null;

function money(value, suffix = "") {
  return `${fmt.format(Number(value || 0))}${suffix}`;
}

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const node = byId(id);
  if (node) node.textContent = value;
}

function duration(seconds) {
  const total = Number(seconds || 0);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function showView(view, shouldScroll = true) {
  if (view === "admin" && !window.location.pathname.includes("admin")) {
    window.location.href = "/admin";
    return;
  }
  if (view === "dashboard" && currentMe && !currentMe.logged_in) {
    window.location.href = "/auth/login?next=dashboard";
    return;
  }

  const detailArea = byId("detailArea");
  const panels = document.querySelectorAll(".detail-panel");
  const links = document.querySelectorAll("[data-view]");

  links.forEach((link) => link.classList.toggle("active", link.dataset.view === view));
  if (!view || view === "home") {
    detailArea.classList.add("hidden");
    panels.forEach((panel) => panel.classList.add("hidden"));
    history.replaceState(null, "", window.location.pathname);
    return;
  }

  const panel = byId(view);
  if (!panel) return;
  panels.forEach((item) => item.classList.toggle("hidden", item.id !== view));
  detailArea.classList.remove("hidden");
  if (window.location.hash !== `#${view}`) {
    history.replaceState(null, "", `#${view}`);
  }
  if (shouldScroll) {
    detailArea.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderStatus(items) {
  const grid = byId("statusGrid");
  grid.innerHTML = items.map((item) => `
    <article class="status-card ${item.online ? "online" : ""}">
      <div class="status-dot"></div>
      <strong>${escapeHtml(item.name)}</strong>
      <div class="user-meta">${escapeHtml(item.state)}</div>
      <div class="status-metrics">
        <span><b>${money(item.servers)}</b> servers</span>
        <span><b>${money(item.users)}</b> users</span>
        <span><b>${duration(item.uptime_seconds)}</b> uptime</span>
      </div>
    </article>
  `).join("");
}

function renderRows(id, rows, options) {
  const node = byId(id);
  if (!node) return;
  if (!rows || rows.length === 0) {
    node.innerHTML = `<div class="empty">Chưa có dữ liệu để hiển thị.</div>`;
    return;
  }
  node.innerHTML = rows.map((row, index) => {
    const name = options.name(row);
    const meta = options.meta(row);
    const amount = options.amount(row);
    const sub = options.sub ? options.sub(row) : "";
    return `
      <div class="rank-row">
        <span class="rank">${index + 1}</span>
        <div>
          <div class="user-name">${escapeHtml(name)}</div>
          <div class="user-meta">${escapeHtml(meta)}</div>
        </div>
        <div class="amount">
          ${escapeHtml(amount)}
          ${sub ? `<div class="amount-sub">${escapeHtml(sub)}</div>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

function renderPortal(me, summary) {
  const panel = byId("portalPanel");
  const actions = byId("dashboardActions");
  if (!me.logged_in) {
    actions.classList.add("hidden");
    panel.innerHTML = `
      <div class="empty">
        Dashboard cần login Discord để lưu tài khoản và chọn server.
        <div class="hero-actions">
          <a class="button primary" href="/auth/login?next=dashboard">LOGIN DISCORD</a>
          <a class="button secondary" href="${summary.app.contact_url}">LIÊN HỆ ADMIN</a>
        </div>
      </div>
    `;
    return;
  }

  byId("loginLink").textContent = "LOGOUT";
  byId("loginLink").href = "/auth/logout";
  actions.classList.remove("hidden");
  renderRentGuilds(me.guilds);
  renderRequests(me.requests);

  const guildCards = me.guilds.length
    ? me.guilds.map((guild) => `
      <article class="guild-card" data-guild-id="${guild.id}">
        <div>
          <div class="user-name">${escapeHtml(guild.name)}</div>
          <div class="user-meta">ID ${escapeHtml(guild.id)} · ${guild.has_key ? "Đã kích hoạt bot tổng" : "Casino public, bot tổng cần key"}</div>
        </div>
        <div class="guild-actions">
          ${guild.casino_invite ? `<a class="tiny-button cyan" href="${guild.casino_invite}">INVITE CASINO</a>` : ""}
          ${guild.has_key && guild.general_invite ? `<a class="tiny-button pink" href="${guild.general_invite}">INVITE BOT TỔNG</a>` : `
            <input placeholder="Nhập key thuê bot tổng" data-key-input="${guild.id}" />
            <button type="button" data-claim="${guild.id}">KÍCH HOẠT</button>
          `}
        </div>
      </article>
    `).join("")
    : `<div class="empty">Không thấy server nào bạn có quyền quản lý.</div>`;

  panel.innerHTML = `
    <div class="account-strip">
      <div>
        <div class="user-name">${escapeHtml(me.user.username)}</div>
        <div class="user-meta">Discord ID ${escapeHtml(me.user.id)}</div>
      </div>
      <a class="tiny-button" href="${summary.app.contact_url}">LIÊN HỆ ADMIN</a>
    </div>
    ${guildCards}
  `;
}

function renderRentGuilds(guilds) {
  const select = byId("rentGuild");
  if (!guilds || guilds.length === 0) {
    select.innerHTML = `<option value="">Không có server quản lý</option>`;
    return;
  }
  select.innerHTML = guilds.map((guild) => (
    `<option value="${escapeHtml(guild.id)}">${escapeHtml(guild.name)}</option>`
  )).join("");
}

function renderRequests(requests = {}) {
  const rows = [
    ...(requests.topups || []).map((item) => ({
      name: `Nạp ${money(item.amount, " VNĐ")}`,
      meta: item.note || item.method,
      status: item.status,
      time: item.created_at,
    })),
    ...(requests.rentals || []).map((item) => ({
      name: `Thuê key ${item.months} tháng`,
      meta: item.guild_name,
      status: item.status,
      time: item.created_at,
    })),
  ];
  renderRows("requestList", rows, {
    name: (row) => row.name,
    meta: (row) => row.meta,
    amount: (row) => row.status,
    sub: (row) => row.time,
  });
}

async function loadMe(summary) {
  const response = await fetch("/api/me", { cache: "no-store" });
  currentMe = await response.json();

  const casinoInvite = byId("casinoInvite");
  if (currentMe.casino_invite) {
    casinoInvite.href = currentMe.casino_invite;
    casinoInvite.removeAttribute("data-view");
  }
  renderPortal(currentMe, summary);
}

async function claimKey(guildId) {
  const input = document.querySelector(`[data-key-input="${guildId}"]`);
  const key = input ? input.value.trim() : "";
  const response = await fetch("/api/key/claim", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guild_id: guildId, key }),
  });
  const data = await response.json();
  alert(data.message);
  if (data.me) {
    currentMe = data.me;
    renderPortal(currentMe, currentSummary);
  }
}

async function checkHomeKey(event) {
  event.preventDefault();
  const key = byId("homeKeyInput").value.trim();
  setText("homeKeyMessage", "Đang kiểm tra key...");
  const response = await fetch("/api/key/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const data = await response.json();
  setText("homeKeyMessage", data.message);
  if (data.ok && data.invite_url) {
    window.location.href = data.invite_url;
  }
}

async function submitTopup(event) {
  event.preventDefault();
  const response = await fetch("/api/topup/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      amount: byId("topupAmount").value,
      method: "manual",
      note: byId("topupNote").value,
    }),
  });
  const data = await response.json();
  alert(data.message);
  if (data.me) {
    currentMe = data.me;
    renderPortal(currentMe, currentSummary);
  }
}

async function submitRent(event) {
  event.preventDefault();
  const response = await fetch("/api/rent/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      guild_id: byId("rentGuild").value,
      months: byId("rentMonths").value,
      plan: "bot_tong",
      note: byId("rentNote").value,
    }),
  });
  const data = await response.json();
  alert(data.message);
  if (data.me) {
    currentMe = data.me;
    renderPortal(currentMe, currentSummary);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadSummary() {
  const response = await fetch("/api/summary", { cache: "no-store" });
  currentSummary = await response.json();

  document.title = `${currentSummary.app.brand} Dashboard`;
  setText("domain", currentSummary.app.domain);
  setText("updated", `Cập nhật ${new Date(currentSummary.app.updated_at * 1000).toLocaleString("vi-VN")}`);
  renderStatus(currentSummary.status);

  renderRows("cashTop", currentSummary.cash.top, {
    name: (row) => row.username || row.user_id,
    meta: (row) => `ID ${row.user_id} · Level ${row.level || 1}`,
    amount: (row) => money(row.cash, " VNĐ"),
    sub: (row) => `Donate ${money(row.total_donate, " VNĐ")}`,
  });

  renderRows("casinoTop", currentSummary.casino.top, {
    name: (row) => row.user_id,
    meta: (row) => `Role ${row.role || "user"}`,
    amount: (row) => money(row.balance, " OWO"),
    sub: (row) => row.updated_at || "",
  });

  renderRows("donateTop", currentSummary.bank.donate_top, {
    name: (row) => row.username || "User",
    meta: (row) => `${money(row.donate_count)} lượt donate`,
    amount: (row) => money(row.amount, " VNĐ"),
    sub: (row) => row.updated_at || "",
  });

  await loadMe(currentSummary);
  const initialView = window.location.hash.replace("#", "") || (
    window.location.pathname.includes("dashboard") ? "dashboard" : "home"
  );
  showView(initialView, false);
}

async function searchUser(event) {
  event.preventDefault();
  const query = byId("searchInput").value.trim();
  const results = byId("searchResults");
  if (query.length < 3) {
    results.innerHTML = `<div class="empty">Nhập tối thiểu 3 ký tự.</div>`;
    return;
  }
  results.innerHTML = `<div class="empty">Đang tìm...</div>`;
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { cache: "no-store" });
  const data = await response.json();
  renderRows("searchResults", data.results, {
    name: (row) => row.username || row.user_id,
    meta: (row) => `ID ${row.user_id} · Level ${row.level || 1}`,
    amount: (row) => money(row.cash, " VNĐ"),
    sub: (row) => `Donate ${money(row.total_donate, " VNĐ")}`,
  });
}

document.addEventListener("click", (event) => {
  if (!(event.target instanceof Element)) return;
  const viewLink = event.target.closest("[data-view]");
  if (!viewLink) return;
  event.preventDefault();
  showView(viewLink.dataset.view || "home");
});

byId("homeKeyForm").addEventListener("submit", checkHomeKey);
byId("searchForm").addEventListener("submit", searchUser);
byId("topupForm").addEventListener("submit", submitTopup);
byId("rentForm").addEventListener("submit", submitRent);
byId("portalPanel").addEventListener("click", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && target.dataset.claim) {
    claimKey(target.dataset.claim);
  }
});

loadSummary().catch((error) => {
  console.error(error);
  setText("updated", "Không tải được dữ liệu");
});
