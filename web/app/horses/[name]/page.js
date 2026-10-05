"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { apiGet, horseHref } from "../../../lib/api";
import { isStarred, toggleStar, saveFavorite } from "../../../lib/barn";
import PedigreeChart from "../../../components/PedigreeChart";

function money(n) {
  if (n == null) return "—";
  return `$${Number(n).toLocaleString()}`;
}

function FoalLine({ p }) {
  const sexBit = p.sex ? `${p.sex}. ` : "";
  const name = p.status || p.is_subject ? p.name.toUpperCase() : p.name;
  return (
    <div className={`ff-foal${p.is_subject ? " subject" : ""}${p.status ? " stakes" : ""}`}>
      <Link href={horseHref(p.name)}>{name}</Link>
      {p.year ? <span className="yr"> ({p.year})</span> : null}
      {p.sire ? <> ({sexBit}by <Link href={horseHref(p.sire)}>{p.sire}</Link>)</> : null}
      {p.is_subject ? ". Black-type winner, below." : p.status ? `. ${p.status}.` : "."}
      {(p.races || []).length ? ` ${(p.races).join(", ")}.` : null}
      {(p.produce || []).map((g) => (
        <div className="ff-grand" key={`${g.name}-${g.sire}`}>
          Dam of <Link href={horseHref(g.name)}>{g.status ? g.name.toUpperCase() : g.name}</Link>
          {g.sire ? <> ({g.sex ? `${g.sex}. ` : ""}by <Link href={horseHref(g.sire)}>{g.sire}</Link>)</> : null}
          {g.status ? `. ${g.status}.` : "."}
          {(g.races || []).length ? ` ${g.races.join(", ")}.` : null}
        </div>
      ))}
    </div>
  );
}

