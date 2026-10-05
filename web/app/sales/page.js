"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, horseHref } from "../../lib/api";
import { saveAnalyzedSale } from "../../lib/barn";

function Stats({ stats }) {
  if (!stats) return null;
  const lt = stats.lifetime || {};
  const rc = stats.last_5_years;
  return (
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Lifetime</th>
          {rc ? <th>Last 5 yrs</th> : null}
        </tr>
      </thead>
      <tbody>
        {["horses", "gross", "avg", "median", "sold_pct", "rna", "mil"].map((k) => (
          <tr key={k}>
            <td>{k.replace("_", " ")}</td>
            <td>{lt[k]}</td>
            {rc ? <td>{rc[k]}</td> : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function SalesPage() {
  const [tab, setTab] = useState("catalogs");
  const [years, setYears] = useState([]);
  const [year, setYear] = useState("");
  const [catalogs, setCatalogs] = useState([]);
  const [catalogId, setCatalogId] = useState("");
  const [lots, setLots] = useState([]);
  const [stats, setStats] = useState(null);
  const [sex, setSex] = useState("");
  const [sort, setSort] = useState("hip");
  const [sire, setSire] = useState("");
  const [horse, setHorse] = useState({ name: "", year: "", sire: "", dam: "" });
  const [detail, setDetail] = useState(null);
  const [clientsOpen, setClientsOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet("/api/sales/years").then((d) => {
      setYears(d.years || []);
      if (d.years?.length) setYear(String(d.years[0]));
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!year) return;
    apiGet(`/api/sales/catalogs?year=${year}`).then((d) => setCatalogs(d.catalogs || []));
  }, [year]);

  async function loadCatalog(id) {
    setCatalogId(id);
    setDetail(null);
    const d = await apiGet(`/api/sales/lots?catalog_id=${id}&sort=${sort}&sex=${sex}`);
    setLots(d.lots || []);
    setStats(d.stats);
  }

  async function loadSire(ev) {
    ev.preventDefault();
    setDetail(null);
    const d = await apiGet(`/api/sales/sire/${encodeURIComponent(sire)}?sort=${sort}&sex=${sex}`);
    setLots(d.lots || []);
    setStats(d.stats);
  }

  async function loadHorse(ev) {
    ev.preventDefault();
    setDetail(null);
    const q = new URLSearchParams(horse).toString();
    const d = await apiGet(`/api/sales/horse?${q}`);
    setLots(d.lots || []);
    setStats(d.stats);
  }

  async function openLot(id) {
    const d = await apiGet(`/api/sales/lots/${id}`);
    setDetail(d);
    saveAnalyzedSale({ id, name: d.lot?.name, sale: d.lot?.sale });
  }

  const lot = detail?.lot;
  const st = detail?.sire_stats?.lifetime || stats?.lifetime;

  return (
    <div>
      <div className="search-row">
        {["catalogs", "stallion", "horse"].map((t) => (
          <button key={t} className={tab === t ? "primary" : "ghost"} onClick={() => setTab(t)}>
            {t === "catalogs" ? "Catalogs" : t === "stallion" ? "By stallion" : "By horse"}
          </button>
        ))}
        <select className="ghost" value={sex} onChange={(e) => setSex(e.target.value)}>
          <option value="">All sexes</option>
          <option value="C">Colts</option>
          <option value="F">Fillies</option>
          <option value="G">Geldings</option>
          <option value="M">Mares</option>
        </select>
        <select className="ghost" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="hip">Hip</option>
          <option value="price_desc">Price high</option>
          <option value="price_asc">Price low</option>
          <option value="year_desc">Year</option>
        </select>
      </div>
      {error ? <p className="error">{error}. Index sales with `python3 scripts/index_sales.py` if the hub is empty.</p> : null}

      <div className="sales-layout">
        <div className="panel">
          {tab === "catalogs" ? (
            <>
              <h4>YEAR</h4>
              <select value={year} onChange={(e) => setYear(e.target.value)}>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <h4 style={{ marginTop: 12 }}>SALES</h4>
              {catalogs.map((c) => (
                <button key={c.id} className="ghost" style={{ width: "100%", marginBottom: 6, textAlign: "left" }} onClick={() => loadCatalog(c.id)}>
                  {c.title}
                </button>
              ))}
            </>
          ) : null}
          {tab === "stallion" ? (
            <form onSubmit={loadSire}>
              <h4>STALLION PROGENY</h4>
              <input value={sire} onChange={(e) => setSire(e.target.value)} placeholder="Into Mischief" />
              <button className="primary" style={{ marginTop: 8 }}>Search</button>
            </form>
          ) : null}
          {tab === "horse" ? (
            <form onSubmit={loadHorse}>
              <h4>HORSE HISTORY</h4>
              <input placeholder="Name" value={horse.name} onChange={(e) => setHorse({ ...horse, name: e.target.value })} />
              <input placeholder="Foaling year" value={horse.year} onChange={(e) => setHorse({ ...horse, year: e.target.value })} />
              <input placeholder="Sire" value={horse.sire} onChange={(e) => setHorse({ ...horse, sire: e.target.value })} />
              <input placeholder="Dam" value={horse.dam} onChange={(e) => setHorse({ ...horse, dam: e.target.value })} />
              <button className="primary" style={{ marginTop: 8 }}>Search</button>
            </form>
          ) : null}
        </div>

        <div>
          {detail ? (
            <div className="lot-dash">
              <div className="lot-head">
                <div><div className="meta-label">Hip</div><b>{lot.hip}</b></div>
                <div>
                  <div className="meta-label">Consigned by</div>
                  <b>{lot.consignor || "—"}</b>
                  <div>{lot.name}</div>
                </div>
                <div><div className="meta-label">Color</div><b>{lot.color || "—"}</b></div>
                <div><div className="meta-label">Sex</div><b>{lot.sex_letter || lot.sex}</b></div>
                <div><div className="meta-label">Foaled</div><b>{lot.birth_year || "—"}</b></div>
                <div><div className="meta-label">Barn</div><b>{lot.barn || "—"}</b></div>
                <button className="ghost" onClick={() => setDetail(null)}>✕</button>
              </div>
              <div className="panel">
                <h4>EXPECTED MARKET</h4>
                <div className="market"><div className="bell" /></div>
                <p>Bust {st?.avg || "—"} · Median {st?.median || "—"} · Boom {st?.gross ? "see sire stats" : "—"}</p>
                <Stats stats={detail.sire_stats} />
              </div>
              <div className="panel">
                <h4>SIMILAR SUCCESSFUL STALLION CROSSES</h4>
                {(detail.similar_crosses || []).map((c) => (
                  <div key={c.broodmare_sire} className="suggest-card">
                    <div>
                      {lot.sire} × {c.broodmare_sire}
                      <div className="parents">{c.winners.map((w) => `${w.name} (${w.status})`).join(", ")}</div>
                    </div>
                  </div>
                ))}
                <h4>DAM FAMILY</h4>
                {lot.damsire ? <p>Damsire: {lot.damsire}</p> : null}
                {lot.dam ? <Link href={horseHref(lot.dam)}>See {lot.dam} pedigree</Link> : null}
              </div>
              <div className="panel">
                <h4>PHYSICAL / NOTES</h4>
                <p className="notes">
                  {lot.sire} × {lot.dam}
                  {lot.foaled_location ? `\nFoaled: ${lot.foaled_location}` : ""}
                  {`\nPrice: ${lot.price_raw}`}
                  {lot.purchaser ? `\nPurchaser: ${lot.purchaser}` : ""}
                </p>
                <button className="ghost" onClick={() => setClientsOpen((v) => !v)}>Clients</button>
                {clientsOpen ? (
                  <div className="clients">
                    <div className="client">Client 1 — saved locally in My Barn</div>
                    <div className="client">Client 2</div>
                    <div className="client">Client 3</div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="panel">
              <Stats stats={stats} />
              <table>
                <thead>
                  <tr>
                    <th>Hip</th><th>Horse</th><th>Sex</th><th>Color</th><th>Sire</th><th>Dam</th><th>Price</th><th>Sale</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((l) => (
                    <tr key={l.id} onClick={() => openLot(l.id)} style={{ cursor: "pointer" }}>
                      <td>{l.hip}</td>
                      <td>{l.name}</td>
                      <td>{l.sex_letter}</td>
                      <td>{l.color}</td>
                      <td>{l.sire}</td>
                      <td>{l.dam}</td>
                      <td className="money">{l.price_raw}</td>
                      <td>{l.sale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
