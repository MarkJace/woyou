import { WoyouMap } from "./map.js";
import { WeatherOverlays } from "./overlays.js";

const $ = (id) => document.getElementById(id);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(`woyou.${key}`);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`woyou.${key}`, JSON.stringify(value));
    } catch {
      /* 忽略隐私模式下的写入失败 */
    }
  },
};

const GLYPHS = {
  streets: "街",
  satellite: "卫",
  terrain: "形",
  cloudless: "云",
  clouds: "云",
  radar: "雷",
  temp: "温",
  wind: "风",
  air: "气",
  street: "景",
  default: "图",
};

const state = {
  config: null,
  sources: [],
  base: store.get("base", null),
  composite: store.get("composite", false),
  baseExtras: new Set(store.get("baseExtras", []) || []),
  compositeOpacity: store.get("compositeOpacity", 0.55),
  units: store.get("units", "metric"),
  theme: store.get("theme", "light"),
  follow: store.get("follow", false),
  opacity: store.get("opacity", 0.6),
  speed: store.get("speed", "normal"),
  map: null,
  weather: null,
  weatherLabel: "",
  selected: null,
  weatherActive: new Set(),
  envActive: new Set(),
  overlays: null,
  streetview: false,
  svImages: [],
  svIndex: 0,
  svTimer: null,
  svGuard: 0,
  svAutoOpened: false,
  svFailed: new Set(),
  requestId: 0,
  followTimer: null,
  pendingTarget: null,
  radar: {
    enabled: false,
    meta: null,
    frames: [],
    host: "",
    index: 0,
    playing: false,
    timer: null,
  },
};

/* ------------------------------------------------------------------ */
/* 图标                                                                */
/* ------------------------------------------------------------------ */
const COLORS = {
  sun: "#f6a821",
  cloud: "#f3f8ff",
  cloudStroke: "#94a3b6",
  rain: "#2f80ed",
  snow: "#7fb6e8",
  bolt: "#f2b01e",
};

const CLOUD_PATH =
  "M18 47h26a9 9 0 0 0 0-18 13 13 0 0 0-24-2 9 9 0 0 0-2 20Z";

function cloud(fill = COLORS.cloud) {
  return `<path d="${CLOUD_PATH}" fill="${fill}" stroke="${COLORS.cloudStroke}" stroke-width="2"/>`;
}

function sun(cx = 24, cy = 24, r = 9) {
  const rays = [
    [cx, cy - r - 5, cx, cy - r - 10],
    [cx, cy + r + 5, cx, cy + r + 10],
    [cx - r - 5, cy, cx - r - 10, cy],
    [cx + r + 5, cy, cx + r + 10, cy],
    [cx - 8, cy - 8, cx - 12, cy - 12],
    [cx + 8, cy + 8, cx + 12, cy + 12],
    [cx + 8, cy - 8, cx + 12, cy - 12],
    [cx - 8, cy + 8, cx - 12, cy + 12],
  ]
    .map(
      ([x1, y1, x2, y2]) =>
        `<path d="M${x1} ${y1}L${x2} ${y2}" stroke="${COLORS.sun}" stroke-width="2.4" stroke-linecap="round"/>`
    )
    .join("");
  return `<g><circle cx="${cx}" cy="${cy}" r="${r}" fill="${COLORS.sun}"/>${rays}</g>`;
}

function moon() {
  return `<g><path d="M40 34a14 14 0 1 1-12-20 11 11 0 0 0 12 20Z" fill="#d5e1f0" stroke="#94a3b6" stroke-width="2"/><circle cx="43" cy="15" r="1.6" fill="#c3d2e5"/><circle cx="50" cy="22" r="1.1" fill="#c3d2e5"/></g>`;
}

function rainDrops(count = 3, color = COLORS.rain) {
  const xs = [24, 32, 40, 28, 36];
  return Array.from({ length: count })
    .map(
      (_, i) =>
        `<path d="M${xs[i]} 50c0 0-3 4.2-3 6.2a3 3 0 0 0 6 0c0-2-3-6.2-3-6.2Z" fill="${color}"/>`
    )
    .join("");
}

function snowFlakes() {
  return [22, 32, 42]
    .map(
      (x) =>
        `<g stroke="${COLORS.snow}" stroke-width="1.8" stroke-linecap="round"><path d="M${x} 50v8"/><path d="M${x - 3.5} 52.5l7 3"/><path d="M${x + 3.5} 52.5l-7 3"/></g>`
    )
    .join("");
}

