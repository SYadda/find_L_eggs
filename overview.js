const ADMIN_I18N = {
  en: {
    title: "Find L Eggs - Overview",
    subtitle: "Single-click a supermarket address to copy it; double-click to open it on the map.",
    langLabel: "Language",
    backToMap: "Back to map",
    generatedAt: "Generated at:",
    currentCity: "Current city:",
    nearbyCities: "Nearby cities:",
    thMarket: "Market",
    thAddress: "Address",
    thSummary: "Summary",
    thDetails: "Active votes (expires in)",
    noVotes: "No active votes",
    noValidData: "No valid data yet",
    showAll: "Show all supermarkets",
    statusPlenty: "plenty",
    statusFew: "few",
    statusNone: "none",
    totalVotes: "Total",
    copied: "Address copied",
    loadFailed: "Failed to load overview data.",
  },
  zh: {
    title: "寻找大鸡蛋 - 概览页",
    subtitle: "单击超市地址可复制到剪贴板；双击可跳转到地图并打开该超市。",
    langLabel: "语言",
    backToMap: "返回地图",
    generatedAt: "生成时间：",
    currentCity: "当前城市：",
    nearbyCities: "临近城市：",
    thMarket: "超市",
    thAddress: "地址",
    thSummary: "汇总",
    thDetails: "有效投票（到期倒计时）",
    noVotes: "暂无有效投票",
    noValidData: "暂无有效数据",
    showAll: "查看全部超市",
    statusPlenty: "大量",
    statusFew: "少量",
    statusNone: "没有",
    totalVotes: "总票数",
    copied: "地址已复制",
    loadFailed: "概览数据加载失败。",
  },
  de: {
    title: "Finde Eier der Größe L - Übersicht",
    subtitle: "Adresse einmal klicken zum Kopieren; doppelklicken, um zur Karte zu springen und den Markt zu oeffnen.",
    langLabel: "Sprache",
    backToMap: "Zurueck zur Karte",
    generatedAt: "Erstellt um:",
    currentCity: "Aktuelle Stadt:",
    nearbyCities: "Nahe Städte:",
    thMarket: "Markt",
    thAddress: "Adresse",
    thSummary: "Uebersicht",
    thDetails: "Aktive Stimmen (Ablauf in)",
    noVotes: "Keine aktiven Stimmen",
    noValidData: "Noch keine gueltigen Daten",
    showAll: "Alle Supermaerkte anzeigen",
    statusPlenty: "viele",
    statusFew: "wenige",
    statusNone: "keine",
    totalVotes: "Gesamt",
    copied: "Adresse kopiert",
    loadFailed: "Uebersichtsdaten konnten nicht geladen werden.",
  },
};

const MAP_VIEW_STORAGE_KEY = "find_l_eggs_map_view";
const FALLBACK_CENTER = { lat: 49.5972, lon: 11.0045 };

let adminLang = "en";
let adminData = null;
let countdownTimer = null;
let includeAll = false;

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

function applyAdminLanguage() {
  document.title = ta("title");
  setAdminText("adminTitle", "title");
  setAdminText("adminSubtitle", "subtitle");
  setAdminText("adminLangLabel", "langLabel");
  setAdminText("backToMap", "backToMap");
  setAdminText("generatedAtLabel", "generatedAt");
  setAdminText("currentCityLabel", "currentCity");
  setAdminText("nearbyCitiesLabel", "nearbyCities");
  setAdminText("thMarket", "thMarket");
  setAdminText("thAddress", "thAddress");
  setAdminText("thSummary", "thSummary");
  setAdminText("thDetails", "thDetails");
  setAdminText("showAllBtn", "showAll");
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

function setMapCenter(lat, lon) {
  localStorage.setItem(MAP_VIEW_STORAGE_KEY, JSON.stringify({ lat, lon }));
}

async function openNearbyCity(city) {
  if (!city) {
    return;
  }
  includeAll = false;
  setMapCenter(city.lat, city.lon);
  await refreshAdminData();
}

function loadMapCenter() {
  try {
    const raw = localStorage.getItem(MAP_VIEW_STORAGE_KEY);
    if (!raw) {
      return FALLBACK_CENTER;
    }
    const parsed = JSON.parse(raw);
    const lat = Number(parsed?.lat);
    const lon = Number(parsed?.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      return FALLBACK_CENTER;
    }
    return { lat, lon };
  } catch (_err) {
    return FALLBACK_CENTER;
  }
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

async function fetchOverviewMarkets() {
  const center = loadMapCenter();
  const res = await fetch("/api/overview/markets", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      lat: center.lat,
      lon: center.lon,
      include_all: includeAll,
    }),
  });
  if (!res.ok) {
    throw new Error("failed to fetch overview markets");
  }
  return res.json();
}