export default function HorsePage() {
  const { name } = useParams();
  const decoded = decodeURIComponent(name || "");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setData(null);
    apiGet(`/api/horses/${encodeURIComponent(decoded)}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [decoded]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="empty">Loading profile…</p>;

  const s = data.stallion || {};
  const racing = s.progeny_racing || {};
  const earn = s.progeny_earnings || {};
  const totals = data.race_totals || {};
  const family = data.female_family || [];

  return (
    <div className="dash">
      <div>
        <div className="panel">
          <h4>SALES CATALOG PEDIGREE</h4>
          <PedigreeChart tree={data.pedigree} showSubject={false} />
        </div>
        <div className="panel family-panel" style={{ marginTop: 12 }}>
          <h4>FEMALE FAMILY</h4>
          {family.length === 0 ? (
            <p className="empty">No dam line on file for this horse yet.</p>
          ) : family.map((d) => (
            <div className="ff-block" key={d.ordinal}>
              <div className="ff-ord">{d.ordinal}</div>
              <div className="ff-head">
                <Link href={horseHref(d.name)}>{(d.name || "").toUpperCase()}</Link>
                {d.year ? ` (${d.year})` : ""}
                {d.sire ? <>, by <Link href={horseHref(d.sire)}>{d.sire}</Link>.</> : "."}
                {d.status ? ` ${d.status}.` : ""}
              </div>
              <div className="ff-racing">
                {(d.racing || []).length
                  ? d.racing.join("; ")
                  : "Racing record not on file."}
              </div>
              <div className="ff-prod-label">Produce</div>
              {(d.produce || []).length === 0 ? (
                <p className="empty">No produce on file yet.</p>
              ) : (
                d.produce.map((p) => <FoalLine key={`${p.name}-${p.sire}`} p={p} />)
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <div className="hero">
          <div className="farm">{s.farm || "PEDIGREE PROFILE"}</div>
          <h1>{data.name.toUpperCase()}</h1>
          <div className="sub">
            Foaled: {s.year_foaled || data.year || "—"} · Entered Stud: {s.entered_stud || "—"}
          </div>
          <div className="kpi-row">
            <div className="kpi">
              <span>Stud Fee</span>
              <b>{s.stud_fee || "—"}</b>
            </div>
            <div className="kpi">
              <span>Sire Rank</span>
              <b className="muted">{s.rank ? `#${s.rank}` : "NA"}</b>
            </div>
          </div>
        </div>
        <h4 style={{ marginTop: 16 }}>RACE RECORD & MAJOR WINS</h4>
        <table>
          <thead>
            <tr>
              <th>Season</th><th>Age</th><th>Starts</th><th>1st</th><th>2nd</th><th>3rd</th><th>Earnings</th>
            </tr>
          </thead>
          <tbody>
            {(data.race_record || []).map((r) => (
              <tr key={r.age}>
                <td>{r.season}</td>
                <td>{r.age}</td>
                <td>{r.starts}</td>
                <td>{r.firsts}</td>
                <td>{r.seconds}</td>
                <td>{r.thirds}</td>
                <td className="money">{r.earnings_display}</td>
              </tr>
            ))}
            <tr>
              <td>TOTAL</td>
              <td>—</td>
              <td>{totals.starts || 0}</td>
              <td>{totals.firsts || 0}</td>
              <td>{totals.seconds || 0}</td>
              <td>{totals.thirds || 0}</td>
              <td className="money">{money(totals.earnings)}</td>
            </tr>
          </tbody>
        </table>
        {s.major_wins ? <div className="notes" style={{ marginTop: 12 }}>{s.major_wins}</div> : null}
        {(data.stud_book || []).length ? (
          <div style={{ marginTop: 16 }}>
            <h4>STUD FEE & MARES BRED</h4>
            <div className="history-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Year</th>
                    <th>Stud Fee</th>
                    <th>Mares Bred</th>
                    <th>Live Foals</th>
                    <th>Live Foal %</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stud_book.map((row) => (
                    <tr key={row.year}>
                      <td>{row.year}</td>
                      <td className="money">{row.stud_fee || "—"}</td>
                      <td>{row.mares_bred ?? "—"}</td>
                      <td>{row.live_foals ?? "—"}</td>
                      <td>{row.live_foal_pct || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
        {s.career_highlight ? (
          <div className="notes" style={{ marginTop: 16 }}>{s.career_highlight}</div>
        ) : null}
        <div style={{ marginTop: 16 }}>
          <Link className="primary" href={data.has_profile ? `/hypomating?sire=${encodeURIComponent(data.name)}` : `/hypomating?mare=${encodeURIComponent(data.name)}`}>
            {data.has_profile ? "Select for hypomating" : "Use as broodmare"}
          </Link>
        </div>
      </div>

      <div>
        <div className="panel">
          <h4>PROGENY STATISTICS</h4>
          <div className="stats-grid">
            <div className="stat-box">
              <span>Crops / Foals</span>
              <strong>{racing.Crops || "—"} / {racing.Foals || "—"}</strong>
            </div>
            <div className="stat-box">
              <span>Winners %</span>
              <strong>{racing["Winners%"] || racing["Winners %"] || racing.Winners || "—"}</strong>
            </div>
            <div className="stat-box">
              <span>Blacktype %</span>
              <strong>{racing["Blacktype Winners%"] || racing["Black Type %"] || racing["BTW %"] || "—"}</strong>
            </div>
            <div className="stat-box">
              <span>Avg Earnings</span>
              <strong>{earn["Avg Earnings/starter"] || earn["Average Earnings Per Runner"] || earn["Avg Earnings"] || "—"}</strong>
            </div>
          </div>
        </div>
        <div className="panel" style={{ marginTop: 12 }}>
          <h4>SUCCESSFUL CROSSES</h4>
          {(data.top_progeny || []).length ? (
            <table>
              <thead>
                <tr><th>Horse</th><th>Broodmare Sire</th><th>Class</th></tr>
              </thead>
              <tbody>
                {(data.top_progeny || []).map((p) => (
                  <tr key={p.name}>
                    <td><Link href={horseHref(p.name)}>{p.name}</Link></td>
                    <td>{p.broodmare_sire}</td>
                    <td>{p.class}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="catalog-empty">No successful crosses recorded for this stallion yet.</p>
          )}
        </div>
      </div>

      <div className="tools">
        <button onClick={() => { toggleStar(data.name); saveFavorite(data.name); setTick((n) => n + 1); }} title="Star">
          {isStarred(data.name) && tick >= 0 ? "★" : "☆"}
        </button>
        <Link href="/stallions" title="Back">↔</Link>
      </div>
    </div>
  );
}
