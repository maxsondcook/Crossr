"use client";

import { useEffect, useRef, useState } from "react";

const STYLES = {
  pen: { stroke: "#ef6b73", width: 2.5, opacity: 1 },
  highlighter: { stroke: "#f5d76e", width: 16, opacity: 0.35 },
};
const ERASE_RADIUS = 14;

function load(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key) || "[]");
  } catch {
    return [];
  }
}

function save(key, strokes) {
  try {
    if (strokes.length) window.localStorage.setItem(key, JSON.stringify(strokes));
    else window.localStorage.removeItem(key);
  } catch {
    /* storage full or blocked: drawings just won't persist */
  }
}

function pathOf(points) {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
}

/**
 * Freehand pen / highlighter / eraser layer over a scrolling column.
 * Lives inside the column (position: relative) and spans its full scroll height,
 * so marks move with the content. Strokes persist in localStorage under storageKey.
 * tool: null (off) | "pen" | "highlighter" | "eraser". clearSignal bumps to wipe this layer.
 */
export default function MarkupLayer({ storageKey, tool, clearSignal }) {
  const svgRef = useRef(null);
  const [strokes, setStrokes] = useState([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const drawing = useRef(null);

  useEffect(() => { setStrokes(storageKey ? load(storageKey) : []); }, [storageKey]);

  useEffect(() => {
    if (!clearSignal) return;
    setStrokes([]);
    if (storageKey) save(storageKey, []);
  }, [clearSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  // Match the column's full scrollable size.
  useEffect(() => {
    const host = svgRef.current?.parentElement;
    if (!host) return undefined;
    const measure = () => setSize({ w: host.scrollWidth, h: host.scrollHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(host);
    for (const child of host.children) if (child !== svgRef.current) ro.observe(child);
    return () => ro.disconnect();
  }, [storageKey]);

  function point(e) {
    const box = svgRef.current.getBoundingClientRect();
    return [e.clientX - box.left, e.clientY - box.top];
  }

  function eraseAt([x, y]) {
    setStrokes((cur) => {
      const next = cur.filter((s) => !s.points.some(([px, py]) => Math.hypot(px - x, py - y) < ERASE_RADIUS));
      if (next.length !== cur.length && storageKey) save(storageKey, next);
      return next;
    });
  }

  function onDown(e) {
    if (!tool) return;
    e.preventDefault();
    svgRef.current.setPointerCapture(e.pointerId);
    const p = point(e);
    if (tool === "eraser") {
      drawing.current = { eraser: true };
      eraseAt(p);
      return;
    }
    drawing.current = { tool, points: [p] };
    setStrokes((cur) => [...cur, drawing.current]);
  }

  function onMove(e) {
    const d = drawing.current;
    if (!d) return;
    const p = point(e);
    if (d.eraser) {
      eraseAt(p);
      return;
    }
    d.points.push(p);
    setStrokes((cur) => [...cur.slice(0, -1), { ...d }]);
  }

  function onUp() {
    const d = drawing.current;
    drawing.current = null;
    if (d && !d.eraser && storageKey) {
      setStrokes((cur) => {
        save(storageKey, cur);
        return cur;
      });
    }
  }

  return (
    <svg
      ref={svgRef}
      className={`markup-layer${tool ? ` active tool-${tool}` : ""}`}
      width={size.w}
      height={size.h}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
    >
      {strokes.map((s, i) => {
        const st = STYLES[s.tool] || STYLES.pen;
        return (
          <path
            key={i}
            d={pathOf(s.points)}
            fill="none"
            stroke={st.stroke}
            strokeWidth={st.width}
            strokeOpacity={st.opacity}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        );
      })}
    </svg>
  );
}