function renderNearbyCities(data) {
  const wrap = document.getElementById("nearbyCitiesWrap");
  const buttons = document.getElementById("nearbyCityButtons");
  if (!wrap || !buttons) {
    return;
  }

  buttons.innerHTML = "";
  const nearbyCities = Array.isArray(data?.nearby_cities) ? data.nearby_cities : [];
  if (!nearbyCities.length) {
    wrap.style.display = "none";
    return;
  }

  wrap.style.display = "inline-flex";
  for (const city of nearbyCities) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "city-btn nearby-city-btn";
    btn.textContent = city.city;
    btn.title = `${city.city} (${city.distance_km} km)`;
    btn.addEventListener("click", () => {
      openNearbyCity(city).catch(() => undefined);
    });
    buttons.appendChild(btn);
  }
}

function renderRows(data) {
  const body = document.getElementById("adminTableBody");
  body.innerHTML = "";

  const markets = [...data.markets].sort((a, b) => {
    const priorityDelta = statusPriority(a.display_status) - statusPriority(b.display_status);
    if (priorityDelta !== 0) {
      return priorityDelta;
    }
    return b.total_votes - a.total_votes;
  });

  for (const market of markets) {
    const tr = document.createElement("tr");

    const tdMarket = document.createElement("td");
    tdMarket.textContent = market.brand;

    const tdAddress = document.createElement("td");
    tdAddress.textContent = market.address;
    tdAddress.className = "admin-address";
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
    tdSummary.textContent = `${ta("totalVotes") }=${market.total_votes}, ${localizedStatus("plenty") }=${market.counts.plenty}, ${localizedStatus("few") }=${market.counts.few}, ${localizedStatus("none") }=${market.counts.none}`;

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

  if (!markets.length) {
    const emptyRow = document.createElement("tr");
    const emptyCell = document.createElement("td");
    emptyCell.colSpan = 4;
    emptyCell.textContent = includeAll ? ta("noVotes") : ta("noValidData");
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

function renderMeta(data) {
  const generatedAt = document.getElementById("generatedAtValue");
  generatedAt.textContent = new Date(data.generated_at).toLocaleString();

  const cityValue = document.getElementById("currentCityValue");
  cityValue.textContent = data.city || "-";

  renderNearbyCities(data);

  const showAllBtn = document.getElementById("showAllBtn");
  showAllBtn.style.display = includeAll ? "none" : "inline-block";
  showAllBtn.classList.toggle("active", includeAll);
  showAllBtn.setAttribute("aria-pressed", includeAll ? "true" : "false");
}

async function refreshAdminData() {
  adminData = await fetchOverviewMarkets();
  renderMeta(adminData);
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
        renderMeta(adminData);
        renderRows(adminData);
        updateCountdowns();
      }
    });
  });
}

function setupShowAllButton() {
  const btn = document.getElementById("showAllBtn");
  btn.addEventListener("click", async () => {
    includeAll = true;
    btn.classList.add("active");
    btn.setAttribute("aria-pressed", "true");
    await refreshAdminData();
  });
}

async function main() {
  applyAdminLanguage();
  setupLanguage();
  setupShowAllButton();
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
  body.innerHTML = `<tr><td colspan="4">${ta("loadFailed")}</td></tr>`;
});