"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/dashboard", label: "Дашборд" },
  { href: "/coach", label: "Коуч" },
  { href: "/planning", label: "План" },
  { href: "/hrv", label: "HRV" },
  { href: "/activities", label: "Активности" },
];

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="mb-6 flex items-center gap-1 overflow-x-auto rounded-card border border-surface-border bg-surface p-1 shadow-card">
      <span className="px-3 text-sm font-bold text-ink">🏃 AI Trainer</span>
      <div className="ml-auto flex gap-1">
        {links.map((l) => {
          const active = pathname === l.href || pathname.startsWith(l.href + "/");
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                active
                  ? "bg-ink text-white"
                  : "text-ink-soft hover:bg-surface-muted"
              }`}
            >
              {l.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
