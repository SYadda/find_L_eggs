const STATUS_COLORS = {
  plenty: "#2fa84f",
  plenty_light: "#9ed8aa",
  few: "#f0ba1f",
  few_light: "#f5dea0",
  none: "#db3a34",
  none_light: "#efada9",
  unknown: "#8d8d8d",
};

const I18N = {
  en: {
    title: "Find L Eggs",
    tagline: "Help people with tighter budgets get larger eggs.",
    repoNote: "Source code on",
    langLabel: "Language",
    adminLink: "Open overview",
    description1:
      "Please only upload eggs priced at or below 2.49€/10 or 4.19€/18. This is usually supermarket-own-brand barn eggs (Bodenhaltung). We are not tracking expensive eggs.",
    description2:
      "All data comes from recent user uploads. The best way to support us is to keep uploading fresh data!",
    legendPlenty: "Plenty of L eggs",
    legendFew: "Few L eggs",
    legendNone: "No L eggs",
    legendUnknown: "Not enough information",
    votePrompt: "What did you see at this supermarket?",
    votePlenty: "Plenty",
    voteFew: "Few",
    voteNone: "None",
    counts: "Votes",
    duplicateVote:
      "You already voted the same status for this market within 1 hour.",
    voteOk: "Vote submitted.",
    voteError: "Vote failed. Please try again.",
    noGeo: "No coordinates available for this market.",
    thresholdTip: "Gray means no status reached threshold.",
  },
  zh: {
    title: "寻找大鸡蛋",
    tagline: "帮助预算紧张的人买到更大的鸡蛋。",
    repoNote: "开源项目，代码见",
    langLabel: "语言",
    adminLink: "打开概览页",
    description1:
      "请仅上传价格小于等于 2.49€/10 个或 4.19€/18 个的鸡蛋信息。这通常是超市自有品牌的 Bodenhaltung 鸡蛋。我们不关注昂贵鸡蛋。",
    description2: "所有数据均来自近期用户上传。对我们最好的支持，就是持续上传最新数据！",
    legendPlenty: "大量 L 号鸡蛋",
    legendFew: "少量 L 号鸡蛋",
    legendNone: "没有 L 号鸡蛋",
    legendUnknown: "信息不足",
    votePrompt: "你在此超市看到的情况如何？",
    votePlenty: "大量",
    voteFew: "少量",
    voteNone: "没有",
    counts: "票数",
    duplicateVote: "1 小时内你已对该超市投过同样状态。",
    voteOk: "投票成功。",
    voteError: "投票失败，请稍后重试。",
    noGeo: "该超市暂无坐标。",
    thresholdTip: "灰色代表票数未达到阈值。",
  },
  de: {
    title: "Finde Eier der Größe L",
    tagline: "Hilft Menschen mit kleinem Budget, groessere Eier zu finden.",
    repoNote: "Quellcode auf",
    langLabel: "Sprache",
    adminLink: "Uebersicht öffnen",
    description1:
      "Bitte melde nur Eier mit einem Preis von höchstens 2,49€/10 oder 4,19€/18. Das sind in der Regel Eigenmarken-Bodenhaltungseier. Teure Eier werden hier nicht erfasst.",
    description2:
      "Alle Daten stammen aus aktuellen Nutzer-Meldungen. Die beste Unterstützung ist, weiterhin frische Daten hochzuladen!",
    legendPlenty: "Viele L-Eier",
    legendFew: "Wenige L-Eier",
    legendNone: "Keine L-Eier",
    legendUnknown: "Zu wenig Informationen",
    votePrompt: "Wie ist die Situation in diesem Supermarkt?",
    votePlenty: "Viel",
    voteFew: "Wenig",
    voteNone: "Keine",
    counts: "Stimmen",
    duplicateVote:
      "Du hast fuer diesen Markt in der letzten Stunde schon denselben Status abgestimmt.",
    voteOk: "Stimme gesendet.",
    voteError: "Abstimmung fehlgeschlagen. Bitte erneut versuchen.",
    noGeo: "Keine Koordinaten fuer diesen Markt verfuegbar.",
    thresholdTip: "Grau bedeutet: Kein Status hat den Schwellwert erreicht.",
  },
};

let currentLang = "en";
const markerMap = new Map();
let map;
let initialViewport = null;

const MAP_VIEW_STORAGE_KEY = "find_l_eggs_map_view";

function loadSavedViewport() {
  try {
    const raw = localStorage.getItem(MAP_VIEW_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    const lat = Number(parsed?.lat);
    const lon = Number(parsed?.lon);
    const zoom = Number(parsed?.zoom);

    const validLat = Number.isFinite(lat) && lat >= -90 && lat <= 90;
    const validLon = Number.isFinite(lon) && lon >= -180 && lon <= 180;
    const validZoom = Number.isFinite(zoom) && zoom >= 1 && zoom <= 19;
    if (!validLat || !validLon || !validZoom) {
      return null;
    }

    return {
      lat,
      lon,
      zoom,
    };
  } catch (_err) {
    return null;
  }
}

function saveCurrentViewport() {
  if (!map) {
    return;
  }
  try {
    const center = map.getCenter();
    const payload = {
      lat: Number(center.lat.toFixed(6)),
      lon: Number(center.lng.toFixed(6)),
      zoom: map.getZoom(),
    };
    localStorage.setItem(MAP_VIEW_STORAGE_KEY, JSON.stringify(payload));
  } catch (_err) {
    // Ignore storage errors (e.g. private mode or disabled storage).
  }
}

function focusedMarketIdFromQuery() {
  const raw = new URLSearchParams(window.location.search).get("focusMarket");
  if (!raw) {
    return null;
  }
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function focusMarketFromQuery() {
  const marketId = focusedMarketIdFromQuery();
  if (!marketId) {
    return;
  }
  const marker = markerMap.get(marketId);
  if (!marker) {
    return;
  }
  const latLng = marker.getLatLng();
  map.setView(latLng, Math.max(map.getZoom(), 15), { animate: true });
  marker.openPopup();
}

function t(key) {
  return I18N[currentLang][key] || I18N.en[key] || key;
}

function setText(id, key) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = t(key);
  }
}

