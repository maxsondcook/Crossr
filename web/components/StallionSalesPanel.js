"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet } from "../lib/api";

const CATS = [
  ["yearlings", "Yearlings", "var(--accent, #e3a24a)"],
  ["weanlings", "Weanlings", "#5fb8a6"],
  ["all", "All horses", "#8aa0c8"],
];

function money(n) {
  if (n == null) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

function SummaryTable({ data }) {
  const periods = [
    ["current", `${data.current_year} (to date)`],
    ["latest", `${data.latest_completed_year}`],
    ["last3", `${data.latest_completed_year - 2}–${data.latest_completed_year}`],
    ["lifetime", "Lifetime"],
  ];
  return (
    <div className="history-wrap">
      <table>
        <thead>
          <tr>
            <th>Average price</th>
            {periods.map(([k, label]) => <th key={k}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {CATS.map(([cat, label]) => (
            <tr key={cat}>
              <td>{label}</td>
              {periods.map(([p]) => {
                const s = data.summary?.[cat]?.[p];
                return (
                  <td key={p} className="money" title={s ? `${s.sold} sold of ${s.offered} offered · median ${money(s.median)}` : ""}>
                    {s && s.average != null ? money(s.average) : "—"}
                    {s && s.sold ? <span className="muted" style={{ fontSize: 12 }}> · {s.sold}</span> : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="sub" style={{ fontSize: 12, marginTop: 6 }}>
        Sold lots only (RNAs not counted as sales, outs excluded); small number = horses sold.
        {` ${data.current_year} is incomplete, so annual averages use ${data.latest_completed_year}.`}
      </p>
    </div>
  );
}

function YearChart({ rows }) {
  const [hidden, setHidden] = useState({});
  const W = 640, H = 220, P = { l: 56, r: 12, t: 12, b: 28 };
  const shown = CATS.filter(([cat]) => !hidden[cat]);
  const values = rows.flatMap((r) => shown.map(([cat]) => r[`${cat}_avg`]).filter((v) => v != null));
  if (!rows.length || !values.length) return <p className="catalog-empty">No priced sales by year.</p>;
  const max = Math.max(...values) * 1.08;
  const x = (i) => P.l + (rows.length === 1 ? 0 : (i * (W - P.l - P.r)) / (rows.length - 1));
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const step = Math.max(1, Math.ceil(rows.length / 10));
  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 6 }}>
        {CATS.map(([cat, label, color]) => (
          <label key={cat} style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer", fontSize: 13 }}>
            <input type="checkbox" checked={!hidden[cat]} onChange={() => setHidden((h) => ({ ...h, [cat]: !h[cat] }))} />
            <span style={{ width: 12, height: 3, background: color, display: "inline-block" }} />
            {label}
          </label>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img" aria-label="Average sale price by year">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="currentColor" opacity="0.12" />
            <text x={P.l - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="currentColor" opacity="0.7">
              {t >= 1e6 ? `$${(t / 1e6).toFixed(1)}M` : `$${Math.round(t / 1000)}k`}
            </text>
          </g>
        ))}
        {rows.map((r, i) => (i % step === 0 || i === rows.length - 1) ? (
          <text key={r.year} x={x(i)} y={H - 8} fontSize="10" textAnchor="middle" fill="currentColor" opacity="0.7">
            {r.year}{r.complete ? "" : "*"}
          </text>
        ) : null)}
        {shown.map(([cat, label, color]) => {
          // Break the line at years with no sales instead of drawing through them.
          const segs = [];
          let cur = [];
          rows.forEach((r, i) => {
            const v = r[`${cat}_avg`];
            if (v == null) { if (cur.length) segs.push(cur); cur = []; } else cur.push([x(i), y(v), r, v]);
          });
          if (cur.length) segs.push(cur);
          return (
            <g key={cat}>
              {segs.map((seg, k) => (
                <polyline key={k} fill="none" stroke={color} strokeWidth="2" points={seg.map(([a, b]) => `${a},${b}`).join(" ")} />
              ))}
              {segs.flat().map(([a, b, r, v]) => (
                <circle key={`${cat}-${r.year}`} cx={a} cy={b} r="3" fill={color}>
                  <title>{`${label} ${r.year}: ${money(v)} (${r[`${cat}_sold`]} sold)`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
      <p className="sub" style={{ fontSize: 12 }}>* year in progress. Gaps are years with no sales in that category.</p>
    </div>
  );
}

const SORTS = {
  hip_asc: (a, b) => (parseInt(a.hip, 10) || 0) - (parseInt(b.hip, 10) || 0),
  hip_desc: (a, b) => (parseInt(b.hip, 10) || 0) - (parseInt(a.hip, 10) || 0),
  price_desc: (a, b) => (b.price || 0) - (a.price || 0),
  price_asc: (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
};

function SaleHorses({ lots, hrefFor }) {
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");
  const [sex, setSex] = useState("all");
  const [bms, setBms] = useState([]);
  const [sort, setSort] = useState("hip_asc");
  const types = useMemo(() => [...new Set(lots.map((l) => l.type))].sort(), [lots]);
  const sexes = useMemo(() => [...new Set(lots.map((l) => l.sex).filter(Boolean))].sort(), [lots]);
  const damsires = useMemo(() => [...new Set(lots.map((l) => l.damsire).filter(Boolean))].sort(), [lots]);
  useEffect(() => { setStatus("all"); setType("all"); setSex("all"); setBms([]); }, [lots]);
  const shown = lots
    .filter((l) => status === "all" || l.status === status)
    .filter((l) => type === "all" || l.type === type)
    .filter((l) => sex === "all" || l.sex === sex)
    .filter((l) => !bms.length || bms.includes(l.damsire))
    .slice()
    .sort(SORTS[sort]);
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-start" }}>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Sold status">
          <option value="all">Sold &amp; not sold</option>
          <option value="sold">Sold</option>
          <option value="not sold">Not sold (RNA)</option>
          <option value="out">Out</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Horse type">
          <option value="all">All types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={sex} onChange={(e) => setSex(e.target.value)} aria-label="Sex">
          <option value="all">All sexes</option>
          {sexes.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="hip_asc">Hip ↑</option>
          <option value="hip_desc">Hip ↓</option>
          <option value="price_desc">Price ↓</option>
          <option value="price_asc">Price ↑</option>
        </select>
        <select
          multiple
          value={bms}
          onChange={(e) => setBms([...e.target.selectedOptions].map((o) => o.value))}
          aria-label="Broodmare sires"
          title="Broodmare sires (Ctrl/Cmd-click for several)"
          style={{ minWidth: 180, height: 72 }}
        >
          {damsires.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        {bms.length ? <button type="button" className="ghost" onClick={() => setBms([])}>Clear sires</button> : null}
      </div>
      <div className="history-wrap" style={{ marginTop: 8 }}>
        <table>
          <thead>
            <tr><th>Hip</th><th>Horse</th><th>Type</th><th>Sex</th><th>Broodmare Sire</th><th>Status</th><th>Price</th></tr>
          </thead>
          <tbody>
            {shown.map((l) => (
              <tr key={l.id}>
                <td>{l.hip}</td>
                <td>{l.name ? <Link href={hrefFor(l.name)}>{l.name}</Link> : "—"}</td>
                <td>{l.type}</td>
                <td>{l.sex || "—"}</td>
                <td>{l.damsire || "—"}</td>
                <td>{l.status}</td>
                <td className="money">{l.status === "sold" ? money(l.price) : (l.price_raw || "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!shown.length ? <p className="catalog-empty">No horses match these filters.</p> : null}
      </div>
    </div>
  );
}

export default function StallionSalesPanel({ name, hrefFor }) {
  const [data, setData] = useState(null);
  const [catalogId, setCatalogId] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setError("");
    const q = catalogId ? `?catalog_id=${catalogId}` : "";
    apiGet(`/api/sales/sire/${encodeURIComponent(name)}/summary${q}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [name, catalogId]);
  useEffect(() => { setCatalogId(null); setData(null); }, [name]);

  if (error) return <div className="panel panel-wide"><h4>SALES</h4><p className="error">{error}</p></div>;
  if (!data) return <div className="panel panel-wide"><h4>SALES</h4><p className="catalog-empty">Loading…</p></div>;
  if (!data.lots_total) return null; // no progeny ever offered: hide the panel
  const sale = data.sales.find((s) => s.catalog_id === data.selected_catalog_id);
  const ss = data.sale_stats || {};
  return (
    <div className="panel panel-wide">
      <h4>SALES · {data.lots_total.toLocaleString()} PROGENY OFFERED</h4>
      <SummaryTable data={data} />
      <h4 style={{ marginTop: 16 }}>AVERAGE PRICE BY YEAR</h4>
      <YearChart rows={data.by_year} />
      <h4 style={{ marginTop: 16 }}>BY SALE</h4>
      <select
        value={data.selected_catalog_id || ""}
        onChange={(e) => setCatalogId(Number(e.target.value))}
        aria-label="Sale"
        style={{ maxWidth: "100%" }}
      >
        {data.sales.map((s) => (
          <option key={s.catalog_id} value={s.catalog_id}>
            {s.year} · {s.title} — {s.progeny} offered, {s.sold} sold
          </option>
        ))}
      </select>
      {sale ? (
        <div className="kpi-row" style={{ marginTop: 10 }}>
          {CATS.map(([cat, label]) => ss[cat]?.offered ? (
            <div className="kpi" key={cat}>
              <span>{label}</span>
              <b>{money(ss[cat].average)}</b>
              <span className="muted" style={{ fontSize: 12 }}>
                {ss[cat].sold}/{ss[cat].offered} sold · high {money(ss[cat].high)}
              </span>
            </div>
          ) : null)}
        </div>
      ) : null}
      <SaleHorses lots={data.sale_lots || []} hrefFor={hrefFor} />
    </div>
  );
}
