/* 气温热力图、空气质量热力图、风场流线（Canvas 叠加层） */

const TEMP_STOPS = [
  [-30, [75, 0, 130]],
  [-20, [0, 0, 255]],
  [-10, [0, 128, 255]],
  [0, [0, 255, 255]],
  [10, [0, 220, 80]],
  [20, [255, 230, 0]],
  [30, [255, 140, 0]],
  [40, [255, 40, 0]],
  [50, [150, 0, 0]],
];

const AQI_STOPS = [
  [0, [0, 228, 0]],
  [50, [255, 255, 0]],
  [100, [255, 126, 0]],
  [150, [255, 0, 0]],
  [200, [143, 63, 151]],
  [300, [126, 0, 35]],
];

function interpolate(value, stops) {
  if (value <= stops[0][0]) return stops[0][1];
  if (value >= stops[stops.length - 1][0]) return stops[stops.length - 1][1];
  for (let i = 1; i < stops.length; i += 1) {
    const [v1, c1] = stops[i];
    const [v0, c0] = stops[i - 1];
    if (value <= v1) {
      const t = (value - v0) / (v1 - v0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
      ];
    }
  }
  return stops[stops.length - 1][1];
}

function gradientCss(stops, min, max) {
  const parts = stops.map(([value, color]) => {
    const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
    return `rgb(${color[0]}, ${color[1]}, ${color[2]}) ${pct.toFixed(1)}%`;
  });
  return `linear-gradient(90deg, ${parts.join(", ")})`;
}

export class WeatherOverlays {
  constructor(map, options = {}) {
    this.map = map;
    this.opacity = options.opacity ?? 0.6;
    this.units = options.units ?? "metric";
    this.onUpdate = options.onUpdate;
    this.onError = options.onError;

    this.kind = null; // temperature | air
    this.wind = false;
    this.data = { temperature: null, air: null, wind: null };
    this.cache = new Map();
    this.seq = { temperature: 0, air: 0, wind: 0 };
    this.controllers = {};
    this.particles = [];
    this.anim = null;
    this._raf = null;

    this.heatCanvas = document.getElementById("heatmap-canvas");
    this.windCanvas = document.getElementById("wind-canvas");
    this.heatCtx = this.heatCanvas.getContext("2d");
    this.windCtx = this.windCanvas.getContext("2d");

    this._onMove = () => {
      this.scheduleHeatmap();
      this.particles = [];
    };
    this._onMoveEnd = () => {
      this.scheduleHeatmap();
      this.particles = [];
      this.refresh();
    };
    this._onResize = () => this.resize();

    map.on("move", this._onMove);
    map.on("moveend", this._onMoveEnd);
    window.addEventListener("resize", this._onResize);
    this.resize();
  }

  /* ------------------------------------------------------------------ */
  /* 对外接口                                                            */
  /* ------------------------------------------------------------------ */
  setKind(kind, enabled) {
    if (enabled) {
      this.kind = kind;
      this.fetchKind(kind);
    } else if (this.kind === kind) {
      this.kind = null;
    }
    this.drawHeatmap();
    this.onUpdate?.();
  }

  setWind(enabled) {
    this.wind = enabled;
    if (enabled) {
      this.fetchKind("wind");
      this.startWind();
    } else {
      this.stopWind();
    }
    this.onUpdate?.();
  }

  setOpacity(opacity) {
    this.opacity = opacity;
    this.drawHeatmap();
  }

  setUnits(units) {
    this.units = units;
    this.onUpdate?.();
  }

  refresh() {
    if (this.kind) this.fetchKind(this.kind);
    if (this.wind) this.fetchKind("wind");
  }

  legend() {
    if (this.kind === "temperature") {
      const data = this.data.temperature;
      const unit = this.units === "imperial" ? "°F" : "°C";
      const convert = (value) =>
        this.units === "imperial" ? (value * 9) / 5 + 32 : value;
      const range = data
        ? `当前 ${Math.round(convert(data.min ?? 0))}–${Math.round(convert(data.max ?? 0))} ${unit}`
        : "正在加载…";
      return {
        title: "气温",
        subtitle: range,
        gradient: gradientCss(TEMP_STOPS, -30, 50),
        labels: [-30, -10, 10, 30, 50].map(
          (value) => `${Math.round(convert(value))}°`
        ),
      };
    }
    if (this.kind === "air") {
      const data = this.data.air;
      return {
        title: "空气质量",
        subtitle: data ? `US AQI ${data.min ?? "—"}–${data.max ?? "—"}` : "正在加载…",
        gradient: gradientCss(AQI_STOPS, 0, 300),
        labels: ["0", "50", "100", "150", "200", "300+"],
      };
    }
    if (this.wind) {
      const data = this.data.wind;
      return {
        title: "风场",
        subtitle: data ? `10 米风速 · 最大 ${data.max ?? "—"} m/s` : "正在加载…",
        gradient: null,
        labels: [],
        note: "流线方向 = 风向，速度对应 10 米风速",
      };
    }
    return null;
  }

