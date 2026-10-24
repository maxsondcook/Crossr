"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { horseHref } from "../lib/api";
import { horseCaps, matingCaps } from "../lib/display";
import PedigreeChart from "./PedigreeChart";
import FemaleFamily from "./FemaleFamily";

function money(n) {
  if (n == null || n === "") return "—";
  const num = Number(n);
  if (!num) return "—";
  return `$${num.toLocaleString()}`;
}

function priceLabel(row) {
  if (!row) return "—";
  const raw = row.price_raw == null ? "" : String(row.price_raw).trim();
  if (row.is_rna) {
    if (!raw || raw.toUpperCase() === "RNA") return "RNA";
    return raw.toUpperCase().startsWith("RNA") ? raw.toUpperCase() : `RNA ${raw}`;
  }
  if (raw && row.price_num) return raw.toUpperCase();
  if (row.price_num) return money(row.price_num);
  return "—";
}

function saleHeading(title, year) {
  const name = title == null ? "" : String(title).trim();
  const y = year == null || year === "" ? "" : String(year).trim();
  if (!name) return horseCaps(y);
  if (!y) return horseCaps(name);
  if (name.includes(y)) return horseCaps(name);
  return horseCaps(`${name} ${y}`);
}

/**
 * Shared hypofoal detail surface (Create hypofoal + Barn).
 * Panels: Pedigree, Female Family, Similar Successful Crosses,
 * Similar Auction Results, Current-day stallions similarity.
 */
export default function HypofoalDetail({ report, onBack = null, loading = false, error = "" }) {
  const [openAuction, setOpenAuction] = useState("");
  if (loading) {
    return <p className="empty">Loading hypofoal…</p>;
  }
  if (error) {
    return <p className="error">{error}</p>;
  }
  if (!report) {
    return <p className="empty">No hypofoal selected.</p>;
  }

  const title = matingCaps(report.sire, report.dam, report.foal_name);
  const crosses = report.similar_crosses || [];
  const auctions = report.auction_history || [];
  const stallions = report.similar_stallions || [];

  return (
    <div className="hypofoal-detail">
      {onBack ? (
        <button className="ghost" type="button" onClick={onBack}>
          ← BACK
        </button>
      ) : null}
      <h2 className="hypofoal-title">{title}</h2>
      <p className="sub">
        {horseCaps(report.sire)} × {horseCaps(report.dam)}
        {report.inbreeding?.coefficient_pct != null
          ? ` · INBREEDING ${report.inbreeding.coefficient_pct}%`
          : ""}
      </p>

      <div className="dash hypofoal-panels" style={{ marginTop: 12, gridTemplateColumns: "minmax(640px, 1.4fr) minmax(360px, 1fr)" }}>
        <div>
          <div className="panel">
            <h4>PEDIGREE</h4>
            {report.pedigree ? (
              <PedigreeChart tree={report.pedigree} />
            ) : (
              <p className="empty">No pedigree on file for this mating.</p>
            )}
          </div>
          <div className="panel family-panel" style={{ marginTop: 12 }}>
            <h4>FEMALE FAMILY</h4>
            <FemaleFamily family={report.female_family || []} />
          </div>
        </div>

        <div>
          <div className="panel">
            <h4>SIMILAR SUCCESSFUL CROSSES</h4>
            {!crosses.length ? (
              <p className="empty">No similar successful crosses on file yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>HORSE</th>
                    <th>CLASS</th>
                    <th>SIMILARITY</th>
                  </tr>
                </thead>
                <tbody>
                  {crosses.map((row, index) => (
                    <tr key={`${row.name}-${row.class}-${index}`}>
                      <td>
                        <Link href={horseHref(row.name)}>{horseCaps(row.name)}</Link>
                      </td>
                      <td>{horseCaps(row.class) || "—"}</td>
                      <td>{row.similarity != null ? `${row.similarity}%` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="panel" style={{ marginTop: 12 }}>
            <h4>SIMILAR AUCTION RESULTS</h4>
            {!auctions.length ? (
              <p className="empty">No auction history on file for these crosses yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>HORSE</th>
                    <th>SIMILARITY</th>
                    <th>SALE</th>
                    <th>PRICE</th>
                  </tr>
                </thead>
                <tbody>
                  {auctions.map((row, index) => {
                    const key = `${row.name}-${row.sale}-${row.hip}-${index}`;
                    const open = openAuction === key;
                    return (
                      <Fragment key={key}>
                        <tr
                          className="auction-row"
                          role="button"
                          tabIndex={0}
                          onClick={() => setOpenAuction(open ? "" : key)}
                        >
                          <td>
                            <Link href={horseHref(row.name)} onClick={(e) => e.stopPropagation()}>
                              {horseCaps(row.name)}
                            </Link>
                          </td>
                          <td>{row.similarity != null ? `${row.similarity}%` : "—"}</td>
                          <td>{saleHeading(row.sale, row.year)}</td>
                          <td className="money">{priceLabel(row)}</td>
                        </tr>
                        {open ? (
                          <tr className="auction-more">
                            <td colSpan={4}>
                              HIP {row.hip || "—"}
                              {row.is_rna ? " · RNA" : ""}
                              {row.purchaser ? ` · PURCHASER ${horseCaps(row.purchaser)}` : ""}
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <div className="panel" style={{ marginTop: 12 }}>
            <h4>CURRENT-DAY STALLIONS SIMILARITY</h4>
            {!stallions.length ? (
              <p className="empty">No similar active stallions on file yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>STALLION</th>
                    <th>SIMILARITY</th>
                    <th>RANK</th>
                    <th>STUD FEE</th>
                  </tr>
                </thead>
                <tbody>
                  {stallions.map((row) => (
                    <tr key={row.name}>
                      <td>
                        <Link href={horseHref(row.name)}>{horseCaps(row.name)}</Link>
                      </td>
                      <td>{row.similarity != null ? `${row.similarity}%` : "—"}</td>
                      <td>{row.rank && String(row.rank).toUpperCase() !== "N/A" ? `#${row.rank}` : "—"}</td>
                      <td className="money">{horseCaps(row.stud_fee) || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
