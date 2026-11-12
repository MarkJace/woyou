/* 地图初始化、底图切换、天气叠加与雷达帧控制 */
const maplibregl = window.maplibregl;

const BASE_PREFIX = "base-";
const WEATHER_PREFIX = "weather-";
const RADAR_ID = "radar-overlay";

export class WoyouMap {
  constructor(container, options) {
    this.sources = options.sources || [];
    this.baseSources = this.sources.filter((s) => s.category === "base");
    this.weatherSources = this.sources.filter((s) => s.category === "weather");
    this.currentBase = options.base || this.baseSources[0]?.id;
    this.onClick = options.onClick;
    this.onMoveEnd = options.onMoveEnd;
    this.onMouseMove = options.onMouseMove;
    this.onStreetviewClick = options.onStreetviewClick;
    this._svBound = false;

    const style = this._buildStyle();
    this.map = new maplibregl.Map({
      container,
      style,
      center: [options.center[0], options.center[1]],
      zoom: options.zoom,
      minZoom: 1,
      maxZoom: 18,
      attributionControl: false,
      antialias: true,
      dragRotate: false,
      pitchWithRotate: false,
    });

    this.map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right"
    );
    this.map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 110, unit: "metric" }),
      "bottom-right"
    );

    this.ready = new Promise((resolve) => {
      this.map.on("load", () => resolve());
    });

    this.map.on("click", (event) => {
      this.onClick?.(event.lngLat);
    });
    this.map.on("moveend", () => {
      this.onMoveEnd?.(this.map.getCenter(), this.map.getZoom());
    });
    this.map.on("mousemove", (event) => {
      this.onMouseMove?.(event.lngLat);
    });
    window.addEventListener("resize", () => this.map.resize());
  }

  _buildStyle() {
    const style = { version: 8, sources: {}, layers: [] };
    for (const source of this.baseSources) {
      const id = `${BASE_PREFIX}${source.id}`;
      style.sources[id] = {
        type: "raster",
        tiles: [`/tiles/${source.id}/{z}/{x}/{y}`],
        tileSize: source.tile_size || 256,
        maxzoom: source.max_zoom || 19,
      };
      style.layers.push({
        id,
        type: "raster",
        source: id,
        paint: { "raster-opacity": 1 },
        layout: { visibility: source.id === this.currentBase ? "visible" : "none" },
      });
    }
    for (const source of this.weatherSources) {
      const id = `${WEATHER_PREFIX}${source.id}`;
      style.sources[id] = {
        type: "raster",
        tiles: [`/tiles/${source.id}/{z}/{x}/{y}`],
        tileSize: source.tile_size || 256,
        maxzoom: source.max_zoom || 19,
      };
      style.layers.push({
        id,
        type: "raster",
        source: id,
        paint: {
          "raster-opacity": source.opacity ?? 0.55,
          "raster-fade-duration": 0,
        },
        layout: { visibility: "none" },
      });
    }
    return style;
  }

  async setBase(id) {
    await this.ready;
    this.currentBase = id;
    for (const source of this.baseSources) {
      const layerId = `${BASE_PREFIX}${source.id}`;
      if (this.map.getLayer(layerId)) {
        this.map.setLayoutProperty(
          layerId,
          "visibility",
          source.id === id ? "visible" : "none"
        );
        this.map.setPaintProperty(layerId, "raster-opacity", 1);
      }
    }
  }

  async setBaseLayers(primary, ids, opacity = 0.5) {
    await this.ready;
    this.currentBase = primary;
    const visible = new Set([primary, ...ids]);
    for (const source of this.baseSources) {
      const layerId = `${BASE_PREFIX}${source.id}`;
      if (!this.map.getLayer(layerId)) continue;
      const isVisible = visible.has(source.id);
      this.map.setLayoutProperty(
        layerId,
        "visibility",
        isVisible ? "visible" : "none"
      );
      this.map.setPaintProperty(
        layerId,
        "raster-opacity",
        source.id === primary ? 1 : opacity
      );
    }
  }

  async setBaseOpacity(opacity) {
    await this.ready;
    for (const source of this.baseSources) {
      if (source.id === this.currentBase) continue;
      const layerId = `${BASE_PREFIX}${source.id}`;
      if (this.map.getLayer(layerId)) {
        this.map.setPaintProperty(layerId, "raster-opacity", opacity);
      }
    }
  }

  async setWeatherVisible(id, visible) {
    await this.ready;
    const layerId = `${WEATHER_PREFIX}${id}`;
    if (!this.map.getLayer(layerId)) return;
    this.map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
  }

  async setWeatherOpacity(id, opacity) {
    await this.ready;
    const layerId = `${WEATHER_PREFIX}${id}`;
    if (!this.map.getLayer(layerId)) return;
    this.map.setPaintProperty(layerId, "raster-opacity", opacity);
  }

  async setRadarVisible(visible, tileUrl, opacity = 0.7) {
    await this.ready;
    const exists = Boolean(this.map.getSource(RADAR_ID));
    if (!visible) {
      if (this.map.getLayer(RADAR_ID)) this.map.removeLayer(RADAR_ID);
      if (this.map.getSource(RADAR_ID)) this.map.removeSource(RADAR_ID);
      return;
    }
    if (!tileUrl) return;
    if (!exists) {
      this.map.addSource(RADAR_ID, {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
        attribution: "RainViewer",
      });
      this.map.addLayer({
        id: RADAR_ID,
        type: "raster",
        source: RADAR_ID,
        paint: {
          "raster-opacity": opacity,
          "raster-fade-duration": 0,
        },
      });
    } else {
      const source = this.map.getSource(RADAR_ID);
      source.setTiles([tileUrl]);
      if (this.map.getLayer(RADAR_ID)) {
        this.map.setPaintProperty(RADAR_ID, "raster-opacity", opacity);
      }
    }
  }

  async setRadarFrame(tileUrl) {
    await this.ready;
    const source = this.map.getSource(RADAR_ID);
    if (source && tileUrl) source.setTiles([tileUrl]);
  }

  async setRadarOpacity(opacity) {
    await this.ready;
    if (this.map.getLayer(RADAR_ID)) {
      this.map.setPaintProperty(RADAR_ID, "raster-opacity", opacity);
    }
  }

  async setStreetview(images) {
    await this.ready;
    const features = (images || [])
      .filter((image) => image.lat !== null && image.lon !== null)
      .map((image) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [image.lon, image.lat] },
        properties: {
          id: image.id,
          thumb: image.thumb,
          captured: image.captured,
        },
      }));
    const data = { type: "FeatureCollection", features };
    if (!this.map.getSource("streetview")) {
      this.map.addSource("streetview", { type: "geojson", data });
      this.map.addLayer({
        id: "streetview-points",
        type: "circle",
        source: "streetview",
        paint: {
          "circle-radius": 6,
          "circle-color": "#0b6bcb",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.95,
        },
      });
      if (!this._svBound) {
        this.map.on("click", "streetview-points", (event) => {
          const feature = event.features?.[0];
          if (feature) this.onStreetviewClick?.(feature.properties.id);
        });
        this.map.on("mouseenter", "streetview-points", () => {
          this.map.getCanvas().style.cursor = "pointer";
        });
        this.map.on("mouseleave", "streetview-points", () => {
          this.map.getCanvas().style.cursor = "";
        });
        this._svBound = true;
      }
    } else {
      this.map.getSource("streetview").setData(data);
    }
  }

  async clearStreetview() {
    await this.ready;
    if (this.map.getLayer("streetview-points")) {
      this.map.removeLayer("streetview-points");
    }
    if (this.map.getSource("streetview")) {
      this.map.removeSource("streetview");
    }
  }

  flyTo(lat, lon, zoom = 9) {
    this.map.flyTo({ center: [lon, lat], zoom, duration: 1300, essential: true });
  }

  jumpTo(lat, lon, zoom = 9) {
    this.map.jumpTo({ center: [lon, lat], zoom });
  }

  setMarker(lat, lon) {
    if (!this.marker) {
      this.marker = new maplibregl.Marker({ color: "#0b6bcb" });
    }
    this.marker.setLngLat([lon, lat]).addTo(this.map);
  }

  getCenter() {
    const center = this.map.getCenter();
    return { lat: center.lat, lon: center.lng };
  }

  getZoom() {
    return this.map.getZoom();
  }

  getBounds() {
    return this.map.getBounds();
  }

  resize() {
    this.map.resize();
  }
}