function iconSvg(kind, isDay = true) {
  switch (kind) {
    case "clear":
      return isDay ? sun() : moon();
    case "mostly-clear":
      return `<g>${sun(22, 21, 7)}<g transform="translate(9 13) scale(.82)">${cloud()}</g></g>`;
    case "partly":
      return `<g>${sun(20, 20, 7)}<g transform="translate(8 14) scale(.86)">${cloud()}</g></g>`;
    case "cloudy":
      return `<g><g transform="translate(2 2) scale(.72)">${cloud("#e3ecf7")}</g><g transform="translate(13 15) scale(.82)">${cloud()}</g></g>`;
    case "fog":
      return `<g>${cloud()}<g stroke="${COLORS.cloudStroke}" stroke-width="2.4" stroke-linecap="round"><path d="M16 52h30"/><path d="M21 58h22"/></g></g>`;
    case "drizzle":
      return `<g>${cloud()}${rainDrops(2)}</g>`;
    case "rain":
      return `<g>${cloud()}${rainDrops(3)}</g>`;
    case "showers":
      return `<g>${sun(17, 18, 6)}<g transform="translate(6 12) scale(.9)">${cloud()}</g>${rainDrops(3)}</g>`;
    case "snow":
      return `<g>${cloud()}${snowFlakes()}</g>`;
    case "thunder":
      return `<g>${cloud()}<path d="M33 49l-7 10h6l-3 8 10-12h-6l3-6Z" fill="${COLORS.bolt}" stroke="${COLORS.bolt}" stroke-linejoin="round"/></g>`;
    default:
      return `<g>${cloud()}</g>`;
  }
}

/* ------------------------------------------------------------------ */
/* 初始化                                                              */
/* ------------------------------------------------------------------ */
async function init() {
  applyTheme(state.theme);
  syncUnitButtons();
  bindStaticUI();

  const config = await getJSON("/api/v1/config");
  state.config = config;
  state.sources = config.sources || [];
  const version = $("about-version");
  if (version) version.textContent = config.app?.version || "0.1.0";

  const params = new URLSearchParams(window.location.search);
  const latParam = Number.parseFloat(params.get("lat"));
  const lonParam = Number.parseFloat(params.get("lon"));
  const zoomParam = Number.parseFloat(params.get("zoom"));
  const linkView =
    Number.isFinite(latParam) && Number.isFinite(lonParam)
      ? {
          lat: latParam,
          lon: lonParam,
          zoom: Number.isFinite(zoomParam) ? zoomParam : 12,
        }
      : null;
  const saved = store.get("view", null);
  const view = linkView || saved || config.default_view;
  if (!state.base || !state.sources.some((s) => s.id === state.base)) {
    state.base =
      state.sources.find((s) => s.id === "esri-imagery")?.id ||
      state.sources.find((s) => s.category === "base")?.id;
  }
  const baseParam = params.get("base");
  if (
    baseParam &&
    state.sources.some((source) => source.id === baseParam && source.category === "base")
  ) {
    state.base = baseParam;
  }
  if (params.get("composite") === "1") state.composite = true;
  if (params.get("composite") === "0") state.composite = false;
  const extrasParam = params.get("extras");
  if (extrasParam !== null) {
    state.baseExtras = new Set(
      extrasParam
        .split(",")
        .map((id) => id.trim())
        .filter(Boolean)
    );
  }
  state.baseExtras = new Set(
    [...state.baseExtras].filter(
      (id) =>
        id !== state.base &&
        state.sources.some((source) => source.id === id && source.category === "base")
    )
  );

  initMap(view);
  if (state.composite && state.baseExtras.size) applyComposite();
  state.overlays = new WeatherOverlays(state.map.map, {
    opacity: state.opacity,
    units: state.units,
    onUpdate: renderLegend,
    onError: (message) => toast(message),
  });
  renderLayers();
  bindMapUI();
  applyDeepLink();

  loadWeather(view.lat, view.lon, "");
  loadHealth();
}

function initMap(view) {
  state.map = new WoyouMap("map", {
    sources: state.sources,
    base: state.base,
    center: [view.lon, view.lat],
    zoom: view.zoom,
    onClick: handleMapClick,
    onMoveEnd: handleMoveEnd,
    onMouseMove: handleMouseMove,
    onStreetviewClick: (id) => {
      state.svGuard = Date.now();
      openStreetview(id);
    },
  });
  state.map.ready.then(() => {
    updateStatus();
    updateAttribution();
  });
}

/* ------------------------------------------------------------------ */
/* 图层                                                                */
/* ------------------------------------------------------------------ */
function glyph(icon) {
  return GLYPHS[icon] || GLYPHS.default;
}

function applyDeepLink() {
  const layer = new URLSearchParams(window.location.search).get("layer");
  if (!layer) return;
  const items = [
    ...$$("#env-list .layer-item"),
    ...$$("#streetview-list .layer-item"),
  ];
  const item = items.find((element) => element.dataset.id === layer);
  if (!item) return;
  item.click();
}

function makeLayerItem(source, withSwitch) {
  const item = document.createElement("div");
  item.className = "layer-item";
  item.dataset.id = source.id;

  const icon = document.createElement("div");
  icon.className = "layer-icon";
  icon.textContent = glyph(source.icon || source.id);

  const text = document.createElement("div");
  text.className = "layer-text";
  const strong = document.createElement("strong");
  strong.textContent = source.name;
  const span = document.createElement("span");
  span.textContent = source.description || "";
  text.append(strong, span);

  const control = document.createElement("div");
  control.className = withSwitch ? "layer-switch" : "layer-radio";

  item.append(icon, text, control);
  return item;
}