  /* ------------------------------------------------------------------ */
  /* 数据                                                                */
  /* ------------------------------------------------------------------ */
  bounds() {
    const b = this.map.getBounds();
    let west = b.getWest();
    let east = b.getEast();
    let south = b.getSouth();
    let north = b.getNorth();
    if (west > east) {
      west = -180;
      east = 180;
    }
    south = Math.max(-85, Math.min(85, south));
    north = Math.max(-85, Math.min(85, north));
    if (east - west < 0.02 || north - south < 0.02) return null;
    return { west, south, east, north };
  }

  async fetchKind(kind) {
    const bounds = this.bounds();
    if (!bounds) return;
    const nx = 12;
    const ny = 9;
    const key = [
      kind,
      bounds.west.toFixed(2),
      bounds.south.toFixed(2),
      bounds.east.toFixed(2),
      bounds.north.toFixed(2),
      nx,
      ny,
    ].join(":");
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.at < 300000) {
      this.data[kind] = cached.data;
      this.afterData(kind);
      return;
    }

    const token = (this.seq[kind] || 0) + 1;
    this.seq[kind] = token;
    this.controllers[kind]?.abort();
    const controller = new AbortController();
    this.controllers[kind] = controller;
    const params = new URLSearchParams({
      kind,
      west: bounds.west.toFixed(4),
      south: bounds.south.toFixed(4),
      east: bounds.east.toFixed(4),
      north: bounds.north.toFixed(4),
      nx: String(nx),
      ny: String(ny),
    });

