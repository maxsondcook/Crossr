"use client";

import Link from "next/link";
import { horseHref } from "../lib/api";

function FoalLine({ p, hrefFor }) {
  const sexBit = p.sex ? `${p.sex}. ` : "";
  const name = p.status || p.is_subject ? (p.name || "").toUpperCase() : p.name;
  const link = (label) => (hrefFor ? hrefFor(label) : horseHref(label));
  return (
    <div className={`ff-foal${p.is_subject ? " subject" : ""}${p.status ? " stakes" : ""}`}>
      <Link href={link(p.name)}>{name}</Link>
      {p.year ? <span className="yr"> ({p.year})</span> : null}
      {p.sire ? <> ({sexBit}by <Link href={link(p.sire)}>{p.sire}</Link>)</> : null}
      {p.is_subject ? ". Black-type winner, above." : p.status ? `. ${p.status}.` : "."}
      {(p.races || []).length ? ` ${(p.races).join(", ")}.` : null}
      {(p.produce || []).map((g) => (
        <div className="ff-grand" key={`${g.name}-${g.sire}`}>
          Dam of <Link href={link(g.name)}>{g.status ? g.name.toUpperCase() : g.name}</Link>
          {g.sire ? <> ({g.sex ? `${g.sex}. ` : ""}by <Link href={link(g.sire)}>{g.sire}</Link>)</> : null}
          {g.status ? `. ${g.status}.` : "."}
          {(g.races || []).length ? ` ${g.races.join(", ")}.` : null}
        </div>
      ))}
    </div>
  );
}

export default function FemaleFamily({ family, hrefFor = null }) {
  if (!family || family.length === 0) {
    return <p className="empty">No dam line on file for this horse yet.</p>;
  }
  const link = (label) => (hrefFor ? hrefFor(label) : horseHref(label));
  return family.map((d) => (
    <div className="ff-block" key={d.ordinal}>
      <div className="ff-ord">{d.ordinal}</div>
      <div className="ff-head">
        <Link href={link(d.name)}>{(d.name || "").toUpperCase()}</Link>
        {d.year ? ` (${d.year})` : ""}
        {d.sire ? <>, by <Link href={link(d.sire)}>{d.sire}</Link>.</> : "."}
        {d.status ? ` ${d.status}.` : ""}
      </div>
      <div className="ff-racing">
        {(d.racing || []).length ? d.racing.join("; ") : "Racing record not on file."}
      </div>
      <div className="ff-prod-label">Produce</div>
      {(d.produce || []).length === 0 ? (
        <p className="empty">No produce on file yet.</p>
      ) : (
        d.produce.map((p) => <FoalLine key={`${p.name}-${p.sire}`} p={p} hrefFor={hrefFor} />)
      )}
    </div>
  ));
}
