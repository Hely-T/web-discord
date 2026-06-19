const fmt = new Intl.NumberFormat("vi-VN");
let currentSummary = null;
let currentMe = null;
let currentBotControl = null;

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

function renderArchiveFeatures(features) {
  const grid = byId("archiveFeatures");
  if (!grid || !features || !features.groups) return;
  grid.innerHTML = features.groups.map((group) => `
    <article class="feature-card ${escapeHtml(group.accent || "")}-line">
      <div class="feature-head">
        <h3>${escapeHtml(group.name)}</h3>
        <span>${escapeHtml(group.commands.length)} lệnh</span>
      </div>
      <p>${escapeHtml(group.description)}</p>
      <div class="command-table">
        ${group.commands.map((cmd) => `
          <div class="command-row">
            <div>
              <strong>${escapeHtml(cmd.name)}</strong>
              ${cmd.aliases ? `<small>${escapeHtml(cmd.aliases)}</small>` : ""}
            </div>
            <code>${escapeHtml(cmd.usage)}</code>
            <span>${escapeHtml(cmd.description)}</span>
          </div>
        `).join("")}
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

function renderHeaderState(me) {
  const loginLink = byId("loginLink");
  if (!loginLink || !me) return;
  if (!me.logged_in) {
    loginLink.textContent = "LOGIN";
    loginLink.href = "/auth/login?next=dashboard";
    loginLink.classList.remove("logged-in");
    setText("dashboardSubtitle", "Login Discord để nạp tiền, thuê key và invite bot tổng");
    return;
  }

  loginLink.innerHTML = `
    <span>${escapeHtml(me.user.username)}</span>
    <small>${escapeHtml(me.user.role || "user")}</small>
  `;
  loginLink.href = "/auth/logout";
  loginLink.classList.add("logged-in");
  setText("dashboardSubtitle", `Đã login Discord: ${me.user.username}`);
}

function renderPortal(me, summary) {
  const panel = byId("portalPanel");
  const actions = byId("dashboardActions");
  renderHeaderState(me);
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
        <div class="label">Tài khoản Discord</div>
        <div class="user-name">${escapeHtml(me.user.username)}</div>
        <div class="user-meta">Discord ID ${escapeHtml(me.user.id)} · ${escapeHtml(me.user.status)} · ${escapeHtml(me.user.role)}</div>
      </div>
      <div class="account-actions">
        <a class="tiny-button cyan" href="${summary.app.contact_url}">LIÊN HỆ ADMIN</a>
        <a class="tiny-button" href="/auth/logout">LOGOUT</a>
      </div>
    </div>
    <div class="dashboard-hint">
      <strong>Server bạn quản lý</strong>
      <span>Invite casino trực tiếp. Bot tổng cần kích hoạt key theo từng server.</span>
    </div>
    ${guildCards}
  `;
}

function renderVoiceChannels() {
  const guildSelect = byId("botGuild");
  const channelSelect = byId("botVoiceChannel");
  const guildAccess = byId("botGuildAccess");
  const joinButton = byId("botJoinVoice");
  const guild = (currentBotControl?.guilds || []).find((item) => item.id === guildSelect.value);
  const previous = channelSelect.value;
  if (!guild || guild.channels.length === 0) {
    channelSelect.innerHTML = `<option value="">Không có phòng voice khả dụng</option>`;
    joinButton.disabled = true;
    guildAccess.innerHTML = guild && !guild.bot_present && guild.invite_url
      ? `<a class="tiny-button cyan" href="${escapeHtml(guild.invite_url)}">INVITE VOICE BOT</a>`
      : `<span>${guild ? "Bot không thấy phòng có quyền Connect." : "Chưa có server khả dụng."}</span>`;
    return;
  }
  joinButton.disabled = false;
  guildAccess.innerHTML = "";
  channelSelect.innerHTML = guild.channels.map((channel) => (
    `<option value="${escapeHtml(channel.id)}">${escapeHtml(channel.name)} (${channel.members})</option>`
  )).join("");
  if (guild.channels.some((channel) => channel.id === previous)) {
    channelSelect.value = previous;
  } else if (guild.voice_channel_id) {
    channelSelect.value = guild.voice_channel_id;
  }
}

function renderBotControl(data) {
  const panel = byId("botControl");
  panel.classList.remove("hidden");
  currentBotControl = data;
  byId("botRuntimeDot").classList.toggle("online", Boolean(data.online));
  setText("botRuntimeName", data.user?.name || "Discord bot");
  setText("botRuntimeMeta", data.online ? `${data.latency_ms}ms · ${data.guilds.length} server khả dụng` : "Offline");

  const guildSelect = byId("botGuild");
  const previousGuild = guildSelect.value;
  guildSelect.innerHTML = data.guilds.length
    ? data.guilds.map((guild) => `<option value="${escapeHtml(guild.id)}">${escapeHtml(guild.name)}</option>`).join("")
    : `<option value="">Không có server đã kích hoạt</option>`;
  if (data.guilds.some((guild) => guild.id === previousGuild)) guildSelect.value = previousGuild;
  renderVoiceChannels();

  const connections = byId("voiceConnections");
  connections.innerHTML = data.connections.length
    ? data.connections.map((item) => `
      <div class="voice-connection">
        <span class="runtime-dot online"></span>
        <div>
          <strong>${escapeHtml(item.channel_name)}</strong>
          <small>${escapeHtml(item.guild_name)} · ${item.latency_ms}ms</small>
        </div>
      </div>
    `).join("")
    : `<div class="empty compact-empty">Bot chưa treo voice.</div>`;

  const presenceForm = byId("presenceForm");
  presenceForm.classList.toggle("hidden", !data.can_manage_presence);
  if (data.can_manage_presence) {
    byId("presenceType").value = data.presence?.type || "playing";
    byId("presenceStatus").value = data.presence?.status || "online";
    byId("presenceName").value = data.presence?.name || "";
    byId("presenceDetails").value = data.presence?.details || "";
    byId("presenceState").value = data.presence?.state || "";
    byId("presenceUrl").value = data.presence?.url || "";
  }
}

async function loadBotControl() {
  const panel = byId("botControl");
  if (!currentMe?.logged_in) {
    panel.classList.add("hidden");
    return;
  }
  const response = await fetch("/api/bot/control", { cache: "no-store" });
  const data = await response.json();
  if (!data.ok) {
    panel.classList.remove("hidden");
    setText("botRuntimeMeta", "Offline");
    setText("botRuntimeMessage", data.message || "Không tải được bot runtime.");
    return;
  }
  setText("botRuntimeMessage", "");
  renderBotControl(data);
}

async function controlVoice(action) {
  const guildId = byId("botGuild").value;
  const channelId = byId("botVoiceChannel").value;
  if (!guildId || (action === "join" && !channelId)) {
    setText("botRuntimeMessage", "Hãy chọn server và phòng voice.");
    return;
  }
  setText("botRuntimeMessage", action === "join" ? "Đang kết nối voice..." : "Đang rời voice...");
  const response = await fetch("/api/bot/voice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, guild_id: guildId, channel_id: channelId }),
  });
  const data = await response.json();
  setText("botRuntimeMessage", data.message || "Đã xử lý.");
  if (data.ok) await loadBotControl();
}