function renderLayers() {
  renderBaseList();

  const weatherList = $("weather-list");
  weatherList.replaceChildren();
  const radarItem = makeLayerItem(
    {
      id: "radar",
      name: "雷达回波",
      description: "RainViewer · 近 2 小时",
      icon: "radar",
    },
    true
  );
  radarItem.addEventListener("click", () => toggleRadar());
  weatherList.append(radarItem);

  for (const source of state.sources.filter((s) => s.category === "weather")) {
    const item = makeLayerItem(source, true);
    item.addEventListener("click", () => toggleWeatherSource(source.id, item));
    weatherList.append(item);
  }

  const streetviewList = $("streetview-list");
  streetviewList.replaceChildren();
  const streetviewItem = makeLayerItem(
    {
      id: "streetview",
      name: "街景照片",
      description: "KartaView · 点击蓝点查看",
      icon: "street",
    },
    true
  );
  streetviewItem.addEventListener("click", () => toggleStreetview());
  streetviewList.append(streetviewItem);

  const envList = $("env-list");
  envList.replaceChildren();
  const envSources = [
    {
      id: "temperature",
      name: "气温热力图",
      description: "2 米气温 · Open-Meteo",
      icon: "temp",
    },
    {
      id: "wind",
      name: "风场流线",
      description: "10 米风 · 动态流线",
      icon: "wind",
    },
    {
      id: "airquality",
      name: "空气质量",
      description: "US AQI · CAMS",
      icon: "air",
    },
  ];
  for (const env of envSources) {
    const item = makeLayerItem(env, true);
    item.addEventListener("click", () => toggleEnv(env.id, item));
    envList.append(item);
  }

  const slider = $("opacity-slider");
  slider.value = String(Math.round(state.opacity * 100));
  $("opacity-value").textContent = `${Math.round(state.opacity * 100)}%`;
}

function renderBaseList() {
  const baseList = $("base-list");
  baseList.replaceChildren();
  const composite = state.composite;
  for (const source of state.sources.filter((s) => s.category === "base")) {
    const item = makeLayerItem(source, composite);
    const selected =
      source.id === state.base || (composite && state.baseExtras.has(source.id));
    if (selected) item.classList.add("active");
    item.addEventListener("click", () => {
      if (state.composite) toggleCompositeBase(source.id);
      else selectBase(source.id);
    });
    baseList.append(item);
  }
  $("composite-toggle").checked = composite;
  $("composite-controls").classList.toggle("hidden", !composite);
  $("composite-opacity").value = String(Math.round(state.compositeOpacity * 100));
  $("composite-opacity-value").textContent = `${Math.round(state.compositeOpacity * 100)}%`;
}

async function applyComposite() {
  const ids = [state.base, ...state.baseExtras];
  if (state.composite) {
    await state.map.setBaseLayers(state.base, ids, state.compositeOpacity);
  } else {
    await state.map.setBase(state.base);
  }
}

function toggleCompositeBase(id) {
  const selected = new Set([state.base, ...state.baseExtras]);
  if (selected.has(id)) {
    selected.delete(id);
    if (!selected.size) return;
    if (id === state.base) {
      state.base = selected.values().next().value;
    }
  } else {
    selected.add(id);
  }
  state.baseExtras = new Set([...selected].filter((item) => item !== state.base));
  store.set("base", state.base);
  store.set("baseExtras", [...state.baseExtras]);
  applyComposite();
  renderBaseList();
  updateStatus();
  updateAttribution();
}

async function selectBase(id) {
  state.base = id;
  store.set("base", id);
  await state.map.setBase(id);
  renderBaseList();
  updateStatus();
  updateAttribution();
}

async function toggleWeatherSource(id, item) {
  const active = state.weatherActive.has(id);
  if (active) {
    state.weatherActive.delete(id);
    item.classList.remove("active");
    await state.map.setWeatherVisible(id, false);
  } else {
    state.weatherActive.add(id);
    item.classList.add("active");
    await state.map.setWeatherVisible(id, true);
    await state.map.setWeatherOpacity(id, state.opacity);
  }
  updateAttribution();
}

function toggleEnv(id, item) {
  const active = state.envActive.has(id);
  const kind = id === "airquality" ? "air" : id;
  if (active) {
    state.envActive.delete(id);
    item.classList.remove("active");
    if (kind === "wind") state.overlays?.setWind(false);
    else state.overlays?.setKind(kind, false);
  } else {
    if (kind === "temperature" || kind === "air") {
      const other = kind === "temperature" ? "airquality" : "temperature";
      if (state.envActive.has(other)) {
        state.envActive.delete(other);
        $$("#env-list .layer-item").forEach((element) => {
          if (element.dataset.id === other) element.classList.remove("active");
        });
      }
      state.overlays?.setKind(kind, true);
    } else {
      state.overlays?.setWind(true);
    }
    state.envActive.add(id);
    item.classList.add("active");
  }
  renderLegend();
  updateAttribution();
}

function renderLegend() {
  const container = $("layer-legend");
  const info = state.overlays?.legend();
  if (!info) {
    container.classList.add("hidden");
    container.replaceChildren();
    return;
  }
  container.classList.remove("hidden");
  container.replaceChildren();

  const head = document.createElement("div");
  head.className = "legend-head";
  const title = document.createElement("strong");
  title.textContent = info.title;
  const subtitle = document.createElement("span");
  subtitle.textContent = info.subtitle || "";
  head.append(title, subtitle);
  container.append(head);

  if (info.gradient) {
    const bar = document.createElement("div");
    bar.className = "legend-bar";
    bar.style.background = info.gradient;
    const labels = document.createElement("div");
    labels.className = "legend-labels";
    for (const label of info.labels || []) {
      const span = document.createElement("span");
      span.textContent = label;
      labels.append(span);
    }
    container.append(bar, labels);
  }

  if (info.note) {
    const note = document.createElement("div");
    note.className = "legend-note";
    note.textContent = info.note;
    container.append(note);
  }
}

