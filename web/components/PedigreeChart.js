"use client";

import { useMemo } from "react";
import Link from "next/link";
import { horseHref } from "../lib/api";

const ANCESTOR_GENS = 5;
const LEAF_ROWS = 2 ** ANCESTOR_GENS;
/** Character slots per generation column (name ~18ch inside border “pipes”). */
const CELL_CHARS = 20;

function flatten(node, idx, depth, map) {
  if (!node || depth > ANCESTOR_GENS) return;
  map[idx] = node;
  flatten(node.sire, idx * 2 + 1, depth + 1, map);
  flatten(node.dam, idx * 2 + 2, depth + 1, map);
}

function Cell({ n, className, style, hrefFor }) {
  const href = n?.name ? (hrefFor ? hrefFor(n.name) : horseHref(n.name)) : "";
  const year = n?.year != null && n.year !== "" ? String(n.year) : "";
  return (
    <div className={`cat-cell ${className || ""}`} style={style}>
      {n?.name ? (
        <div className="cat-cell-inner">
          <Link className="cat-name" href={href} title={year ? `${n.name} (${year})` : n.name}>
            {n.name}
          </Link>
          {year ? <span className="yr">{year}</span> : null}
        </div>
      ) : (
        <div className="cat-cell-inner empty" aria-hidden="true" />
      )}
    </div>
  );
}

export default function PedigreeChart({ tree, showSubject = true, hrefFor = null }) {
  const map = useMemo(() => {
    const m = {};
    flatten(tree, 0, 0, m);
    return m;
  }, [tree]);

  if (!tree) return <div className="empty">No pedigree loaded.</div>;

  const cells = [];
  for (let gen = 1; gen <= ANCESTOR_GENS; gen += 1) {
    const count = 2 ** gen;
    const start = count - 1;
    const span = LEAF_ROWS / count;
    const col = (showSubject ? 1 : 0) + gen;
    for (let i = 0; i < count; i += 1) {
      const idx = start + i;
      const side = i < count / 2 ? "sire" : "dam";
      cells.push(
        <Cell
          key={idx}
          n={map[idx]}
          hrefFor={hrefFor}
          className={`cat-g${gen} ${side}`}
          style={{
            gridColumn: col,
            gridRow: span === 1 ? i + 1 : `${i * span + 1} / span ${span}`,
          }}
        />,
      );
    }
  }

  const subjectHref = tree.name ? (hrefFor ? hrefFor(tree.name) : horseHref(tree.name)) : "";
  const subjectYear = tree.year != null && tree.year !== "" ? String(tree.year) : "";
  const cols = showSubject ? ANCESTOR_GENS + 1 : ANCESTOR_GENS;

  return (
    <div
      className="pedigree-fit"
      style={{
        "--ped-cols": String(cols),
        "--ped-chars": String(CELL_CHARS),
      }}
    >
      <div className={`catalog-ped gen-5${showSubject ? "" : " no-subject"}`}>
        {showSubject ? (
          <div className="cat-subject">
            <Link
              className="cat-name"
              href={subjectHref}
              title={subjectYear ? `${tree.name} (${subjectYear})` : tree.name}
            >
              {tree.name}
            </Link>
            {subjectYear ? <span className="yr">{subjectYear}</span> : null}
          </div>
        ) : null}
        {cells}
      </div>
    </div>
  );
}
