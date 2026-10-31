import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import type { MapFlight, MapPayload } from "../types";
import { hhmm } from "../types";

type LL = [number, number];

/** Great-circle points between two lat/lon pairs (spherical slerp). */
function arc(a: LL, b: LL, n = 48): LL[] {
  const r = Math.PI / 180;
  const [p1, l1, p2, l2] = [a[0] * r, a[1] * r, b[0] * r, b[1] * r];
  const v1 = [Math.cos(p1) * Math.cos(l1), Math.cos(p1) * Math.sin(l1), Math.sin(p1)];
  const v2 = [Math.cos(p2) * Math.cos(l2), Math.cos(p2) * Math.sin(l2), Math.sin(p2)];
  const d = Math.acos(Math.min(1, v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]));
  if (d < 1e-9) return [a, b];
  const out: LL[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const s1 = Math.sin((1 - t) * d) / Math.sin(d);
    const s2 = Math.sin(t * d) / Math.sin(d);
    const x = s1 * v1[0] + s2 * v2[0], y = s1 * v1[1] + s2 * v2[1], z = s1 * v1[2] + s2 * v2[2];
    out.push([Math.atan2(z, Math.hypot(x, y)) / r, Math.atan2(y, x) / r]);
  }
  return out;
}

const STYLE: Record<MapFlight["role"], L.PolylineOptions> = {
  disrupted: { color: "#facc15", weight: 5, opacity: 1 },
  bank: { color: "#38bdf8", weight: 1.5, opacity: 0.7 },
  connection: { color: "#a78bfa", weight: 2, opacity: 0.85, dashArray: "6 6" },
};

/** Fraction of the flight completed at `now` (time-zone naive; position estimated). */
function progress(f: MapFlight, now: number, eta: number | null): number | null {
  const arr = eta ?? f.est_arr_min ?? f.sched_arr_min;
  if (now <= f.sched_dep_min || now >= arr || arr <= f.sched_dep_min) return null;
  return (now - f.sched_dep_min) / (arr - f.sched_dep_min);
}

export function TrafficMap({ map, etaNew, chaos }: { map: MapPayload; etaNew: number | null; chaos: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const lm = useRef<L.Map | null>(null);
  const layer = useRef<L.LayerGroup | null>(null);

  useEffect(() => {
    if (!el.current || lm.current) return;
    const m = L.map(el.current, { zoomControl: false, attributionControl: false, preferCanvas: false });
    const tiles = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 10 });
    tiles.on("tileerror", () => m.removeLayer(tiles)); // plain background + airport dots if tiles fail
    tiles.addTo(m);
    lm.current = m;
    layer.current = L.layerGroup().addTo(m);
    return () => {
      m.remove();
      lm.current = null;
    };
  }, []);

  useEffect(() => {
    const m = lm.current, g = layer.current;
    if (!m || !g) return;
    g.clearLayers();
    const ap = Object.fromEntries(map.airports.map((a) => [a.iata, a]));
    const order = { bank: 0, connection: 1, disrupted: 2 } as const;
    const flights = [...map.flights].sort((a, b) => order[a.role] - order[b.role]);
    for (const f of flights) {
      const pts = arc([f.origin_lat, f.origin_lon], [f.dest_lat, f.dest_lon]);
      L.polyline(pts, STYLE[f.role]).addTo(g);
      const eta = f.role === "disrupted" ? (etaNew ?? f.est_arr_min) : null;
      const p = progress(f, map.now_min, eta);
      if (p != null) {
        const pos = pts[Math.round(p * (pts.length - 1))];
        const big = f.role === "disrupted";
        L.circleMarker(pos, { radius: big ? 6 : 3, color: big ? "#facc15" : "#e2e8f0", fillOpacity: 1, weight: 1 })
          .bindTooltip(`${f.flight_id} (position estimated)`, { direction: "top" })
          .addTo(g);
      }
      if (f.role === "disrupted") {
        L.marker([f.dest_lat, f.dest_lon], {
          icon: L.divIcon({
            className: "",
            html: `<div class="map-eta ${etaNew != null ? "map-eta-new" : ""}">${f.flight_id} ETA ${hhmm(eta)}</div>`,
            iconAnchor: [-14, 30],
          }),
        }).addTo(g);
      }
    }
    for (const a of map.airports) {
      const focus = a.iata === map.focus_airport;
      L.circleMarker([a.lat, a.lon], {
        radius: focus ? 5 : a.role === "origin" ? 4 : 2.5,
        color: focus ? "#fff" : a.role === "origin" ? "#facc15" : "#64748b",
        fillOpacity: 1,
        weight: 1,
      })
        .bindTooltip(a.iata, { permanent: focus || a.role === "origin", direction: "right", className: "map-label" })
        .addTo(g);
      if (focus) {
        L.circleMarker([a.lat, a.lon], { radius: 18, color: chaos ? "#f59e0b" : "#22d3ee", weight: chaos ? 4 : 2, fill: false, className: chaos ? "ring-pulse" : "" }).addTo(g);
      }
    }
    const b = L.latLngBounds(map.airports.map((a) => [a.lat, a.lon] as LL));
    if (b.isValid()) m.fitBounds(b, { padding: [24, 24] });
  }, [map, etaNew, chaos]);

  return (
    <div className="relative">
      <div ref={el} className="h-80 w-full rounded-b-lg bg-slate-900" />
      <div className="pointer-events-none absolute bottom-1 left-2 z-[500] flex gap-3 text-[10px] text-slate-400">
        <span className="text-yellow-300">━ disrupted</span>
        <span className="text-sky-300">─ arrival bank ({map.flights.filter((f) => f.role === "bank").length})</span>
        <span className="text-violet-300">┅ connections ({map.flights.filter((f) => f.role === "connection").length})</span>
        <span>clock {hhmm(map.now_min)} · positions estimated</span>
      </div>
    </div>
  );
}