function toggleStreetview() {
  state.streetview = !state.streetview;
  $$("#streetview-list .layer-item").forEach((element) => {
    element.classList.toggle("active", state.streetview);
  });
  $("streetview-btn").classList.toggle("active", state.streetview);
  if (state.streetview) {
    refreshStreetview();
  } else {
    state.svImages = [];
    state.svIndex = 0;
    state.map.clearStreetview();
    $("sv-status").textContent = "KartaView · 未开启";
    closeStreetview();
  }
  updateAttribution();
}

async function refreshStreetview() {
  if (!state.streetview) return;
  const status = $("sv-status");
  if (state.map.getZoom() < 13) {
    state.map.clearStreetview();
    state.svImages = [];
    status.textContent = "请放大到街道级别（z≥13）";
    return;
  }
  const center = state.map.getCenter();
  status.textContent = "正在查找 KartaView 街景…";
  try {
    const data = await getJSON(
      `/api/v1/streetview?lat=${center.lat.toFixed(5)}&lon=${center.lon.toFixed(5)}&radius=500&limit=100`
    );
    if (!state.streetview) return;
    state.svImages = data.images || [];
    state.svFailed.clear();
    await state.map.setStreetview(state.svImages);
    if (state.svImages.length) {
      status.textContent = `KartaView · ${state.svImages.length} 张 · 点击蓝点查看`;
      const autoOpen =
        new URLSearchParams(window.location.search).get("sv") === "1";
      if (autoOpen && !state.svAutoOpened) {
        state.svAutoOpened = true;
        openStreetview(state.svImages[0].id);
      }
    } else {
      status.replaceChildren();
      status.append("500 米内没有街景。");
      const demo = document.createElement("button");
      demo.type = "button";
      demo.className = "ghost-btn";
      demo.textContent = "去柏林看看";
      demo.style.marginLeft = "8px";
      demo.style.padding = "2px 8px";
      demo.style.fontSize = "10px";
      demo.addEventListener("click", () => state.map.flyTo(52.5, 13.4, 16));
      status.append(demo);
    }
  } catch (error) {
    if (state.streetview) status.textContent = "KartaView 接口暂时不可用，请稍后重试";
    toast("街景加载失败，请稍后再试");
    console.error(error);
  }
}

function openStreetview(id) {
  const index = state.svImages.findIndex((image) => image.id === id);
  if (index < 0) return;
  state.svIndex = index;
  $("streetview-modal").classList.remove("hidden");
  showStreetview();
}

function showStreetview() {
  const image = state.svImages[state.svIndex];
  if (!image) return;
  const img = $("sv-image");
  const empty = $("sv-empty");
  img.classList.add("hidden");
  empty.classList.remove("hidden");
  empty.textContent = "正在加载街景图片…";
  img.onload = () => {
    img.classList.remove("hidden");
    empty.classList.add("hidden");
  };
  img.onerror = () => {
    img.classList.add("hidden");
    empty.classList.remove("hidden");
    state.svFailed.add(image.id);
    const remaining = state.svImages.filter((item) => !state.svFailed.has(item.id));
    if (remaining.length) {
      empty.textContent = "这张照片已失效，正在切换下一张…";
      const next = state.svImages.findIndex((item) => !state.svFailed.has(item.id));
      state.svIndex = next;
      setTimeout(() => {
        if (!$("streetview-modal").classList.contains("hidden")) showStreetview();
      }, 700);
    } else {
      empty.textContent = "当前区域没有可用的街景照片";
    }
  };
  img.src = `/api/v1/streetview/image/${encodeURIComponent(image.id)}`;
  const bits = [
    image.captured ? image.captured.slice(0, 10) : null,
    image.is_pano ? "全景照片" : "街道照片",
    image.heading !== null && image.heading !== undefined
      ? `${Math.round(image.heading)}°`
      : null,
    image.distance !== undefined ? `${Math.round(image.distance)} m` : null,
  ].filter(Boolean);
  $("sv-meta").textContent = bits.join(" · ") || "—";
  $("sv-count").textContent = `${state.svIndex + 1} / ${state.svImages.length}`;
}

function closeStreetview() {
  $("streetview-modal").classList.add("hidden");
  const img = $("sv-image");
  img.removeAttribute("src");
  img.classList.add("hidden");
}

function stepStreetview(delta) {
  const total = state.svImages.length;
  if (!total) return;
  for (let step = 1; step <= total; step += 1) {
    const index = (state.svIndex + delta * step + total * total) % total;
    if (!state.svFailed.has(state.svImages[index].id)) {
      state.svIndex = index;
      showStreetview();
      return;
    }
  }
  toast("当前区域没有可用的街景照片");
}

