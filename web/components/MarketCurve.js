"use client";

const SIGNAL_COLOR = {
  boom: "#3ddc97",
  firm: "#2ec4b6",
  fair: "#d4af37",
  soft: "#e8943a",
  bust: "#ef6b73",
};

/** Map marker 0..1 along the boom→bust path into an approximate peak-ish point. */
function markerPoint(t) {
  const x = 28 + Math.max(0, Math.min(1, t)) * (332 - 28);
  // Mirror the cubic-ish arch used in the SVG path (peak near center).
  const u = (x - 28) / (332 - 28);
  const arch = 1 - Math.pow(2 * u - 1, 2);
  const y = 122 - arch * 94;
  return { x, y };
}

export default function MarketCurve({ prediction }) {
  const ready = Boolean(prediction?.ready);
  const signal = (prediction?.signal || "fair").toLowerCase();
  const label = prediction?.label || (ready ? "Fair" : "…");
  const note = prediction?.note || (ready ? "" : "Loading market signal…");
  const color = SIGNAL_COLOR[signal] || SIGNAL_COLOR.fair;
  const marker = ready ? markerPoint(Number(prediction?.marker ?? 0.5)) : null;

  return (
    <div className="market-card" data-signal={ready ? signal : "loading"}>
      <svg viewBox="0 0 360 150" role="img" aria-label={`Market prediction ${label}`}>
        <line x1="24" y1="122" x2="336" y2="122" stroke="#243049" />
        <path
          d="M28 122 C 78 122, 110 28, 180 28 C 250 28, 282 122, 332 122"
          fill="rgba(46,196,182,0.12)"
          stroke="#2ec4b6"
          strokeWidth="2.5"
        />
        <text x="36" y="96" fill="#3ddc97" fontSize="13" fontWeight="700">Boom</text>
        <text x="180" y="20" fill="#e8943a" fontSize="13" fontWeight="700" textAnchor="middle">Peak</text>
        <text x="300" y="96" fill="#ef6b73" fontSize="13" fontWeight="700" textAnchor="end">Bust</text>
        {marker ? (
          <>
            <line
              x1={marker.x}
              y1={marker.y}
              x2={marker.x}
              y2="122"
              stroke={color}
              strokeDasharray="4 4"
            />
            <circle cx={marker.x} cy={marker.y} r="6" fill={color} stroke="#0b1220" strokeWidth="2" />
            <text
              x={marker.x}
              y={Math.max(18, marker.y - 12)}
              fill={color}
              fontSize="13"
              fontWeight="700"
              textAnchor="middle"
            >
              {label}
            </text>
          </>
        ) : null}
      </svg>
      <p className="market-note">{note || " "}</p>
    </div>
  );
}
