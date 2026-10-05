"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import Nav from "./Nav";
import { refreshAuth } from "../lib/auth";

export default function AppFrame({ children }) {
  const path = usePathname();

  useEffect(() => {
    refreshAuth();
  }, []);

  if (path === "/" || path === "/signin") {
    return children;
  }

  return (
    <div className="shell">
      <Nav />
      {children}
    </div>
  );
}