function updateAttribution() {
  const parts = [];
  const baseIds = state.composite ? [state.base, ...state.baseExtras] : [state.base];
  for (const id of baseIds) {
    const source = state.sources.find((item) => item.id === id);
    if (source?.attribution && !parts.includes(source.attribution)) {
      parts.push(source.attribution);
    }
  }
  for (const id of state.weatherActive) {
    if (id === "radar") {
      parts.push("RainViewer");
      continue;
    }
    const source = state.sources.find((s) => s.id === id);
    if (source?.attribution) parts.push(source.attribution);
  }
  if (state.envActive.has("airquality")) parts.push("CAMS / Open-Meteo");
  else if (state.envActive.size) parts.push("Open-Meteo");
  if (state.streetview) parts.push("KartaView contributors");
  $("attribution").textContent = parts.join(" · ");
}

/* ------------------------------------------------------------------ */
/* 雷达                                                                */
/* ------------------------------------------------------------------ */
function radarTileUrl(frame) {
  return `${state.radar.host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`;
}

async function loadRadarMeta() {
  if (state.radar.meta) return state.radar.meta;
  const meta = await getJSON("/api/v1/radar");
  state.radar.meta = meta;
  state.radar.host = meta.host;
  state.radar.frames = meta.frames || [];
  const lastPast = state.radar.frames.reduce(
    (acc, frame, index) => (frame.kind === "past" ? index : acc),
    0
  );
  state.radar.index = lastPast;
  const range = $("radar-range");
  range.max = String(Math.max(0, state.radar.frames.length - 1));
  range.value = String(state.radar.index);
  return meta;
}

async function toggleRadar(force) {
  const next = typeof force === "boolean" ? force : !state.radar.enabled;
  const item = $('[data-id="radar"]');
  if (!next) {
    state.radar.enabled = false;
    state.weatherActive.delete("radar");
    stopRadar();
    $("timeline").classList.add("hidden");
    item?.classList.remove("active");
    await state.map.setRadarVisible(false);
    updateAttribution();
    return;
  }

  try {
    await loadRadarMeta();
  } catch (error) {
    toast("雷达数据加载失败，请稍后再试");
    console.error(error);
    return;
  }
  if (!state.radar.frames.length) {
    toast("当前没有可用的雷达帧");
    return;
  }
  state.radar.enabled = true;
  state.weatherActive.add("radar");
  item?.classList.add("active");
  $("timeline").classList.remove("hidden");
  applyRadarFrame(state.radar.index);
  await state.map.setRadarVisible(
    true,
    radarTileUrl(state.radar.frames[state.radar.index]),
    state.opacity
  );
  updateRadarStatus();
  updateAttribution();
}

function updateRadarStatus() {
  const frames = state.radar.frames;
  const past = frames.filter((f) => f.kind === "past").length;
  const now = frames.length - past;
  const status = $("radar-status");
  if (status) {
    status.textContent = `共 ${frames.length} 帧 · 历史 ${past} 帧 + 预报 ${now} 帧`;
  }
}

function applyRadarFrame(index) {
  const frames = state.radar.frames;
  if (!frames.length) return;
  const safe = Math.max(0, Math.min(index, frames.length - 1));
  state.radar.index = safe;
  const frame = frames[safe];
  $("radar-range").value = String(safe);
  const time = new Date(frame.time * 1000).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  $("radar-time").textContent = time;
  $("radar-mode").textContent = frame.kind === "nowcast" ? "短临预报" : "历史回波";
  state.map.setRadarFrame(radarTileUrl(frame));
}

function speedMs() {
  return { slow: 900, normal: 550, fast: 300 }[state.speed] || 550;
}

function startRadar() {
  if (!state.radar.enabled || state.radar.playing) return;
  state.radar.playing = true;
  $("radar-play").textContent = "⏸";
  state.radar.timer = setInterval(() => {
    const next = (state.radar.index + 1) % state.radar.frames.length;
    applyRadarFrame(next);
  }, speedMs());
}

function stopRadar() {
  state.radar.playing = false;
  $("radar-play").textContent = "▶";
  if (state.radar.timer) {
    clearInterval(state.radar.timer);
    state.radar.timer = null;
  }
}

/* ------------------------------------------------------------------ */
/* 天气                                                                */
/* ------------------------------------------------------------------ */
async function loadWeather(lat, lon, label = "") {
  const requestId = ++state.requestId;
  state.selected = { lat, lon };
  if (label) state.weatherLabel = label;
  const fallback = label || `${lat.toFixed(3)}, ${lon.toFixed(3)}`;
  $("wx-place").textContent = fallback;
  $("wx-sub").textContent = "正在获取天气…";
  $("weather-card").setAttribute("aria-busy", "true");

  try {
    const data = await getJSON(
      `/api/v1/weather?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&units=${state.units}`
    );
    if (requestId !== state.requestId) return;
    state.weather = data;
    renderWeather(data, label);
    if (!label) reverseName(lat, lon, requestId);
  } catch (error) {
    if (requestId === state.requestId) {
      $("wx-sub").textContent = "天气加载失败";
      toast("天气服务暂时不可用");
    }
    console.error(error);
  } finally {
    if (requestId === state.requestId) {
      $("weather-card").removeAttribute("aria-busy");
    }
  }
}

