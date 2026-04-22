const ADMIN_I18N = {
  en: {
    title: "Find L Eggs - Overview",
    subtitle: "Single-click a supermarket address to copy it; double-click to open it on the map.",
    langLabel: "Language",
    backToMap: "Back to map",
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
    copied: "Address copied",
  },
  zh: {
    title: "寻找大鸡蛋 - 概览页",
    subtitle: "单击超市地址可复制到剪贴板；双击可跳转到地图并打开该超市。",
    langLabel: "语言",
    backToMap: "返回地图",
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
    copied: "地址已复制",
  },
  de: {
    title: "Finde Eier der Größe L - Übersicht",
    subtitle: "Adresse einmal klicken zum Kopieren; doppelklicken, um zur Karte zu springen und den Markt zu oeffnen.",
    langLabel: "Sprache",
    backToMap: "Zurueck zur Karte",
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
    copied: "Adresse kopiert",
  },
};

let adminLang = "en";
let adminData = null;
let countdownTimer = null;
let currentCity = "Erlangen";

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
  if (status === "plenty" || status === "plenty_light") {
    return ta("displayPlenty");
  }
  if (status === "few" || status === "few_light") {
    return ta("displayFew");
  }
  if (status === "none" || status === "none_light") {
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
  setAdminText("generatedAtLabel", "generatedAt");
  setAdminText("thMarket", "thMarket");
  setAdminText("thAddress", "thAddress");
  setAdminText("thSummary", "thSummary");
  setAdminText("thDetails", "thDetails");
}

function statusPriority(displayStatus) {
  if (displayStatus === "plenty" || displayStatus === "plenty_light") {
    return 0;
  }
  if (displayStatus === "few" || displayStatus === "few_light") {
    return 1;
  }
  if (displayStatus === "none" || displayStatus === "none_light") {
    return 2;
  }
  return 3;
}

function openMarketOnMap(marketId) {
  const url = new URL("/", window.location.origin);
  url.searchParams.set("focusMarket", String(marketId));
  window.location.href = url.toString();
}

async function copyAddress(text) {
  if (!text) {
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "readonly");
  area.style.position = "absolute";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  document.body.removeChild(area);
}

function applyCityButtonsState() {
  document.querySelectorAll(".city-btn").forEach((btn) => {
    const isActive = btn.dataset.city === currentCity;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function showAdminToast(text) {
  let toast = document.querySelector(".admin-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "admin-toast";
    document.body.appendChild(toast);
  }
  toast.textContent = text;
  toast.style.position = "fixed";
  toast.style.left = "50%";
  toast.style.bottom = "20px";
  toast.style.transform = "translateX(-50%)";
  toast.style.background = "rgba(20, 20, 20, 0.9)";
  toast.style.color = "#fff";
  toast.style.padding = "8px 12px";
  toast.style.borderRadius = "10px";
  toast.style.fontSize = "13px";
  toast.style.zIndex = "9999";
  toast.style.opacity = "1";
  toast.style.transition = "opacity 0.2s ease";

  clearTimeout(showAdminToast.timer);
  showAdminToast.timer = setTimeout(() => {
    toast.style.opacity = "0";
  }, 1200);
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

  const marketsInCity = data.markets
    .filter((market) => market.city === currentCity)
    .sort((a, b) => {
      const priorityDelta = statusPriority(a.display_status) - statusPriority(b.display_status);
      if (priorityDelta !== 0) {
        return priorityDelta;
      }
      return b.total_votes - a.total_votes;
    });

  for (const market of marketsInCity) {
    const tr = document.createElement("tr");

    const tdMarket = document.createElement("td");
    tdMarket.textContent = market.brand;

    const tdAddress = document.createElement("td");
    tdAddress.textContent = market.address;
    tdAddress.className = "admin-address";
    tdAddress.title = ta("notice1");
    tdAddress.style.cursor = "pointer";
    tdAddress.addEventListener("click", () => {
      copyAddress(market.address)
        .then(() => showAdminToast(ta("copied")))
        .catch(() => undefined);
    });
    tdAddress.addEventListener("dblclick", () => {
      openMarketOnMap(market.id);
    });

    const tdSummary = document.createElement("td");
    tdSummary.textContent = `${ta("totalVotes")}=${market.total_votes}, ${localizedStatus("plenty")}=${market.counts.plenty}, ${localizedStatus("few")}=${market.counts.few}, ${localizedStatus("none")}=${market.counts.none}`;

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

  if (!marketsInCity.length) {
    const emptyRow = document.createElement("tr");
    const emptyCell = document.createElement("td");
    emptyCell.colSpan = 4;
    emptyCell.textContent = ta("noVotes");
    emptyRow.appendChild(emptyCell);
    body.appendChild(emptyRow);
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
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      adminLang = btn.dataset.lang || "en";
      applyAdminLanguage();

      document.querySelectorAll(".lang-btn").forEach((otherBtn) => {
        const isActive = otherBtn.dataset.lang === adminLang;
        otherBtn.classList.toggle("active", isActive);
        otherBtn.setAttribute("aria-pressed", isActive ? "true" : "false");
      });

      if (adminData) {
        renderRows(adminData);
        updateCountdowns();
      }
    });
  });
}

function setupCityNavigation() {
  applyCityButtonsState();
  document.querySelectorAll(".city-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentCity = btn.dataset.city || "Erlangen";
      applyCityButtonsState();
      if (adminData) {
        renderRows(adminData);
        updateCountdowns();
      }
    });
  });
}

async function main() {
  applyAdminLanguage();
  setupLanguage();
  setupCityNavigation();
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
  body.innerHTML = '<tr><td colspan="4">Failed to load overview data.</td></tr>';
});