async function updatePresence(event) {
  event.preventDefault();
  setText("botRuntimeMessage", "Đang cập nhật presence...");
  const response = await fetch("/api/bot/presence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: byId("presenceType").value,
      status: byId("presenceStatus").value,
      name: byId("presenceName").value,
      details: byId("presenceDetails").value,
      state: byId("presenceState").value,
      url: byId("presenceUrl").value,
    }),
  });
  const data = await response.json();
  setText("botRuntimeMessage", data.message || "Đã xử lý.");
  if (data.ok) await loadBotControl();
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
  await loadBotControl();
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
  setText("homeUsers", money(currentSummary.cash.users || currentSummary.casino.players));
  setText("homeCash", money(currentSummary.cash.cash_total, " VNĐ"));
  setText("homeOwo", money(currentSummary.casino.owo_total, " OWO"));
  setText("homeTx", money(currentSummary.casino.transactions));
  renderStatus(currentSummary.status);
  renderArchiveFeatures(currentSummary.archive_features);

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
byId("botGuild").addEventListener("change", renderVoiceChannels);
byId("botJoinVoice").addEventListener("click", () => controlVoice("join"));
byId("botLeaveVoice").addEventListener("click", () => controlVoice("leave"));
byId("botControlRefresh").addEventListener("click", loadBotControl);
byId("presenceForm").addEventListener("submit", updatePresence);
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
