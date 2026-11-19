// munichpeaks — 3D map of hiking peaks within a 3 h drive of Munich.
(async function () {
  'use strict';

  // ---- Config ---------------------------------------------------------------
  const TERRARIUM = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
  const DEM_ATTR = 'Elevation: <a href="https://registry.opendata.aws/terrain-tiles/">AWS Terrain Tiles</a> (Mapzen)';
  const OSM_ATTR = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors (ODbL)';
  // Drive-time zones are areas (cool colors); peaks are colored by elevation (warm ramp), so
  // the two never compete. Everything beyond 3 h is greyed out.
  // Five 30-min bands, green (close) -> blue -> purple (far): "Jewel" colors.
  const BANDS = [
    { id: 1, label: 'Up to 1 h', color: '#1fae8b' },
    { id: 2, label: '1 – 1.5 h', color: '#1b98b0' },
    { id: 3, label: '1.5 – 2 h', color: '#2f7bc4' },
    { id: 4, label: '2 – 2.5 h', color: '#5160c0' },
    { id: 5, label: '2.5 – 3 h', color: '#7448ad' },
  ];
  const zoneColor = ['match', ['get', 'min_to'], 60, BANDS[0].color, 90, BANDS[1].color,
                     120, BANDS[2].color, 150, BANDS[3].color, BANDS[4].color];
  const ELE_STOPS = [[1500, '#fff1a8'], [2000, '#ffc857'], [2500, '#ff8c42'], [3000, '#ec4755'], [3500, '#c2185b']];
  const eleColor = ['interpolate', ['linear'], ['get', 'ele'], ...ELE_STOPS.flat()];
  const isZone = ['!', ['has', 'outside']];
  const TERRAIN_EXAGGERATION = 1.4;
  const isMobile = () => window.matchMedia('(max-width: 640px)').matches;
  // Overview camera. A phone is narrow and tall with a legend at the bottom: zoom out a little
  // and look further south so Munich and the Alps both sit in the visible part.
  const HOME = () => isMobile() ? { center: [11.4, 47.25], zoom: 6.55, pitch: 35, bearing: 0 }
                                : { center: [11.25, 47.65], zoom: 7.3, pitch: 35, bearing: 0 };

  // Label language for places and regions: English (where OSM has a name:en) or local
  // (München, Tirol, Trento). Peak names are always the local OSM name.
  let lang = 'en';
  try { if (localStorage.getItem('lang') === 'local') lang = 'local'; } catch (_) {}
  const labelExpr = () => lang === 'en' ? ['coalesce', ['get', 'en'], ['get', 'name']] : ['get', 'name'];
  const nm = x => (lang === 'en' && x.en) || x.name;
  const ORIGIN_LABEL = { en: 'MUNICH', local: 'MÜNCHEN' };
  const ORIGIN_SHORT = { en: 'Munich Hbf', local: 'München Hbf' };
  const ORIGIN_LOCAL = 'München';   // places.geojson name of the origin city (it has its own label)

  // ---- Data -----------------------------------------------------------------
  // no-cache = revalidate (cheap 304), so a data update is never mixed with a stale file
  const getJSON = url => fetch(url, { cache: 'no-cache' }).then(r => r.json());
  const [peakData, iso, regionGeo, places] = await Promise.all([
    getJSON('data/peaks.json'),
    getJSON('data/isochrones.geojson'),
    getJSON('data/regions.geojson'),
    getJSON('data/places.geojson'),
  ]);
  const { origin } = peakData;
  const peaks = peakData.peaks;
  const byId = new Map(peaks.map(p => [p.id, p]));
  // Regions (Regierungsbezirk / Bundesland / Kanton / Provincia) that contain peaks
  const COUNTRIES = { DE: 'Germany', AT: 'Austria', CH: 'Switzerland', IT: 'Italy', LI: 'Liechtenstein' };
  const regions = regionGeo.features.map(f => f.properties).filter(r => r.n > 0);
  const regById = new Map(regions.map(r => [r.id, r]));
  const regionLabelGeo = {
    type: 'FeatureCollection',
    features: regions.map(r => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [r.lon, r.lat] },
                                  properties: { name: r.name, en: r.en } })),
  };
  const peakGeo = {
    type: 'FeatureCollection',
    features: peaks.map(p => ({
      type: 'Feature', id: p.id,
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { id: p.id, name: p.name, ele: p.ele, band: p.band, tier: p.tier,
                    label: `${p.name}\n${p.ele.toLocaleString('en')} m`, rank: p.rank, reg: p.reg },
    })),
  };

  // ---- Style ----------------------------------------------------------------
  const demSource = () => ({ type: 'raster-dem', tiles: [TERRARIUM], encoding: 'terrarium',
                             tileSize: 256, maxzoom: 15, attribution: DEM_ATTR });
  const fontsBase = new URL('fonts/', location.href).href;
  const style = {
    version: 8,
    glyphs: fontsBase + '{fontstack}/{range}.pbf',
    sources: {
      places: { type: 'geojson', data: places, attribution: OSM_ATTR },
      sat: {
        type: 'raster', tileSize: 256, maxzoom: 15,
        tiles: ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg'],
        attribution: '<a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX IT Services GmbH (Copernicus Sentinel data 2020, CC BY-NC-SA)',
      },
      terrain: demSource(),
      hillshade: demSource(),
      iso: { type: 'geojson', data: iso,
             attribution: `Drive times: <a href="https://github.com/valhalla/valhalla">Valhalla</a> on ${OSM_ATTR}` },
      peaks: { type: 'geojson', data: peakGeo },
      regions: { type: 'geojson', data: regionGeo, promoteId: 'id' },
      'region-labels': { type: 'geojson', data: regionLabelGeo },
      origin: { type: 'geojson', data: { type: 'Feature', properties: {},
                                         geometry: { type: 'Point', coordinates: [origin.lon, origin.lat] } } },
    },
    layers: [
      // "Relief" basemap = just shaded terrain on a neutral slate background
      { id: 'bg', type: 'background', paint: { 'background-color': '#2b323c' } },
      { id: 'sat', type: 'raster', source: 'sat', layout: { visibility: 'none' },
        paint: { 'raster-contrast': 0.1, 'raster-saturation': 0.1 } },
      { id: 'hillshade', type: 'hillshade', source: 'hillshade',
        paint: { 'hillshade-exaggeration': 0.75, 'hillshade-shadow-color': '#06090d',
                 'hillshade-highlight-color': '#f2f4f7', 'hillshade-accent-color': '#1b2028',
                 'hillshade-illumination-direction': 315 } },
      { id: 'iso-fill', type: 'fill', source: 'iso', filter: isZone,
        paint: { 'fill-color': zoneColor,
                 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.34, 10, 0.2, 13, 0.08] } },
      { id: 'iso-mask', type: 'fill', source: 'iso', filter: ['has', 'outside'],
        paint: { 'fill-color': '#0a0d12', 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.72, 12, 0.55] } },
      { id: 'iso-line', type: 'line', source: 'iso', filter: isZone,
        paint: { 'line-color': zoneColor,
                 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.8, 11, 1.8],
                 'line-opacity': ['interpolate', ['linear'], ['zoom'], 6, 0.8, 13, 0.35] } },
      // Regions: dim everything but the focused one, hover tint, borders
      { id: 'region-dim', type: 'fill', source: 'regions', filter: ['==', ['get', 'id'], -1],
        paint: { 'fill-color': '#0a0d12', 'fill-opacity': 0.55 } },
      { id: 'region-hit', type: 'fill', source: 'regions', filter: ['>', ['get', 'n'], 0],
        paint: { 'fill-color': '#ffffff',
                 'fill-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 0.07, 0] } },
      { id: 'region-line', type: 'line', source: 'regions', filter: ['>', ['get', 'n'], 0],
        layout: { 'line-join': 'round' },
        paint: { 'line-color': '#e8edf3',
                 'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.95, 0.4],
                 'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5,
                                ['boolean', ['feature-state', 'hover'], false], 1.6, 0.8] } },
      // City / town names (precomputed from OSM), quieter than the peak labels
      { id: 'places', type: 'symbol', source: 'places',
        // München is drawn by its own, more prominent label layer (origin-label)
        // rank 1 (big cities, capitals) is drawn by the 'cities' layer above the peak labels
        filter: ['all', ['>=', ['get', 'rank'], 2],
                 ['<=', ['get', 'rank'], ['step', ['zoom'], 1, 7.5, 2, 9.5, 3]]],
        layout: {
          'text-field': labelExpr(),
          'text-font': ['Noto Sans Regular'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 6, ['match', ['get', 'rank'], 1, 13, 11],
                        11, ['match', ['get', 'rank'], 1, 16, 2, 14, 12]],
          'text-transform': 'uppercase', 'text-letter-spacing': 0.08,
          'symbol-sort-key': ['get', 'rank'], 'text-padding': 6,
        },
        paint: { 'text-color': 'rgba(226,232,240,0.78)', 'text-halo-color': 'rgba(10,13,18,0.8)',
                 'text-halo-width': 1.2 } },
      { id: 'region-labels', type: 'symbol', source: 'region-labels', maxzoom: 8.8,
        layout: { 'text-field': labelExpr(), 'text-font': ['Noto Sans Medium'],
                  'text-size': ['interpolate', ['linear'], ['zoom'], 6, 11, 8.5, 15],
                  'text-transform': 'uppercase', 'text-letter-spacing': 0.18, 'text-padding': 10,
                  'text-variable-anchor': ['center', 'top', 'bottom', 'left', 'right'], 'text-radial-offset': 1.5 },
        paint: { 'text-color': 'rgba(255,255,255,0.6)', 'text-halo-color': 'rgba(10,13,18,0.75)',
                 'text-halo-width': 1.2 } },
      // The starting point: just its name, a little brighter than other places
      { id: 'origin-label', type: 'symbol', source: 'origin',
        layout: { 'text-field': ORIGIN_LABEL[lang], 'text-font': ['Noto Sans Medium'],
                  'text-size': ['interpolate', ['linear'], ['zoom'], 6, 14, 11, 18],
                  'text-letter-spacing': 0.12, 'text-allow-overlap': true },
        paint: { 'text-color': '#ffffff', 'text-halo-color': 'rgba(10,13,18,0.85)', 'text-halo-width': 1.5 } },
      // Peaks: three fame tiers that appear progressively as you zoom in.
      { id: 'peaks', type: 'circle', source: 'peaks',
        filter: ['<=', ['get', 'tier'],
                 ['step', ['zoom'], 1, 8, 2, 9.5, 3]],
        paint: {
          'circle-color': eleColor,
          // zoom must be the outermost expression; the selection check goes inside each stop
          'circle-radius': ['interpolate', ['linear'], ['zoom'],
            6, ['case', ['boolean', ['feature-state', 'selected'], false], 9,
                ['match', ['get', 'tier'], 1, 5, 2, 3.5, 3]],
            12, ['case', ['boolean', ['feature-state', 'selected'], false], 12,
                ['match', ['get', 'tier'], 1, 8, 2, 6, 5]]],
          'circle-stroke-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#ffffff', 'rgba(10,13,18,0.85)'],
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 4, 1.2],
          'circle-pitch-alignment': 'viewport',
          'circle-pitch-scale': 'viewport',
        } },
      { id: 'peak-labels', type: 'symbol', source: 'peaks',
        filter: ['<=', ['get', 'tier'], ['step', ['zoom'], 1, 8.5, 2, 10, 3]],
        layout: {
          'text-field': ['get', 'label'],
          'text-font': ['Noto Sans Medium'],
          'text-size': ['interpolate', ['linear'], ['zoom'], 7, 11, 12, 13],
          'text-offset': [0, 0.9], 'text-anchor': 'top',
          'symbol-sort-key': ['get', 'rank'],
          'text-padding': 4,
        },
        paint: { 'text-color': '#ffffff', 'text-halo-color': 'rgba(10,14,20,0.85)', 'text-halo-width': 1.4 } },
      // Big cities and state capitals (Innsbruck, Salzburg, Bolzano, …): a small dot + name, placed
      // before the peak labels so they are never hidden by them. Munich has its own label.
      { id: 'city-dots', type: 'circle', source: 'places',
        filter: ['all', ['==', ['get', 'rank'], 1], ['!=', ['get', 'name'], ORIGIN_LOCAL]],
        paint: { 'circle-radius': 2.5, 'circle-color': '#e8edf3', 'circle-stroke-color': 'rgba(10,13,18,0.8)',
                 'circle-stroke-width': 1, 'circle-pitch-alignment': 'viewport' } },
      { id: 'cities', type: 'symbol', source: 'places',
        filter: ['all', ['==', ['get', 'rank'], 1], ['!=', ['get', 'name'], ORIGIN_LOCAL]],
        layout: { 'text-field': labelExpr(), 'text-font': ['Noto Sans Medium'],
                  'text-size': ['interpolate', ['linear'], ['zoom'], 6, 12, 11, 15],
                  'text-transform': 'uppercase', 'text-letter-spacing': 0.08,
                  'text-variable-anchor': ['left', 'right', 'top', 'bottom'], 'text-radial-offset': 0.6,
                  'symbol-sort-key': ['-', 0, ['get', 'pop']], 'text-padding': 4 },
        paint: { 'text-color': 'rgba(240,244,248,0.92)', 'text-halo-color': 'rgba(10,13,18,0.85)',
                 'text-halo-width': 1.4 } },
    ],
    terrain: { source: 'terrain', exaggeration: TERRAIN_EXAGGERATION },
  };

  // ---- Map --------------------------------------------------------------
  const map = new maplibregl.Map({ container: 'map', style, ...HOME(), maxPitch: 85, attributionControl: false });
  window.__map = map; // debug handle
  map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');

  map.on('load', () => {
    // compact attribution starts expanded; on phones collapse it so it doesn't cover the map
    if (isMobile()) document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');
    if (typeof map.setSky === 'function') {
      map.setSky({ 'sky-color': '#1b2b44', 'horizon-color': '#c9d6e3', 'fog-color': '#a8b8c8',
                   'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.4 });
    }
  });


  // ---- Legend -----------------------------------------------------------
  document.getElementById('origin-name').textContent = ORIGIN_SHORT[lang];
  document.getElementById('subtitle').textContent =
    `${peaks.length} hiking summits within a 3 h drive`;
  const hidden = new Set();
  const ul = document.getElementById('legend-bands');
  for (const b of BANDS) {
    const n = peaks.filter(p => p.band === b.id).length;
    const li = document.createElement('li');
    li.innerHTML = `<span class="swatch" style="--c:${b.color}"></span>${b.label}<span class="count">${n} peaks</span>`;
    li.title = 'Show / hide these peaks';
    li.onclick = () => {
      hidden.has(b.id) ? hidden.delete(b.id) : hidden.add(b.id);
      li.classList.toggle('off', hidden.has(b.id));
      applyFilters();
    };
    ul.appendChild(li);
  }
  const out = document.createElement('li');
  out.className = 'static';
  out.innerHTML = '<span class="swatch outside"></span>Beyond 3 h';
  ul.appendChild(out);
  const lo = ELE_STOPS[0][0], hi = ELE_STOPS[ELE_STOPS.length - 1][0];
  document.getElementById('ele-bar').style.background = `linear-gradient(90deg, ${
    ELE_STOPS.map(([e, c]) => `${c} ${((e - lo) / (hi - lo) * 100).toFixed(0)}%`).join(', ')})`;
  document.getElementById('ele-ticks').innerHTML =
    ELE_STOPS.map(([e]) => `<span>${e.toLocaleString('en')}${e === hi ? '+' : ''}</span>`).join('');

  // ---- Wait for style before wiring anything that touches layers --------
  await new Promise(res => map.loaded() ? res() : map.once('load', res));

  // Peak visibility = drive-time legend toggles + fame tiers by zoom. With a focused region,
  // all of its peaks are shown (and labelled) and the rest fade out.
  const TIER_DOT = ['<=', ['get', 'tier'], ['step', ['zoom'], 1, 8, 2, 9.5, 3]];
  const TIER_LABEL = ['<=', ['get', 'tier'], ['step', ['zoom'], 1, 8.5, 2, 10, 3]];
  function applyFilters() {
    const bandF = hidden.size ? ['!', ['in', ['get', 'band'], ['literal', [...hidden]]]] : true;
    const inReg = focus ? ['==', ['get', 'reg'], focus.id] : false;
    map.setFilter('peaks', ['all', bandF, focus ? ['any', inReg, TIER_DOT] : TIER_DOT]);
    map.setFilter('peak-labels', ['all', bandF, focus ? inReg : TIER_LABEL]);
    const op = focus ? ['case', inReg, 1, 0.3] : 1;
    map.setPaintProperty('peaks', 'circle-opacity', op);
    map.setPaintProperty('peaks', 'circle-stroke-opacity', op);
    map.setLayoutProperty('region-labels', 'visibility', focus ? 'none' : 'visible');
    map.setFilter('region-dim', focus ? ['!=', ['get', 'id'], focus.id] : ['==', ['get', 'id'], -1]);
  }

  document.getElementById('toggle-iso').onchange = e => {
    const v = e.target.checked ? 'visible' : 'none';
    ['iso-fill', 'iso-mask', 'iso-line'].forEach(id => map.setLayoutProperty(id, 'visibility', v));
  };

  document.querySelectorAll('.basemap button').forEach(btn => btn.onclick = () => {
    document.querySelectorAll('.basemap button').forEach(b => b.classList.toggle('active', b === btn));
    const sat = btn.dataset.base === 'sat';
    map.setLayoutProperty('sat', 'visibility', sat ? 'visible' : 'none');
    map.setPaintProperty('hillshade', 'hillshade-exaggeration', sat ? 0.3 : 0.75);
  });

  // ---- Fly-in + rotate around the summit (on demand, no auto-rotation) --------------
  // Rotation is a per-frame jumpTo that re-aims through the summit (see aimPoint), so the
  // camera circles the summit itself rather than the point in the valley behind it.
  const ROTATE_STEP = 45, ROTATE_MS = 900;
  let orbiting = false, orbitRaf = 0;
  function stopOrbit() {
    if (orbiting) { orbiting = false; cancelAnimationFrame(orbitRaf); map.stop(); }
  }
  function rotateAround(p, delta) {
    stopOrbit();
    orbiting = true;
    const start = map.getBearing(), t0 = performance.now();
    const ease = t => 1 - Math.pow(1 - t, 3);
    const step = now => {
      if (!orbiting) return;
      const t = Math.min(1, (now - t0) / ROTATE_MS);
      const bearing = start + delta * ease(t);
      map.jumpTo({ bearing, center: aimPoint(p, bearing) });
      if (t < 1) orbitRaf = requestAnimationFrame(step); else orbiting = false;
    };
    orbitRaf = requestAnimationFrame(step);
  }
  ['mousedown', 'touchstart', 'wheel'].forEach(ev =>
    map.getCanvasContainer().addEventListener(ev, stopOrbit, { passive: true }));

  // same ramp as the map, for the info card
  function eleHex(e) {
    const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
    const st = ELE_STOPS;
    if (e <= st[0][0]) return st[0][1];
    for (let i = 1; i < st.length; i++) {
      if (e <= st[i][0]) {
        const t = (e - st[i - 1][0]) / (st[i][0] - st[i - 1][0]);
        const a = hex(st[i - 1][1]), b = hex(st[i][1]);
        return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * t)).join(',')})`;
      }
    }
    return st[st.length - 1][1];
  }

  const fmtTime = m => m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}`;
  const card = document.getElementById('card');
  let selected = null;

  function selectPeak(p, { fly = true } = {}) {
    if (selected != null) map.setFeatureState({ source: 'peaks', id: selected }, { selected: false });
    selected = p.id;
    map.setFeatureState({ source: 'peaks', id: p.id }, { selected: true });

    const band = BANDS[p.band - 1];
    const eb = document.getElementById('card-band');
    eb.textContent = `${band.label} drive`;
    eb.style.color = band.color;
    document.getElementById('card-name').textContent = p.name;
    document.getElementById('card-alt').textContent = p.alt || '';
    const ele = document.getElementById('card-ele');
    ele.textContent = `${p.ele.toLocaleString('en')} m`;
    ele.style.color = eleHex(p.ele);
    document.getElementById('card-time').textContent = fmtTime(p.min);
    document.getElementById('card-km').textContent = `${p.km} km`;
    let note = `From ${ORIGIN_SHORT[lang]}, free-flow (no traffic). Weekend trips usually take longer.`;
    if (p.th) note += ` Routed to trailhead: ${p.th}.`;
    else if (p.gap >= 2) note += ` Routed to the nearest road, ${p.gap.toFixed(1)} km from the summit; the real trailhead may differ.`;
    document.getElementById('card-note').textContent = note;

    const links = [];
    if (p.wp) {
      const [lang, ...t] = p.wp.split(':');
      links.push(`<a href="https://${lang}.wikipedia.org/wiki/${encodeURIComponent(t.join(':'))}" target="_blank" rel="noopener">Wikipedia</a>`);
    }
    links.push(`<a href="https://www.openstreetmap.org/node/${p.id}" target="_blank" rel="noopener">OpenStreetMap</a>`);
    document.getElementById('card-links').innerHTML = links.join('');

    card.hidden = false;
    document.body.classList.add('peak-open');
    if (focus && p.reg !== focus.id) clearRegion();
    // after clearRegion, so the label names where "back" will go
    card.querySelector('.back').textContent = `‹ Back to ${focus ? nm(focus) : 'overview'}`;
    setHash('peak', p.id);
    if (!fly) return;

    stopOrbit();
    flightToken++;
    const bearing = map.getBearing() - 40;
    map.flyTo({
      center: aimPoint(p, bearing), zoom: 11.6, pitch: FLY_PITCH, bearing,
      duration: 4500, curve: 1.6, essential: true, padding: viewPadding(),
    });
  }

  function currentElevation() {
    const tr = map.transform;
    return (tr && typeof tr.elevation === 'number') ? tr.elevation : 0;
  }

  // During a camera animation MapLibre freezes the center's elevation at its starting value
  // (e.g. ~1200 m for the overview). Aiming at the summit's lon/lat would therefore aim at a
  // point far *below* the summit, and the summit would sit high above screen center. Instead,
  // aim at the point where the line of sight through the summit reaches that frozen
  // elevation: (summit height - frozen elevation) * tan(pitch) further along the bearing.
  // (MapLibre 4.7 keeps that frozen elevation after the flight too, so the orbit re-uses
  // this function every frame.)
  const FLY_PITCH = 70;
  function aimPoint(p, bearing) {
    const frozen = currentElevation();
    const summit = p.ele * TERRAIN_EXAGGERATION;
    const d = Math.max(0, summit - frozen) * Math.tan(FLY_PITCH * Math.PI / 180); // metres
    const b = bearing * Math.PI / 180;
    const dLat = (d * Math.cos(b)) / 111320;
    const dLon = (d * Math.sin(b)) / (111320 * Math.cos(p.lat * Math.PI / 180));
    return [p.lon + dLon, p.lat + dLat];
  }

  let flightToken = 0;
  // On phones the map is only visible between the top controls and the bottom sheet (card or
  // region panel); measure both instead of guessing, mobile Safari's toolbars change the height.
  const topControlsBottom = () => document.querySelector('.top-right').getBoundingClientRect().bottom;
  const sheetHeight = el => window.innerHeight - el.getBoundingClientRect().top;
  function viewPadding() {
    return isMobile() ? { top: topControlsBottom() + 10, bottom: sheetHeight(card) + 10, left: 0, right: 0 }
                      : { left: 340, top: 0, bottom: 0, right: 0 };
  }

  function closeCard() {
    card.hidden = true;
    document.body.classList.remove('peak-open');
    if (selected != null) map.setFeatureState({ source: 'peaks', id: selected }, { selected: false });
    selected = null;
    stopOrbit();
    flightToken++;
    if (focus) { setHash('region', focus.id); flyToRegion(focus); return; }
    setHash(null);
    map.flyTo({ ...HOME(), padding: { left: 0, right: 0, top: 0, bottom: 0 }, duration: 3000 });
  }
  card.querySelector('.close').onclick = closeCard;
  card.querySelector('.back').onclick = closeCard;
  card.querySelectorAll('.rotate button').forEach(b => b.onclick = () => {
    const p = byId.get(selected);
    if (!p || (map.isMoving() && !orbiting)) return;   // don't cut the fly-in short
    rotateAround(p, +b.dataset.deg);
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!card.hidden) closeCard();
    else if (focus) exitRegion();
  });

  // A click hits a peak first; otherwise (no peak open) it focuses the region under it.
  map.on('click', e => {
    const pk = map.queryRenderedFeatures(e.point, { layers: ['peaks'] })[0];
    if (pk) { const p = byId.get(pk.properties.id); if (p) selectPeak(p); return; }
    // a click on empty map while a peak is open goes back (to the region, or the overview);
    // dragging to look around doesn't fire a click, so that still works
    if (selected != null) { closeCard(); return; }
    const rf = map.queryRenderedFeatures(e.point, { layers: ['region-hit'] })[0];
    const r = rf && regById.get(rf.properties.id);
    // with a region focused, a click outside it goes back to the full map
    if (focus) { if (r !== focus) exitRegion(); return; }
    if (r) selectRegion(r);
  });

  // ---- Regions ----------------------------------------------------------
  let focus = null, hoverId = null;
  const regionPanel = document.getElementById('region');
  const regionSelect = document.getElementById('region-select');
  let regionSort = 'rank';

  function buildRegionSelect() {
    regionSelect.replaceChildren(new Option('Browse by region…', ''));
    for (const [cc, label] of Object.entries(COUNTRIES)) {
      const rs = regions.filter(r => r.country === cc).sort((a, b) => nm(a).localeCompare(nm(b)));
      if (!rs.length) continue;
      const g = document.createElement('optgroup');
      g.label = label;
      for (const r of rs) g.appendChild(new Option(`${nm(r)} (${r.n})`, r.id));
      regionSelect.appendChild(g);
    }
    regionSelect.value = focus ? String(focus.id) : '';
  }
  buildRegionSelect();

  // ---- Label language toggle --------------------------------------------
  function applyLang(l) {
    lang = l;
    try { localStorage.setItem('lang', l); } catch (_) {}
    document.querySelectorAll('.lang button').forEach(b => b.classList.toggle('active', b.dataset.lang === l));
    ['places', 'cities', 'region-labels'].forEach(id => map.setLayoutProperty(id, 'text-field', labelExpr()));
    map.setLayoutProperty('origin-label', 'text-field', ORIGIN_LABEL[l]);
    document.getElementById('origin-name').textContent = ORIGIN_SHORT[l];
    buildRegionSelect();
    if (focus) renderRegion();
    if (selected != null && focus) card.querySelector('.back').textContent = `‹ Back to ${nm(focus)}`;
  }
  document.querySelectorAll('.lang button').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
    b.onclick = () => applyLang(b.dataset.lang);
  });
  regionSelect.onchange = () => {
    const r = regById.get(+regionSelect.value);
    if (r) { if (!card.hidden) closeCardQuiet(); selectRegion(r); }
    else if (focus) exitRegion();
  };

  map.on('mousemove', 'region-hit', e => {
    const id = e.features[0]?.id;
    if (id === hoverId) return;
    if (hoverId != null) map.setFeatureState({ source: 'regions', id: hoverId }, { hover: false });
    hoverId = id;
    if (id != null && selected == null) map.setFeatureState({ source: 'regions', id }, { hover: true });
  });
  map.on('mouseleave', 'region-hit', () => {
    if (hoverId != null) map.setFeatureState({ source: 'regions', id: hoverId }, { hover: false });
    hoverId = null;
  });

  function regionPadding() {
    return isMobile() ? { top: topControlsBottom() + 12, bottom: sheetHeight(regionPanel) + 12, left: 16, right: 16 }
                      : { left: 360, top: 60, bottom: 40, right: 60 };
  }
  // Camera for a region's bbox, computed directly (fitBounds is thrown off by the pitch and
  // frozen terrain elevation left over from a 3D peak view). Seen from straight above; the 3D
  // terrain stays on, so tilting the map (right-drag / two fingers) shows the mountains.
  function flyToRegion(r) {
    const [w, s, e, n] = r.bbox;
    const pad = regionPadding();
    const merc = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) / (2 * Math.PI);
    const dx = (e - w) / 360, dy = merc(n) - merc(s);
    const c = map.getContainer();
    const availW = c.clientWidth - pad.left - pad.right, availH = c.clientHeight - pad.top - pad.bottom;
    const zoom = Math.min(10.5, Math.log2(Math.min(availW / (dx * 512), availH / (dy * 512))) - 0.1);
    const yc = (merc(n) + merc(s)) / 2;
    const lat = (360 / Math.PI) * Math.atan(Math.exp(yc * 2 * Math.PI)) - 90;
    map.flyTo({ center: [(w + e) / 2, lat], zoom, pitch: 0, bearing: 0, padding: pad,
                duration: 2500, essential: true });
  }

  function selectRegion(r, { fly = true } = {}) {
    if (focus) map.setFeatureState({ source: 'regions', id: focus.id }, { selected: false });
    focus = r;
    map.setFeatureState({ source: 'regions', id: r.id }, { selected: true });
    regionSelect.value = String(r.id);
    applyFilters();
    renderRegion();
    regionPanel.hidden = false;
    document.body.classList.add('region-open');
    setHash('region', r.id);
    stopOrbit();
    flightToken++;
    if (fly) flyToRegion(r);
  }
  function clearRegion() {
    if (!focus) return;
    map.setFeatureState({ source: 'regions', id: focus.id }, { selected: false });
    focus = null;
    regionSelect.value = '';
    regionPanel.hidden = true;
    document.body.classList.remove('region-open');
    applyFilters();
  }
  function exitRegion() {
    clearRegion();
    setHash(null);
    map.flyTo({ ...HOME(), padding: { left: 0, right: 0, top: 0, bottom: 0 }, duration: 2500 });
  }
  // close the peak card without flying anywhere (another camera move follows)
  function closeCardQuiet() {
    card.hidden = true;
    document.body.classList.remove('peak-open');
    if (selected != null) map.setFeatureState({ source: 'peaks', id: selected }, { selected: false });
    selected = null;
  }
  regionPanel.querySelector('.back').onclick = exitRegion;
  regionPanel.querySelectorAll('.sort button').forEach(b => b.onclick = () => {
    regionSort = b.dataset.sort;
    regionPanel.querySelectorAll('.sort button').forEach(x => x.classList.toggle('active', x === b));
    renderRegion();
  });

  function renderRegion() {
    const r = focus;
    const ps = peaks.filter(p => p.reg === r.id);
    document.getElementById('region-country').textContent = COUNTRIES[r.country];
    document.getElementById('region-name').textContent = nm(r);
    const closest = Math.min(...ps.map(p => p.min)), highest = Math.max(...ps.map(p => p.ele));
    document.getElementById('region-meta').textContent =
      `${ps.length} peaks · closest ${fmtTime(closest)} · highest ${highest.toLocaleString('en')} m`;
    const key = { rank: p => p.rank, ele: p => -p.ele, min: p => p.min }[regionSort];
    ps.sort((a, b) => key(a) - key(b));
    const ol = document.getElementById('region-list');
    ol.replaceChildren(...ps.map(p => {
      const li = document.createElement('li');
      const dot = document.createElement('span');
      dot.className = 'dot';
      dot.style.background = eleHex(p.ele);
      const nm = document.createElement('span');
      nm.className = 'nm';
      nm.textContent = p.name;
      const v = document.createElement('span');
      v.className = 'v';
      v.textContent = `${p.ele.toLocaleString('en')} m · ${fmtTime(p.min)}`;
      li.append(dot, nm, v);
      li.onclick = () => selectPeak(p);
      return li;
    }));
    ol.scrollTop = 0;
  }
  map.on('mouseenter', 'peaks', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'peaks', () => { map.getCanvas().style.cursor = ''; });

  // ---- Search -----------------------------------------------------------
  const dl = document.getElementById('peak-names');
  const nameIdx = new Map();
  for (const p of [...peaks].sort((a, b) => a.name.localeCompare(b.name))) {
    const key = `${p.name} (${p.ele} m)`;
    nameIdx.set(key.toLowerCase(), p);
    const opt = document.createElement('option');
    opt.value = key;
    dl.appendChild(opt);
  }
  const search = document.getElementById('search');
  search.addEventListener('change', () => {
    const q = search.value.trim().toLowerCase();
    if (!q) return;
    // peaks are in fame order, so the first match is the best-known one
    const names = x => [x.name, x.alt].filter(Boolean).map(n => n.toLowerCase());
    const p = nameIdx.get(q) || peaks.find(x => names(x).some(n => n.startsWith(q)))
                             || peaks.find(x => names(x).some(n => n.includes(q)));
    if (p) { selectPeak(p); search.value = ''; search.blur(); }
  });

  // Deep links: #peak=<osm id> or #region=<osm relation id>. Updated only on select/close (not
  // on moveend: the orbit moves the map every frame, and browsers throttle replaceState).
  function setHash(kind, id) {
    const url = kind ? `#${kind}=${id}` : location.pathname + location.search;
    try { history.replaceState(null, '', url); } catch (_) { /* ignore */ }
  }
  const mp = location.hash.match(/peak=(\d+)/), mr = location.hash.match(/region=(\d+)/);
  if (mp && byId.has(+mp[1])) {
    const p = byId.get(+mp[1]);
    if (regById.has(p.reg)) selectRegion(regById.get(p.reg), { fly: false });
    selectPeak(p);
  } else if (mr && regById.has(+mr[1])) selectRegion(regById.get(+mr[1]));
})();
