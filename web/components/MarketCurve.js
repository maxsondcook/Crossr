"use client";

export default function MarketCurve() {
  return (
    <div className="market-card">
      <svg viewBox="0 0 360 150" role="img" aria-label="Market prediction placeholder">
        <line x1="24" y1="122" x2="336" y2="122" stroke="#243049" />
        <path
          d="M28 122 C 78 122, 110 28, 180 28 C 250 28, 282 122, 332 122"
          fill="rgba(46,196,182,0.18)"
          stroke="#2ec4b6"
          strokeWidth="2.5"
        />
        <line x1="180" y1="28" x2="180" y2="122" stroke="#d4af37" strokeDasharray="4 4" />
        <text x="36" y="96" fill="#3ddc97" fontSize="13" fontWeight="700">Boom</text>
        <text x="180" y="20" fill="#e8943a" fontSize="13" fontWeight="700" textAnchor="middle">Bust</text>
      </svg>
      <p className="market-note">Placeholder until the market model is connected.</p>
    </div>
  );
}
