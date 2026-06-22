const state = {
  me: null,
  control: null,
  section: "voice",
  refreshing: false,
};

const byId = (id) => document.getElementById(id);

function setNotice(message, kind = "info") {
  const notice = byId("notice");
  if (!message) {
    notice.className = "notice hidden";
    notice.textContent = "";
    return;
  }
  notice.className = `notice ${kind}`;
  notice.textContent = message;
}

function apiError(payload, fallback) {
  return payload?.message || fallback || "Không thể hoàn tất yêu cầu.";
}

async function request(url, options = {}) {
  const response = await fetch(url, {
    cache: "no-store",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload?.ok === false) throw new Error(apiError(payload, `HTTP ${response.status}`));
  return payload;
}

function avatarUrl(user) {
  if (!user?.avatar) return "";
  return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png?size=64`;
}

function showSection(section) {
  state.section = section;
  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === section);
  });
  document.querySelectorAll("[data-section]").forEach((button) => {
    button.classList.toggle("active", button.dataset.section === section);
  });
  const titles = {
    voice: "Treo phòng voice",
    presence: "RPC và presence",
    access: "Quyền truy cập",
  };
  byId("pageTitle").textContent = titles[section] || titles.voice;
  history.replaceState(null, "", section === "voice" ? "/control" : `/control#${section}`);
}

function renderAccount() {
  const loggedIn = Boolean(state.me?.logged_in);
  byId("loginGate").classList.toggle("hidden", loggedIn);
  byId("workspace").classList.toggle("hidden", !loggedIn);
  const account = byId("accountButton");
  if (!loggedIn) {
    const enabled = state.me?.login_enabled !== false;
    account.textContent = enabled ? "Đăng nhập Discord" : "OAuth chưa cấu hình";
    account.href = enabled ? "/auth/login?next=control" : "#";
    byId("loginButton").textContent = enabled ? "Tiếp tục với Discord" : "OAuth chưa cấu hình";
    byId("loginButton").href = enabled ? "/auth/login?next=control" : "#";
    byId("loginButton").classList.toggle("disabled", !enabled);
    account.style.removeProperty("--avatar");
    return;
  }
  const user = state.me.user;
  account.textContent = user.username || "Discord user";
  account.href = "/auth/logout";
  const avatar = avatarUrl(user);
  if (avatar) account.style.setProperty("--avatar", `url(${avatar})`);
}

function renderAccess() {
  const list = byId("accessList");
  const guilds = state.me?.guilds || [];
  byId("verifiedCard").innerHTML = state.me?.verified
    ? '<strong>✓ Đã xác minh</strong> · Hồ sơ được lưu để đồng bộ role khi bạn vào server mới.'
    : 'Chưa xác minh. Đăng nhập web hoặc bấm Verify trong Discord.';
  const globalForm = byId("globalKeyForm");
  globalForm.querySelector("strong").textContent = state.me?.extension_access ? "Extension đang hoạt động" : "Kích hoạt key Extension";
  if (!guilds.length) {
    list.innerHTML = '<div class="empty-state">Không tìm thấy server Discord do bạn quản lý.</div>';
    return;
  }
  list.innerHTML = guilds.map((guild) => `
    <article class="access-row ${guild.has_key ? "active" : ""}">
      <div class="server-avatar">${escapeHtml((guild.name || "?").slice(0, 2).toUpperCase())}</div>
      <div class="access-copy">
        <strong>${escapeHtml(guild.name)}</strong>
        <small>${guild.has_key ? "Đã có quyền Voice Station" : "Chưa kích hoạt key"}</small>
      </div>
      ${guild.has_key ? `
        <div class="access-actions"><span class="access-status">BOT ACTIVE</span>
        ${guild.general_invite ? `<a class="secondary-button" href="${escapeHtml(guild.general_invite)}" target="_blank" rel="noreferrer">Mời bot</a>` : ""}</div>
      ` : `
        <form class="key-form" data-guild-id="${guild.id}">
          <input name="key" autocomplete="off" placeholder="Nhập key" required />
          <button class="secondary-button" type="submit">Kích hoạt</button>
        </form>
      `}
    </article>
  `).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function currentGuild() {
  const id = byId("guildSelect").value;
  return (state.control?.guilds || []).find((guild) => guild.id === id);
}

function renderChannels() {
  const guild = currentGuild();
  const select = byId("channelSelect");
  const missing = byId("botMissing");
  const form = byId("voiceForm");
  if (!guild) {
    select.innerHTML = '<option value="">Không có server được cấp quyền</option>';
    form.classList.remove("hidden");
    missing.classList.add("hidden");
    return;
  }
  if (!guild.bot_present) {
    form.classList.add("hidden");
    missing.classList.remove("hidden");
    byId("inviteButton").href = guild.invite_url || "#";
    return;
  }
  form.classList.remove("hidden");
  missing.classList.add("hidden");
  const channels = guild.channels || [];
  select.innerHTML = channels.length
    ? channels.map((channel) => `<option value="${channel.id}" ${channel.id === guild.target_channel_id ? "selected" : ""}>${escapeHtml(channel.name)} · ${channel.members} người</option>`).join("")
    : '<option value="">Bot không có quyền Connect vào room nào</option>';
}

function renderSessions() {
  const list = byId("sessionList");
  const connections = state.control?.connections || [];
  const pending = (state.control?.guilds || []).filter((guild) => guild.target_channel_id && !guild.voice_channel_id);
  const rows = [
    ...connections.map((item) => ({ ...item, status: "connected" })),
    ...pending.map((guild) => ({
      guild_id: guild.id,
      guild_name: guild.name,
      channel_id: guild.target_channel_id,
      channel_name: guild.target_channel_name || "Đang nối lại",
      status: "reconnecting",
      latency_ms: 0,
    })),
  ];
  byId("connectionCount").textContent = String(connections.length);
  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">Chưa có room nào được ghim.</div>';
    return;
  }
  list.innerHTML = rows.map((item) => `
    <article class="session-row">
      <span class="session-indicator ${item.status}"></span>
      <div><strong>${escapeHtml(item.channel_name)}</strong><small>${escapeHtml(item.guild_name)}</small></div>
      <div class="session-meta"><strong>${item.status === "connected" ? `${item.latency_ms} ms` : "RETRY"}</strong><small>${item.status === "connected" ? "Connected" : "Persistent target"}</small></div>
    </article>
  `).join("");
}

function renderControl() {
  const control = state.control;
  const online = Boolean(control?.online);
  const badge = byId("runtimeBadge");
  badge.classList.toggle("online", online);
  badge.classList.toggle("offline", !online);
  byId("runtimeText").textContent = online ? "Bot online" : "Bot offline";
  byId("botName").textContent = control?.user?.name || "Discord bot";
  byId("botLatency").textContent = online ? `${control.latency_ms || 0} ms gateway` : apiError(control, "Chưa kết nối");
  const guilds = control?.guilds || [];
  byId("guildCount").textContent = String(guilds.length);
  const select = byId("guildSelect");
  const selected = select.value;
  select.innerHTML = guilds.length
    ? guilds.map((guild) => `<option value="${guild.id}">${escapeHtml(guild.name)}</option>`).join("")
    : '<option value="">Chưa có server có key hiệu lực</option>';
  if (guilds.some((guild) => guild.id === selected)) select.value = selected;
  renderChannels();
  renderSessions();

  const canPresence = Boolean(control?.can_manage_presence);
  byId("presenceForm").querySelectorAll("input, select, button").forEach((field) => { field.disabled = !canPresence; });
  byId("presencePermission").textContent = canPresence ? "Admin enabled" : "Admin only";
  const presence = control?.presence || {};
  byId("presenceType").value = presence.type || "playing";
  byId("presenceStatus").value = presence.status === "do_not_disturb" ? "dnd" : (presence.status || "online");
  byId("presenceName").value = presence.name || "";
  byId("presenceDetails").value = presence.details || "";
  byId("presenceState").value = presence.state || "";
  byId("presenceUrl").value = presence.url || "";
}

async function loadMe() {
  state.me = await request("/api/me");
  renderAccount();
  renderAccess();
  return state.me;
}

async function loadControl({ quiet = false } = {}) {
  if (!state.me?.logged_in || state.refreshing) return;
  state.refreshing = true;
  byId("refreshButton").classList.add("spinning");
  try {
    state.control = await request("/api/bot/control");
    renderControl();
    if (!quiet && !state.control.online) setNotice(apiError(state.control, "Bot Discord đang offline."), "warning");
  } catch (error) {
    state.control = { online: false, guilds: [], connections: [], message: error.message };
    renderControl();
    if (!quiet) setNotice(error.message, "error");
  } finally {
    state.refreshing = false;
    byId("refreshButton").classList.remove("spinning");
  }
}

async function submitVoice(event) {
  event.preventDefault();
  const guildId = byId("guildSelect").value;
  const channelId = byId("channelSelect").value;
  if (!guildId || !channelId) return setNotice("Hãy chọn server và phòng voice.", "warning");
  byId("joinButton").disabled = true;
  try {
    const result = await request("/api/bot/voice", {
      method: "POST",
      body: JSON.stringify({ action: "join", guild_id: guildId, channel_id: channelId }),
    });
    setNotice(result.message, "success");
    await loadControl({ quiet: true });
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    byId("joinButton").disabled = false;
  }
}

async function leaveVoice() {
  const guildId = byId("guildSelect").value;
  if (!guildId) return setNotice("Hãy chọn server cần ngắt voice.", "warning");
  byId("leaveButton").disabled = true;
  try {
    const result = await request("/api/bot/voice", {
      method: "POST",
      body: JSON.stringify({ action: "leave", guild_id: guildId }),
    });
    setNotice(result.message, "success");
    await loadControl({ quiet: true });
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    byId("leaveButton").disabled = false;
  }
}

async function submitPresence(event) {
  event.preventDefault();
  try {
    const result = await request("/api/bot/presence", {
      method: "POST",
      body: JSON.stringify({
        type: byId("presenceType").value,
        status: byId("presenceStatus").value,
        name: byId("presenceName").value,
        details: byId("presenceDetails").value,
        state: byId("presenceState").value,
        url: byId("presenceUrl").value,
      }),
    });
    setNotice(result.message, "success");
    await loadControl({ quiet: true });
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function submitKey(form) {
  const guildId = form.dataset.guildId;
  const key = new FormData(form).get("key");
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const result = await request("/api/key/claim", {
      method: "POST",
      body: JSON.stringify({ guild_id: guildId, key }),
    });
    if (!result.ok) throw new Error(apiError(result));
    state.me = result.me;
    renderAccess();
    setNotice(result.message, "success");
    await loadControl({ quiet: true });
  } catch (error) {
    setNotice(error.message, "error");
    button.disabled = false;
  }
}

async function submitGlobalKey(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const result = await request("/api/key/claim", {
      method: "POST",
      body: JSON.stringify({ key: new FormData(form).get("key") }),
    });
    state.me = result.me;
    renderAccess();
    setNotice(result.message, "success");
    await loadControl({ quiet: true });
  } catch (error) {
    setNotice(error.message, "error");
  } finally { button.disabled = false; }
}

async function boot() {
  const params = new URLSearchParams(location.search);
  const loginError = params.get("login_error") || (params.get("login") === "failed" ? "Discord OAuth không hoàn tất." : "");
  if (loginError) {
    setNotice(loginError, "error");
    history.replaceState(null, "", location.pathname + location.hash);
  }
  try {
    await loadMe();
    if (state.me.logged_in) await loadControl();
  } catch (error) {
    setNotice(error.message, "error");
  }
  const initial = location.hash.slice(1);
  showSection(["voice", "presence", "access"].includes(initial) ? initial : "voice");
}

document.querySelectorAll("[data-section]").forEach((button) => {
  button.addEventListener("click", () => showSection(button.dataset.section));
});
byId("guildSelect").addEventListener("change", renderChannels);
byId("voiceForm").addEventListener("submit", submitVoice);
byId("leaveButton").addEventListener("click", leaveVoice);
byId("presenceForm").addEventListener("submit", submitPresence);
byId("refreshButton").addEventListener("click", () => loadControl());
byId("accessList").addEventListener("submit", (event) => {
  if (event.target.matches(".key-form")) {
    event.preventDefault();
    submitKey(event.target);
  }
});
byId("globalKeyForm").addEventListener("submit", submitGlobalKey);

boot();
setInterval(() => loadControl({ quiet: true }), 15000);
