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

function accuracyNote(expected, lot) {
  const sold = Number(lot?.price_num);
  const mid = Number(expected?.mid);
  const low = Number(expected?.low);
  const high = Number(expected?.high);
  if (!Number.isFinite(sold) || sold <= 0) return "";
  const bits = [];
  if (Number.isFinite(low) && Number.isFinite(high) && low > 0 && high > 0) {
    const inRange = sold >= low && sold <= high;
    bits.push(
      inRange
        ? `Sold inside expected market ${money(low)}–${money(high)}`
        : `Sold outside expected market ${money(low)}–${money(high)}`
    );
  }
  if (Number.isFinite(mid) && mid > 0) {
    const delta = sold - mid;
    const pct = Math.round((delta / mid) * 100);
    const sign = delta >= 0 ? "+" : "−";
    bits.push(`vs mid ${money(mid)} (${sign}${Math.abs(pct)}%)`);
  }
  return bits.join(" · ");
}

export default function ProjectedValue({ valueProjector, expectedMarket, lot, showSold }) {
  const vp = valueProjector || {};
  const breeding = breedingLabel(vp);
  const race = raceLabel(vp);
  const sold = showSold ? soldLabel(lot) : "";
  const showBreeding = Boolean(breeding);
  const showRace = Boolean(race);
  const cols = [showBreeding, showRace, showSold].filter(Boolean).length;
  const ready = Boolean(breeding || race || sold);
  const note = showSold ? accuracyNote(expectedMarket, lot) : "";
  const marketLabel = expectedMarket?.label || "";
  const marketRule = expectedMarket?.rule || "";

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
      {showSold && marketLabel ? (
        <p className="pv-note" data-pv="expected-vs-sold">
          Expected market {marketLabel}
          {note ? ` · ${note}` : ""}
        </p>
      ) : null}
      {showSold && marketRule ? (
        <p className="pv-note meta-sub">{marketRule}</p>
      ) : null}
    </div>
  );
}
