"use client";

function money(n) {
  if (n == null || n === "") return "";
  const num = Number(n);
  if (!Number.isFinite(num) || !num) return "";
  return `$${Math.round(num).toLocaleString()}`;
}

function breedingLabel(vp) {
  if (!vp?.ok) return "";
  if (vp.display) return vp.display;
  if (vp.low != null && vp.high != null && vp.low !== vp.high) {
    return `${money(vp.low)}–${money(vp.high)}`;
  }
  return money(vp.point) || "";
}

function raceLabel(vp) {
  if (!vp?.ok) return "";
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

function accuracyNote(expected, lot) {
  const sold = Number(lot?.price_num);
  const mid = Number(expected?.mid);
  if (!Number.isFinite(sold) || sold <= 0 || !Number.isFinite(mid) || mid <= 0) return "";
  const delta = sold - mid;
  const pct = Math.round((delta / mid) * 100);
  const sign = delta >= 0 ? "+" : "−";
  return `vs expected market mid ${money(mid)} (${sign}${Math.abs(pct)}%)`;
}

export default function ProjectedValue({ valueProjector, expectedMarket, lot, showSold }) {
  const vp = valueProjector || {};
  const breeding = breedingLabel(vp);
  const race = raceLabel(vp);
  const sold = showSold ? soldLabel(lot) : "";
  const ready = Boolean(vp.ok && (breeding || race));
  const note = showSold ? accuracyNote(expectedMarket, lot) : "";

  return (
    <div className="projected-value" data-ready={ready ? "1" : "0"}>
      <div className={`pv-grid${showSold ? " with-sold" : ""}`}>
        <div className="pv-item">
          <span className="pv-label">Breeding value</span>
          <b className="money">{ready && breeding ? breeding : "—"}</b>
        </div>
        <div className="pv-item">
          <span className="pv-label">Projected race value</span>
          <b className="money">{ready && race ? race : "—"}</b>
        </div>
        {showSold ? (
          <div className="pv-item" data-pv="sold">
            <span className="pv-label">Sold</span>
            <b className="money">{sold || "—"}</b>
          </div>
        ) : null}
      </div>
      {note ? <p className="pv-note">{note}</p> : null}
      {!ready && vp?.detail ? (
        <p className="pv-note">{vp.detail}</p>
      ) : null}
    </div>
  );
}
