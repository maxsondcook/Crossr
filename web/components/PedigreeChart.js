"use client";

import { useMemo } from "react";
import Link from "next/link";
import { horseHref } from "../lib/api";

const ANCESTOR_GENS = 5;
const LEAF_ROWS = 2 ** ANCESTOR_GENS;

function flatten(node, idx, depth, map) {
  if (!node || depth > ANCESTOR_GENS) return;
  map[idx] = node;
  flatten(node.sire, idx * 2 + 1, depth + 1, map);
  flatten(node.dam, idx * 2 + 2, depth + 1, map);
}

function Cell({ n, className, style }) {
  return (
    <div className={`cat-cell ${className || ""}`} style={style}>
      {n?.name ? (
        <>
          <Link href={horseHref(n.name)}>{n.name}</Link>
          {n.year ? <span className="yr">{n.year}</span> : null}
          <span className="leaders" aria-hidden="true" />
        </>
      ) : (
        <span className="leaders empty-lead" aria-hidden="true" />
      )}
    </div>
  );
}

export default function PedigreeChart({ tree, showSubject = true }) {
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
          className={`cat-g${gen} ${side}`}
          style={{
            gridColumn: col,
            gridRow: span === 1 ? i + 1 : `${i * span + 1} / span ${span}`,
          }}
        />
      );
    }
  }

  return (
    <div className={`catalog-ped gen-5${showSubject ? "" : " no-subject"}`}>
      {showSubject ? (
        <div className="cat-subject">
          <Link href={horseHref(tree.name)}>{tree.name}</Link>
          {tree.year ? <span className="yr">{tree.year}</span> : null}
        </div>
      ) : null}
      {cells}
    </div>
  );
}