    try {
      const response = await fetch(`/api/v1/grid?${params}`, {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (token !== this.seq[kind]) return;
      this.data[kind] = data;
      this.cache.set(key, { data, at: Date.now() });
      if (this.cache.size > 40) {
        this.cache.delete(this.cache.keys().next().value);
      }
      this.afterData(kind);
    } catch (error) {
      if (error.name !== "AbortError") {
        this.onError?.("环境图层加载失败，请稍后再试");
      }
    }
  }

  afterData(kind) {
    if (kind === "wind") {
      this.particles = [];
      if (this.wind) {
        this.startWind();
        this.drawWindFrame();
      }
    }
    if (kind === this.kind) this.drawHeatmap();
    this.onUpdate?.();
  }

  /* ------------------------------------------------------------------ */
  /* 尺寸与热力图                                                        */
  /* ------------------------------------------------------------------ */
  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    for (const canvas of [this.heatCanvas, this.windCanvas]) {
      const width = canvas.clientWidth || window.innerWidth;
      const height = canvas.clientHeight || window.innerHeight;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      canvas.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    this.width = this.heatCanvas.width / dpr;
    this.height = this.heatCanvas.height / dpr;
    this.particles = [];
    this.drawHeatmap();
    this.windCtx.clearRect(0, 0, this.width, this.height);
    if (this.wind) this.drawWindFrame();
  }

  scheduleHeatmap() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      this.drawHeatmap();
    });
  }

  drawHeatmap() {
    const ctx = this.heatCtx;
    ctx.clearRect(0, 0, this.width, this.height);
    if (!this.kind) return;
    const data = this.data[this.kind];
    if (!data || !data.values) return;

    const stops = this.kind === "temperature" ? TEMP_STOPS : AQI_STOPS;
    const { bounds, nx, ny, values } = data;
    const points = [];
    for (let j = 0; j < ny; j += 1) {
      const lat = bounds.south + ((bounds.north - bounds.south) * j) / (ny - 1);
      for (let i = 0; i < nx; i += 1) {
        const value = values[j]?.[i];
        if (value === null || value === undefined) continue;
        const lon = bounds.west + ((bounds.east - bounds.west) * i) / (nx - 1);
        const point = this.map.project([lon, lat]);
        points.push({ x: point.x, y: point.y, value });
      }
    }
    if (!points.length) return;

    let spacing = 40;
    if (points.length > nx) {
      const dx = Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
      const dy = Math.hypot(points[nx].x - points[0].x, points[nx].y - points[0].y);
      spacing = Math.max(dx, dy);
    }
    const radius = Math.max(16, Math.min(320, spacing * 1.2));

    ctx.save();
    ctx.globalAlpha = Math.min(1, this.opacity * 0.9);
    ctx.filter = "blur(16px)";
    for (const point of points) {
      const [r, g, b] = interpolate(point.value, stops);
      ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.26)`;
      ctx.beginPath();
      ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  /* ------------------------------------------------------------------ */
  /* 风场                                                                */
  /* ------------------------------------------------------------------ */
  startWind() {
    if (this.anim) return;
    const tick = () => {
      this.drawWindFrame();
      this.anim = requestAnimationFrame(tick);
    };
    this.anim = requestAnimationFrame(tick);
  }

  stopWind() {
    if (this.anim) {
      cancelAnimationFrame(this.anim);
      this.anim = null;
    }
    this.windCtx.clearRect(0, 0, this.width, this.height);
    this.particles = [];
  }

  initParticles() {
    this.particles = [];
    for (let i = 0; i < 900; i += 1) {
      this.particles.push(this.spawnParticle({}));
    }
  }

  spawnParticle(particle) {
    const data = this.data.wind;
    if (!data) return particle;
    const { bounds } = data;
    const lat = bounds.south + Math.random() * (bounds.north - bounds.south);
    const lon = bounds.west + Math.random() * (bounds.east - bounds.west);
    let point;
    try {
      point = this.map.project([lon, lat]);
    } catch {
      point = { x: 0, y: 0 };
    }
    particle.lat = lat;
    particle.lon = lon;
    particle.x = point.x;
    particle.y = point.y;
    particle.px = point.x;
    particle.py = point.y;
    particle.age = 20 + Math.floor(Math.random() * 80);
    return particle;
  }

  sampleWind(lat, lon) {
    const data = this.data.wind;
    if (!data) return { u: 0, v: 0 };
    const { bounds, nx, ny, u, v } = data;
    const fx = Math.max(
      0,
      Math.min(nx - 1, ((lon - bounds.west) / (bounds.east - bounds.west)) * (nx - 1))
    );
    const fy = Math.max(
      0,
      Math.min(ny - 1, ((lat - bounds.south) / (bounds.north - bounds.south)) * (ny - 1))
    );
    const x0 = Math.floor(fx);
    const y0 = Math.floor(fy);
    const x1 = Math.min(x0 + 1, nx - 1);
    const y1 = Math.min(y0 + 1, ny - 1);
    const tx = fx - x0;
    const ty = fy - y0;
    const at = (matrix, x, y) => {
      const value = matrix[y]?.[x];
      return value === null || value === undefined ? 0 : value;
    };
    const blend = (matrix) => {
      const a = at(matrix, x0, y0) * (1 - tx) + at(matrix, x1, y0) * tx;
      const b = at(matrix, x0, y1) * (1 - tx) + at(matrix, x1, y1) * tx;
      return a * (1 - ty) + b * ty;
    };
    return { u: blend(u), v: blend(v) };
  }

  drawWindFrame() {
    const ctx = this.windCtx;
    if (!this.wind || !this.data.wind) {
      ctx.clearRect(0, 0, this.width, this.height);
      return;
    }
    if (!this.particles.length) this.initParticles();

    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = "rgba(0, 0, 0, 0.10)";
    ctx.fillRect(0, 0, this.width, this.height);
    ctx.globalCompositeOperation = "source-over";

    ctx.globalAlpha = Math.min(1, this.opacity + 0.15);
    ctx.strokeStyle = "rgba(188, 232, 255, 0.82)";
    ctx.lineWidth = 1.2;
    const scale = 0.22;
    const width = this.width;
    const height = this.height;

    for (const particle of this.particles) {
      const wind = this.sampleWind(particle.lat, particle.lon);
      particle.px = particle.x;
      particle.py = particle.y;
      particle.x += wind.u * scale;
      particle.y -= wind.v * scale;
      particle.age -= 1;
      if (
        particle.age <= 0 ||
        particle.x < -30 ||
        particle.x > width + 30 ||
        particle.y < -30 ||
        particle.y > height + 30
      ) {
        this.spawnParticle(particle);
        continue;
      }
      const speed = Math.hypot(wind.u, wind.v) || 1;
      const tail = Math.min(26, 5 + speed * 1.3);
      const ux = wind.u / speed;
      const vy = wind.v / speed;
      ctx.beginPath();
      ctx.moveTo(particle.x - ux * tail, particle.y + vy * tail);
      ctx.lineTo(particle.x, particle.y);
      ctx.stroke();
    }
  }
}
