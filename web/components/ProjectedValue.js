"use client";

function money(n) {
  if (n == null || n === "") return "";
  const num = Number(n);
  if (!Number.isFinite(num) || !num) return "";
  return `$${Math.round(num).toLocaleString()}`;
}

function breedingLabel(vp) {
  if (!vp) return "";
  if (vp.breeding_ok === false && !vp.display && vp.point == null) return "";
  if (vp.display) return vp.display;
  if (vp.low != null && vp.high != null && vp.low !== vp.high) {
    return `${money(vp.low)}–${money(vp.high)}`;
  }
  return money(vp.point) || "";
}

function raceLabel(vp) {
  if (!vp) return "";
  const raw = (vp.projected_race_earnings || "").trim();
  if (raw) return raw;
  return "";
}

function soldLabel(lot) {
  if (!lot) return "";
  const raw = lot.price_raw == null ? "" : String(lot.price_raw).trim();
  if (lot.is_rna) {
    if (!raw || raw.toUpperCase() === "RNA") return "RNA";
    return raw.toUpperCase().startsWith("RNA") ? raw : `RNA ${raw}`;
  }
  if (raw && lot.price_num) return raw;
  if (lot.price_num) return money(lot.price_num);
  if (lot.is_out) return "OUT";
  return "";
}

export default function ProjectedValue({ valueProjector, lot, showSold }) {
  const vp = valueProjector || {};
  const breeding = breedingLabel(vp);
  const race = raceLabel(vp);
  const sold = showSold ? soldLabel(lot) : "";
  const showBreeding = Boolean(breeding);
  const showRace = Boolean(race);
  const cols = [showBreeding, showRace, showSold].filter(Boolean).length;
  const ready = Boolean(breeding || race || sold);

  return (
    <div className="projected-value" data-ready={ready ? "1" : "0"} data-cols={cols || 1}>
      <div className={`pv-grid cols-${cols || 1}`}>
        {showBreeding ? (
          <div className="pv-item" data-pv="breeding">
            <span className="pv-label">Breeding value</span>
            <b className="money">{breeding}</b>
          </div>
        ) : null}
        {showRace ? (
          <div className="pv-item" data-pv="race">
            <span className="pv-label">Projected race value</span>
            <b className="money">{race}</b>
          </div>
        ) : null}
        {showSold ? (
          <div className="pv-item" data-pv="sold">
            <span className="pv-label">Sold</span>
            <b className="money">{sold || "—"}</b>
          </div>
        ) : null}
        {!showBreeding && !showRace && !showSold ? (
          <div className="pv-item">
            <span className="pv-label">Projected value</span>
            <b>—</b>
          </div>
        ) : null}
      </div>
    </div>
  );
}