function applyLanguage() {
  document.title = t("title");
  setText("title", "title");
  setText("taglineText", "tagline");
  setText("repoNoteText", "repoNote");
  setText("langLabel", "langLabel");
  setText("adminLink", "adminLink");
  setText("description1", "description1");
  setText("description2", "description2");
  setText("legendPlenty", "legendPlenty");
  setText("legendFew", "legendFew");
  setText("legendNone", "legendNone");
  setText("legendUnknown", "legendUnknown");

  document.querySelectorAll(".lang-btn").forEach((btn) => {
    const isActive = btn.dataset.lang === currentLang;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function markerStyle(status) {
  return {
    radius: 8,
    color: "#1d1d1d",
    weight: 1,
    fillColor: STATUS_COLORS[status] || STATUS_COLORS.unknown,
    fillOpacity: 0.92,
  };
}

function popupHtml(market) {
  const c = market.counts;
  return `
    <div class="popup" data-market-id="${market.id}">
      <h3>${market.brand}</h3>
      <p class="address">${market.address}</p>
      <p class="vote-prompt">${t("votePrompt")}</p>
      <div class="vote-row">
        <button class="vote-btn plenty" data-status="plenty">${t("votePlenty")}</button>
        <button class="vote-btn few" data-status="few">${t("voteFew")}</button>
        <button class="vote-btn none" data-status="none">${t("voteNone")}</button>
      </div>
      <div class="counts">
        ${t("counts")}: ${t("votePlenty")}=${c.plenty}, ${t("voteFew")}=${c.few}, ${t("voteNone")}=${c.none}
      </div>
    </div>
  `;
}

function updateMarker(market) {
  const marker = markerMap.get(market.id);
  if (!marker) {
    return;
  }
  marker.setStyle(markerStyle(market.display_status));
  marker.bindPopup(popupHtml(market));
}

function showToast(text) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = text;
  toast.classList.add("show");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("show"), 1800);
}

async function fetchMarkets() {
  const res = await fetch("/api/markets");
  if (!res.ok) {
    throw new Error("failed to fetch markets");
  }
  return res.json();
}

async function postVote(marketId, status) {
  const res = await fetch("/api/vote", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ market_id: marketId, status }),
  });
  const data = await res.json();
  if (!res.ok) {
    const err = new Error(data.error || "vote failed");
    err.payload = data;
    err.status = res.status;
    throw err;
  }
  return data;
}

function attachPopupVoteHandler() {
  map.on("popupopen", (e) => {
    const root = e.popup.getElement();
    if (!root) {
      return;
    }

    root.querySelectorAll(".vote-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const popup = btn.closest(".popup");
        if (!popup) {
          return;
        }
        const marketId = Number(popup.dataset.marketId);
        const status = btn.dataset.status;

        try {
          const data = await postVote(marketId, status);
          updateMarker(data.market);
          showToast(t("voteOk"));
        } catch (err) {
          if (err.status === 409) {
            showToast(t("duplicateVote"));
          } else {
            showToast(t("voteError"));
          }
        }
      });
    });
  });
}

function initMap() {
  initialViewport = loadSavedViewport();
  const center = initialViewport ? [initialViewport.lat, initialViewport.lon] : [49.5972, 11.0045];
  const zoom = initialViewport ? initialViewport.zoom : 12.5;

  map = L.map("map", {
    center,
    zoom,
  });

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  map.on("moveend zoomend", saveCurrentViewport);
}

async function renderMarkets() {
  const markets = await fetchMarkets();
  const bounds = [];

  for (const market of markets) {
    if (typeof market.lat !== "number" || typeof market.lon !== "number") {
      continue;
    }

    const marker = L.circleMarker([market.lat, market.lon], markerStyle(market.display_status))
      .addTo(map)
      .bindPopup(popupHtml(market));

    markerMap.set(market.id, marker);
    bounds.push([market.lat, market.lon]);
  }

  const hasFocusMarket = Boolean(focusedMarketIdFromQuery());
  if (!initialViewport && !hasFocusMarket && bounds.length > 0) {
    map.fitBounds(bounds, { padding: [18, 18] });
  }

  focusMarketFromQuery();
}

function setupLanguageSwitcher() {
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      currentLang = btn.dataset.lang || "en";
      applyLanguage();
      // Re-bind popup text for currently loaded markers.
      fetchMarkets()
        .then((markets) => markets.forEach((m) => updateMarker(m)))
        .catch(() => undefined);
    });
  });
}

async function main() {
  applyLanguage();
  setupLanguageSwitcher();
  initMap();
  attachPopupVoteHandler();
  await renderMarkets();
}

main().catch(() => {
  showToast("Failed to load map data.");
});