async function reverseName(lat, lon, requestId) {
  try {
    const data = await getJSON(
      `/api/v1/reverse?lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}`
    );
    if (requestId !== state.requestId) return;
    state.weatherLabel = data.label || data.name || "";
    if (state.weatherLabel) $("wx-place").textContent = state.weatherLabel;
  } catch {
    /* 逆地理编码失败时保留坐标 */
  }
}

function roundTemp(value) {
  return value === null || value === undefined ? "—" : `${Math.round(value)}°`;
}

function renderWeather(data, label) {
  const current = data.current || {};
  const units = data.units || {};
  const today = (data.daily || [])[0] || {};
  const name =
    label || state.weatherLabel || `${state.selected?.lat.toFixed(3)}, ${state.selected?.lon.toFixed(3)}`;
  $("wx-place").textContent = name;
  $("wx-sub").textContent = `${data.location?.timezone_abbreviation || data.location?.timezone || ""} · 更新于 ${(current.time || "").slice(11, 16) || "—"}`.replace(
    /^ · /,
    ""
  );
  $("wx-icon").innerHTML = iconSvg(current.icon, current.is_day);
  $("wx-temp").textContent = current.temp === null ? "--" : Math.round(current.temp);
  $("wx-unit").textContent = units.temperature || "°C";
  $("wx-desc").textContent = current.label || "—";
  $("wx-range").textContent = `最高 ${roundTemp(today.temp_max)} / 最低 ${roundTemp(today.temp_min)}`;
  $("wx-feels").textContent = `${roundTemp(current.feels)}`;
  $("wx-humidity").textContent = current.humidity === null ? "—" : `${current.humidity}%`;
  $("wx-wind").textContent = `${current.wind_dir || ""} ${Math.round(current.wind || 0)} ${units.wind || ""}`.trim();
  $("wx-precip").textContent = `${current.precip ?? 0} ${units.precipitation || "mm"}`;
  $("wx-tz").textContent = data.location?.timezone_abbreviation || "";

  renderHourly(data.hourly || []);
  renderDaily(data.daily || []);
}

function renderHourly(hours) {
  const container = $("wx-hourly");
  container.replaceChildren();
  for (const hour of hours.slice(0, 24)) {
    const item = document.createElement("div");
    item.className = "hour-item";
    const time = document.createElement("span");
    time.className = "t";
    time.textContent = (hour.time || "").slice(11, 16);
    const icon = document.createElement("span");
    icon.className = "i";
    icon.innerHTML = iconSvg(hour.icon, true);
    const temp = document.createElement("span");
    temp.className = "v";
    temp.textContent = roundTemp(hour.temp);
    const precip = document.createElement("span");
    precip.className = "p";
    precip.textContent = hour.precip_prob ? `${hour.precip_prob}%` : "";
    item.append(time, icon, temp, precip);
    container.append(item);
  }
}

function formatDay(iso) {
  if (!iso) return "—";
  const date = new Date(`${iso}T00:00:00`);
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  return date.toLocaleDateString("zh-CN", { weekday: "short" });
}

function renderDaily(days) {
  const container = $("wx-daily");
  container.replaceChildren();
  for (const day of days.slice(0, 7)) {
    const row = document.createElement("div");
    row.className = "day-row";
    const name = document.createElement("span");
    name.className = "d";
    name.textContent = formatDay(day.date);
    const icon = document.createElement("span");
    icon.className = "i";
    icon.innerHTML = iconSvg(day.icon, true);
    const rain = document.createElement("span");
    rain.className = "r";
    rain.textContent = day.precip_prob ? `${day.precip_prob}%` : "";
    const temps = document.createElement("span");
    temps.className = "temps";
    const high = document.createElement("b");
    high.textContent = roundTemp(day.temp_max);
    const low = document.createElement("span");
    low.textContent = roundTemp(day.temp_min);
    temps.append(high, low);
    row.append(name, icon, rain, temps);
    container.append(row);
  }
}

/* ------------------------------------------------------------------ */
/* 搜索                                                                */
/* ------------------------------------------------------------------ */
let searchTimer = null;
let searchResults = [];
let searchActive = -1;

async function doSearch(query, autoSelect) {
  if (!query.trim()) return;
  try {
    const data = await getJSON(`/api/v1/search?q=${encodeURIComponent(query.trim())}`);
    searchResults = data.results || [];
    searchActive = -1;
    renderSearchResults(searchResults);
    if (autoSelect && searchResults.length) selectSearchResult(searchResults[0]);
  } catch (error) {
    toast("搜索失败，请稍后重试");
    console.error(error);
  }
}

function renderSearchResults(results) {
  const container = $("search-results");
  container.replaceChildren();
  if (!results.length) {
    container.classList.add("hidden");
    return;
  }
  results.forEach((result, index) => {
    const item = document.createElement("div");
    item.className = "search-item";
    item.dataset.index = String(index);
    item.setAttribute("role", "option");
    const pin = document.createElement("div");
    pin.className = "pin";
    pin.textContent = "⌖";
    const text = document.createElement("div");
    text.className = "txt";
    const title = document.createElement("strong");
    title.textContent = result.name || "未命名地点";
    const meta = document.createElement("span");
    meta.textContent = [result.state, result.country].filter(Boolean).join(" · ") || result.label || "";
    text.append(title, meta);
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = result.type || "地点";
    item.append(pin, text, badge);
    item.addEventListener("click", () => selectSearchResult(result));
    container.append(item);
  });
  container.classList.remove("hidden");
}

