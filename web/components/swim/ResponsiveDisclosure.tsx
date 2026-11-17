"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { button } from "./styles";

/** Keep comparison visible on desktop and explicitly expandable on a phone. */
export function ResponsiveDisclosure({ title, children, initiallyOpen = false }: { title: string; children: ReactNode; initiallyOpen?: boolean }) {
  const [wide, setWide] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(initiallyOpen);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const changed = () => setWide(media.matches);
    changed(); media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  return <details className="min-w-0" open={wide || mobileOpen} onToggle={event => { if (!wide) setMobileOpen(event.currentTarget.open); }}>
    <summary className={`${button} cursor-pointer lg:hidden`}>{title}</summary>
    <div className="mt-3 min-w-0 space-y-4 lg:mt-0">{children}</div>
  </details>;
}
