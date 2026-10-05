"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiGet } from "../../lib/api";
import PedigreeChart from "../../components/PedigreeChart";

function CompareInner() {
  const params = useSearchParams();
  const a = params.get("a") || "";
  const b = params.get("b") || "";
  const [left, setLeft] = useState(null);
  const [right, setRight] = useState(null);

  useEffect(() => {
    if (a) apiGet(`/api/horses/${encodeURIComponent(a)}`).then(setLeft);
    if (b) apiGet(`/api/horses/${encodeURIComponent(b)}`).then(setRight);
  }, [a, b]);

  function col(d) {
    if (!d) return <p className="empty">Loading…</p>;
    const s = d.stallion || {};
    return (
      <div className="panel">
        <h2>{d.name}</h2>
        <p>{s.farm} · {s.stud_fee} · Rank {s.rank || "NA"}</p>
        <p>Foaled {s.year_foaled} · Stud {s.entered_stud}</p>
        <PedigreeChart tree={d.pedigree} />
      </div>
    );
  }

  return (
    <div className="dash" style={{ gridTemplateColumns: "1fr 1fr" }}>
      {col(left)}
      {col(right)}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<p className="empty">Loading comparison…</p>}>
      <CompareInner />
    </Suspense>
  );
}