function highlightSearch(index) {
  const items = $$("#search-results .search-item");
  items.forEach((item, i) => item.classList.toggle("active", i === index));
  searchActive = index;
}

function hideSearch() {
  $("search-results").classList.add("hidden");
  searchResults = [];
  searchActive = -1;
}

function selectSearchResult(result) {
  hideSearch();
  $("search-input").value = result.name || "";
  state.pendingTarget = { lat: result.lat, lon: result.lon, at: Date.now() };
  state.map.setMarker(result.lat, result.lon);
  const zoom = result.type === "country" ? 5 : 10;
  state.map.flyTo(result.lat, result.lon, zoom);
  loadWeather(result.lat, result.lon, result.label || result.name);
}

/* ------------------------------------------------------------------ */
/* 地图事件                                                            */
/* ------------------------------------------------------------------ */
function handleMapClick(lngLat) {
  if (Date.now() - state.svGuard < 350) return;
  state.map.setMarker(lngLat.lat, lngLat.lng);
  state.weatherLabel = "";
  loadWeather(lngLat.lat, lngLat.lng, "");
}

function handleMoveEnd(center, zoom) {
  updateStatus();
  store.set("view", { lat: center.lat, lon: center.lng, zoom });
  if (state.streetview) {
    clearTimeout(state.svTimer);
    state.svTimer = setTimeout(() => refreshStreetview(), 350);
  }
  if (state.pendingTarget) {
    const fresh = Date.now() - state.pendingTarget.at < 4000;
    state.pendingTarget = null;
    if (fresh) return;
  }
  if (!state.follow) return;
  clearTimeout(state.followTimer);
  state.followTimer = setTimeout(() => {
    state.weatherLabel = "";
    loadWeather(center.lat, center.lng, "");
  }, 900);
}

function handleMouseMove(lngLat) {
  if (state._coordFrame) return;
  state._coordFrame = requestAnimationFrame(() => {
    state._coordFrame = null;
    $("status-coords").textContent = formatCoords(lngLat.lat, lngLat.lng);
  });
}

function formatCoords(lat, lon) {
  return `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(4)}°${lon >= 0 ? "E" : "W"}`;
}

function updateStatus() {
  if (!state.map) return;
  const center = state.map.getCenter();
  $("status-coords").textContent = formatCoords(center.lat, center.lon);
  $("status-zoom").textContent = `z ${state.map.getZoom().toFixed(1)}`;
  const base = state.sources.find((s) => s.id === state.base);
  const extraCount = state.composite ? state.baseExtras.size : 0;
  $("status-source").textContent = base
    ? `${base.name}${extraCount ? ` +${extraCount}` : ""}`
    : "";
}

async function loadHealth() {
  const el = $("status-health");
  try {
    const data = await getJSON("/api/v1/health");
    const sources = data.sources || [];
    const ok = sources.filter((s) => s.ok).length;
    el.className = `health ${ok === sources.length ? "ok" : ok > 0 ? "" : "bad"}`;
    el.innerHTML = `<i></i>${ok}/${sources.length} 源可用`;
    const bad = sources.filter((s) => !s.ok);
    el.title = bad.length
      ? `不可用：${bad.map((s) => s.id).join(", ")}`
      : "所有数据源正常";
  } catch {
    el.className = "health bad";
    el.innerHTML = "<i></i>健康检查失败";
  }
}

/* ------------------------------------------------------------------ */
/* 设置与主题                                                          */
/* ------------------------------------------------------------------ */
function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  const select = $("theme-select");
  if (select) select.value = theme;
  store.set("theme", theme);
}

function syncUnitButtons() {
  $$("[data-unit]").forEach((button) => {
    button.classList.toggle("active", button.dataset.unit === state.units);
  });
}

function setUnits(units) {
  state.units = units;
  store.set("units", units);
  syncUnitButtons();
  state.overlays?.setUnits(units);
  renderLegend();
  if (state.selected) {
    loadWeather(state.selected.lat, state.selected.lon, state.weatherLabel);
  }
}

async function loadStats() {
  const info = $("cache-info");
  info.textContent = "正在读取…";
  try {
    const data = await getJSON("/api/v1/stats");
    info.textContent = `已缓存 ${data.total_tiles} 张瓦片 · ${formatBytes(data.total_bytes)}`;
  } catch {
    info.textContent = "缓存信息读取失败";
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function openSettings() {
  $("settings-modal").classList.remove("hidden");
  $("theme-select").value = state.theme;
  $("follow-toggle").checked = state.follow;
  $("speed-select").value = state.speed;
  loadStats();
}

function closeSettings() {
  $("settings-modal").classList.add("hidden");
}

/* ------------------------------------------------------------------ */
/* 杂项                                                                */
/* ------------------------------------------------------------------ */
function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.add("hidden"), 3200);
}

