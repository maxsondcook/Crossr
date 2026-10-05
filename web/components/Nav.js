"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { apiGet, horseHref } from "../lib/api";
import { loadUser, signOutAccount } from "../lib/auth";

const LINKS = [
  { href: "/stallions", label: "STALLIONS" },
  { href: "/hypomating", label: "HYPOMATING" },
  { href: "/sales", label: "SALES" },
  { href: "/barn", label: "MY BARN" },
];

export default function Nav() {
  const path = usePathname();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const sync = () => setUser(loadUser());
    sync();
    window.addEventListener("crossr-auth", sync);
    return () => window.removeEventListener("crossr-auth", sync);
  }, []);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      apiGet(`/api/search?q=${encodeURIComponent(q)}`)
        .then((d) => setHits(d.results || []))
        .catch(() => setHits([]));
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <header className="topbar">
      <div className="brand-wrap">
        <Link href="/" className="home-btn" aria-label="Home">
          <img src="/logo.png" alt="Crossr home" />
        </Link>
        <Link href="/" className="brand-name">CROSSR</Link>
      </div>
      <nav className="nav">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={path.startsWith(l.href) ? "active" : ""}>
            {l.label}
          </Link>
        ))}
      </nav>
      <div className="nav-search">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && q.trim()) {
              router.push(horseHref(q.trim()));
              setHits([]);
            }
          }}
          placeholder="Search any horse…"
        />
        {hits.length ? (
          <div className="nav-hits">
            {hits.map((h) => (
              <Link
                key={h.key}
                href={horseHref(h.name)}
                onClick={() => {
                  setQ("");
                  setHits([]);
                }}
              >
                {h.name} {h.year ? <span>({h.year})</span> : null}
              </Link>
            ))}
          </div>
        ) : null}
      </div>
      {user ? (
        <div className="nav-account">
          <Link href="/barn">{user.username}</Link>
          <button className="ghost" onClick={() => signOutAccount()}>Sign out</button>
        </div>
      ) : (
        <Link className="ghost" href="/signin">Sign in</Link>
      )}
    </header>
  );
}
