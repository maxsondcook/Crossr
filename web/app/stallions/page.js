"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiGet, horseHref } from "../../lib/api";
import { isStarred, toggleStar } from "../../lib/barn";

export default function StallionsPage() {
  const [rows, setRows] = useState([]);
  const [farms, setFarms] = useState([]);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("rank");
  const [showFilters, setShowFilters] = useState(false);
  const [farm, setFarm] = useState("");
  const [minFee, setMinFee] = useState("");
  const [maxFee, setMaxFee] = useState("");
  const [studMin, setStudMin] = useState("");
  const [studMax, setStudMax] = useState("");
  const [crop, setCrop] = useState("");
  const [compare, setCompare] = useState([]);
  const [error, setError] = useState("");
  const [stars, setStars] = useState(0);

  useEffect(() => {
    apiGet("/api/stallions/farms").then((d) => setFarms(d.farms || [])).catch(() => {});
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ sort, q, farm, crop });
    if (minFee) params.set("min_fee", minFee);
    if (maxFee) params.set("max_fee", maxFee);
    if (studMin) params.set("stud_year_min", studMin);
    if (studMax) params.set("stud_year_max", studMax);
    apiGet(`/api/stallions?${params}`)
      .then((d) => {
        setRows(d.stallions || []);
        setError("");
      })
      .catch((e) => setError(e.message));
  }, [q, sort, farm, minFee, maxFee, studMin, studMax, crop]);

  const visible = useMemo(() => rows, [rows]);

  function star(name, ev) {
    ev.preventDefault();
    ev.stopPropagation();
    toggleStar(name);
    setStars((n) => n + 1);
  }

  function toggleCompare(name, ev) {
    ev.preventDefault();
    ev.stopPropagation();
    setCompare((cur) => (cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name].slice(0, 2)));
  }

  return (
    <div>
      <div className="search-row">
        <div className="search-box">
          <span>⌕</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="LOOK UP A STALLION..."
          />
        </div>
        <button className="ghost" onClick={() => setShowFilters((v) => !v)}>Filter</button>
        <select className="ghost" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="rank">Sort: Rank</option>
          <option value="name">Sort: A–Z</option>
          <option value="fee_desc">Sort: Stud fee (high)</option>
          <option value="fee_asc">Sort: Stud fee (low)</option>
          <option value="stud_year">Sort: Year entered stud</option>
        </select>
        {compare.length === 2 ? (
          <Link className="primary" href={`/compare?a=${encodeURIComponent(compare[0])}&b=${encodeURIComponent(compare[1])}`}>
            Compare
          </Link>
        ) : (
          <button className="primary" disabled>Compare</button>
        )}
      </div>

      {showFilters ? (
        <div className="filters">
          <label>
            Standing location
            <select value={farm} onChange={(e) => setFarm(e.target.value)}>
              <option value="">All farms</option>
              {farms.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </label>
          <label>
            Min stud fee
            <input value={minFee} onChange={(e) => setMinFee(e.target.value)} placeholder="0" />
          </label>
          <label>
            Max stud fee
            <input value={maxFee} onChange={(e) => setMaxFee(e.target.value)} placeholder="250000" />
          </label>
          <label>
            Entered stud from
            <input value={studMin} onChange={(e) => setStudMin(e.target.value)} placeholder="2015" />
          </label>
          <label>
            Crop
            <select value={crop} onChange={(e) => setCrop(e.target.value)}>
              <option value="">Any</option>
              <option value="First-crop">First-crop</option>
              <option value="Second-crop">Second-crop</option>
              <option value="yearling">First yearlings</option>
              <option value="weanling">First weanlings</option>
              <option value="Established">Established</option>
            </select>
          </label>
        </div>
      ) : null}

      {error ? <p className="error">{error}</p> : null}

      <div className="stallion-list">
        {visible.map((s) => (
          <Link key={s.key} href={horseHref(s.name)} className="stallion-card">
            <img src="/logo.png" alt="" />
            <div>
              <h3>{s.name}</h3>
              <div className="parents">
                {(s.sire || "Unknown") + " × " + (s.dam || "Unknown")}
              </div>
            </div>
            <div>
              <div className="meta-label">Stud Fee & Standing Location</div>
              <div><span className="fee">{s.stud_fee}</span> | {s.farm}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className={`badge ${String(s.badge || "").includes("Young") ? "young" : ""}`}>{s.badge}</span>
              <button className="star" onClick={(e) => star(s.name, e)} title="Star">{isStarred(s.name) && stars >= 0 ? "★" : "☆"}</button>
              <button className="ghost" onClick={(e) => toggleCompare(s.name, e)}>
                {compare.includes(s.name) ? "Added" : "+"}
              </button>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
