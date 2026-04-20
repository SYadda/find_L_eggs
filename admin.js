const ADMIN_I18N = {
  en: {
    title: "Find L Eggs - Admin",
    subtitle: "Read-only board for votes in the last 3 hours.",
    langLabel: "Language",
    backToMap: "Back to map",
    notice1: "This page is read-only and auto-refreshes every 30 seconds.",
    notice2: "Countdowns update every second based on local browser time.",
    generatedAt: "Generated at:",
    thMarket: "Market",
    thAddress: "Address",
    thSummary: "Summary",
    thDetails: "Active votes (expires in)",
    noVotes: "No active votes",
    statusPlenty: "plenty",
    statusFew: "few",
    statusNone: "none",
    displayPlenty: "Plenty",
    displayFew: "Few",
    displayNone: "None",
    displayUnknown: "Unknown",
    totalVotes: "Total",
  },
  zh: {
    title: "寻找大鸡蛋 - 管理页",
    subtitle: "只读看板：显示最近 3 小时内的投票。",
    langLabel: "语言",
    backToMap: "返回地图",
    notice1: "本页面为只读，每 30 秒自动刷新一次。",
    notice2: "倒计时每秒更新，基于浏览器本地时间计算。",
    generatedAt: "生成时间：",
    thMarket: "超市",
    thAddress: "地址",
    thSummary: "汇总",
    thDetails: "有效投票（到期倒计时）",
    noVotes: "暂无有效投票",
    statusPlenty: "大量",
    statusFew: "少量",
    statusNone: "没有",
    displayPlenty: "大量",
    displayFew: "少量",
    displayNone: "没有",
    displayUnknown: "未知",
    totalVotes: "总票数",
  },
  de: {
    title: "Finde Eier der Größe L - Admin",
    subtitle: "Schreibgeschuetzte Uebersicht fuer Stimmen der letzten 3 Stunden.",
    langLabel: "Sprache",
    backToMap: "Zurueck zur Karte",
    notice1: "Diese Seite ist schreibgeschuetzt und aktualisiert sich alle 30 Sekunden.",
    notice2: "Countdowns werden jede Sekunde auf Basis der lokalen Browserzeit aktualisiert.",
    generatedAt: "Erstellt um:",
    thMarket: "Markt",
    thAddress: "Adresse",
    thSummary: "Uebersicht",
    thDetails: "Aktive Stimmen (Ablauf in)",
    noVotes: "Keine aktiven Stimmen",
    statusPlenty: "viele",
    statusFew: "wenige",
    statusNone: "keine",
    displayPlenty: "Viele",
    displayFew: "Wenige",
    displayNone: "Keine",
    displayUnknown: "Unbekannt",
    totalVotes: "Gesamt",
  },
};

let adminLang = "en";
let adminData = null;
let countdownTimer = null;

function ta(key) {
  return ADMIN_I18N[adminLang][key] || ADMIN_I18N.en[key] || key;
}

function setAdminText(id, key) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = ta(key);
  }
}

function formatDuration(seconds) {
  const safe = Math.max(0, seconds);
  const h = Math.floor(safe / 3600);
  const m = Math.floor((safe % 3600) / 60);
  const s = safe % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function localizedStatus(status) {
  if (status === "plenty") {
    return ta("statusPlenty");
  }
  if (status === "few") {
    return ta("statusFew");
  }
  return ta("statusNone");
}

function localizedDisplayStatus(status) {
  if (status === "plenty") {
    return ta("displayPlenty");
  }
  if (status === "few") {
    return ta("displayFew");
  }
  if (status === "none") {
    return ta("displayNone");
  }
  return ta("displayUnknown");
}

function applyAdminLanguage() {
  document.title = ta("title");
  setAdminText("adminTitle", "title");
  setAdminText("adminSubtitle", "subtitle");
  setAdminText("adminLangLabel", "langLabel");
  setAdminText("backToMap", "backToMap");
  setAdminText("adminNotice1", "notice1");
  setAdminText("adminNotice2", "notice2");
  setAdminText("generatedAtLabel", "generatedAt");
  setAdminText("thMarket", "thMarket");
  setAdminText("thAddress", "thAddress");
  setAdminText("thSummary", "thSummary");
  setAdminText("thDetails", "thDetails");
}

async function fetchAdminMarkets() {
  const res = await fetch("/api/admin/markets");
  if (!res.ok) {
    throw new Error("failed to fetch admin markets");
  }
  return res.json();
}

function renderRows(data) {
  const body = document.getElementById("adminTableBody");
  body.innerHTML = "";

  for (const market of data.markets) {
    const tr = document.createElement("tr");

    const tdMarket = document.createElement("td");
    tdMarket.textContent = market.brand;

    const tdAddress = document.createElement("td");
    tdAddress.textContent = market.address;

    const tdSummary = document.createElement("td");
    tdSummary.textContent = `${ta("totalVotes")}=${market.total_votes}, plenty=${market.counts.plenty}, few=${market.counts.few}, none=${market.counts.none}, display=${localizedDisplayStatus(market.display_status)}`;

    const tdDetails = document.createElement("td");
    if (!market.vote_details.length) {
      tdDetails.textContent = ta("noVotes");
    } else {
      const list = document.createElement("ul");
      list.className = "admin-vote-list";

      for (const vote of market.vote_details) {
        const li = document.createElement("li");
        li.dataset.expiresAt = vote.expires_at;
        li.textContent = `${localizedStatus(vote.status)} - ${formatDuration(vote.remaining_seconds)}`;
        list.appendChild(li);
      }
      tdDetails.appendChild(list);
    }

    tr.appendChild(tdMarket);
    tr.appendChild(tdAddress);
    tr.appendChild(tdSummary);
    tr.appendChild(tdDetails);
    body.appendChild(tr);
  }
}

function updateCountdowns() {
  document.querySelectorAll(".admin-vote-list li").forEach((li) => {
    const expiresAt = li.dataset.expiresAt;
    if (!expiresAt) {
      return;
    }
    const remaining = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
    const parts = li.textContent.split(" - ");
    const statusText = parts[0] || "";
    li.textContent = `${statusText} - ${formatDuration(remaining)}`;
  });
}

async function refreshAdminData() {
  adminData = await fetchAdminMarkets();
  const generatedAt = document.getElementById("generatedAtValue");
  generatedAt.textContent = new Date(adminData.generated_at).toLocaleString();
  renderRows(adminData);
  updateCountdowns();
}

function setupLanguage() {
  const select = document.getElementById("adminLanguage");
  select.addEventListener("change", () => {
    adminLang = select.value;
    applyAdminLanguage();
    if (adminData) {
      renderRows(adminData);
      updateCountdowns();
    }
  });
}

async function main() {
  applyAdminLanguage();
  setupLanguage();
  await refreshAdminData();

  if (countdownTimer) {
    clearInterval(countdownTimer);
  }
  countdownTimer = setInterval(updateCountdowns, 1000);
  setInterval(() => {
    refreshAdminData().catch(() => undefined);
  }, 30000);
}

main().catch(() => {
  const body = document.getElementById("adminTableBody");
  body.innerHTML = '<tr><td colspan="4">Failed to load admin data.</td></tr>';
});