function randomPlace() {
  const lat = -55 + Math.random() * 125;
  const lon = -180 + Math.random() * 360;
  state.weatherLabel = "";
  state.map.setMarker(lat, lon);
  state.map.flyTo(lat, lon, 5);
  loadWeather(lat, lon, "");
}

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || body.message || message;
    } catch {
      /* 忽略非 JSON 错误体 */
    }
    throw new Error(message);
  }
  return response.json();
}

/* ------------------------------------------------------------------ */
/* 事件绑定                                                            */
/* ------------------------------------------------------------------ */
function bindStaticUI() {
  $("search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = $("search-input").value;
    if (query.trim()) doSearch(query, true);
  });

  $("search-input").addEventListener("input", (event) => {
    const query = event.target.value.trim();
    clearTimeout(searchTimer);
    if (query.length < 2) {
      hideSearch();
      return;
    }
    searchTimer = setTimeout(() => doSearch(query, false), 320);
  });

  $("search-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (searchResults.length) highlightSearch((searchActive + 1) % searchResults.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (searchResults.length) {
        highlightSearch((searchActive - 1 + searchResults.length) % searchResults.length);
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (searchActive >= 0 && searchResults[searchActive]) {
        selectSearchResult(searchResults[searchActive]);
      } else if (searchResults.length) {
        selectSearchResult(searchResults[0]);
      } else {
        doSearch(event.target.value, true);
      }
    } else if (event.key === "Escape") {
      hideSearch();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-wrap")) hideSearch();
  });

  $$("[data-unit]").forEach((button) => {
    button.addEventListener("click", () => setUnits(button.dataset.unit));
  });

  $("streetview-btn").addEventListener("click", () => toggleStreetview());
  $("sv-close").addEventListener("click", closeStreetview);
  $("sv-prev").addEventListener("click", () => stepStreetview(-1));
  $("sv-next").addEventListener("click", () => stepStreetview(1));
  $("streetview-modal").addEventListener("click", (event) => {
    if (event.target === $("streetview-modal")) closeStreetview();
  });

  $("theme-btn").addEventListener("click", () => {
    applyTheme(state.theme === "light" ? "dark" : "light");
  });

  $("settings-btn").addEventListener("click", openSettings);
  $("settings-close").addEventListener("click", closeSettings);
  $("settings-modal").addEventListener("click", (event) => {
    if (event.target === $("settings-modal")) closeSettings();
  });
  $("theme-select").addEventListener("change", (event) => applyTheme(event.target.value));
  $("follow-toggle").addEventListener("change", (event) => {
    state.follow = event.target.checked;
    store.set("follow", state.follow);
  });
  $("speed-select").addEventListener("change", (event) => {
    state.speed = event.target.value;
    store.set("speed", state.speed);
    if (state.radar.playing) {
      stopRadar();
      startRadar();
    }
  });
  $("cache-refresh").addEventListener("click", loadStats);
  $("wx-refresh").addEventListener("click", () => {
    if (state.selected) {
      loadWeather(state.selected.lat, state.selected.lon, state.weatherLabel);
    }
  });

  $("layers-btn").addEventListener("click", () => {
    $("layer-panel").classList.toggle("open");
  });
  $("close-layers").addEventListener("click", () => {
    $("layer-panel").classList.remove("open");
  });

  $("composite-toggle").addEventListener("change", (event) => {
    state.composite = event.target.checked;
    store.set("composite", state.composite);
    if (!state.composite) {
      state.baseExtras.clear();
      store.set("baseExtras", []);
    }
    applyComposite();
    renderBaseList();
    updateStatus();
    updateAttribution();
  });

  $("composite-opacity").addEventListener("input", (event) => {
    const value = Number(event.target.value) / 100;
    state.compositeOpacity = value;
    store.set("compositeOpacity", value);
    $("composite-opacity-value").textContent = `${Math.round(value * 100)}%`;
    if (state.composite) state.map.setBaseOpacity(value);
  });

  $("opacity-slider").addEventListener("input", (event) => {
    const value = Number(event.target.value) / 100;
    state.opacity = value;
    store.set("opacity", value);
    $("opacity-value").textContent = `${Math.round(value * 100)}%`;
    if (state.radar.enabled) state.map.setRadarOpacity(value);
    for (const id of state.weatherActive) {
      if (id !== "radar") state.map.setWeatherOpacity(id, value);
    }
    state.overlays?.setOpacity(value);
  });

  $("radar-play").addEventListener("click", () => {
    if (state.radar.playing) stopRadar();
    else startRadar();
  });
  $("radar-range").addEventListener("input", (event) => {
    applyRadarFrame(Number(event.target.value));
  });
  $("timeline-close").addEventListener("click", () => toggleRadar(false));

  $("health")?.addEventListener("click", loadHealth);

  document.addEventListener("keydown", (event) => {
    const tag = event.target.tagName;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      $("search-input").focus();
    } else if (event.key === "Escape") {
      hideSearch();
      closeSettings();
      closeStreetview();
      $("layer-panel").classList.remove("open");
    } else if ((event.key === "r" || event.key === "R") && !typing) {
      randomPlace();
    }
  });
}

function bindMapUI() {
  const health = $("status-health");
  health.addEventListener("click", loadHealth);
  health.style.pointerEvents = "auto";
  health.style.cursor = "pointer";
}

init().catch((error) => {
  console.error(error);
  toast("应用初始化失败，请检查后端是否在运行");
});
