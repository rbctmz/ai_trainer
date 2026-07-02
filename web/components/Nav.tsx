"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { isDemo, setDemo } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const links = [
  { href: "/dashboard", label: "Дашборд" },
  { href: "/coach", label: "Коуч" },
  { href: "/decisions", label: "Решения" },
  { href: "/planning", label: "План" },
  { href: "/hrv", label: "HRV" },
  { href: "/sleep", label: "Сон" },
  { href: "/activities", label: "Активности" },
];

export function Nav() {
  const pathname = usePathname();
  const [demo, setDemoState] = useState(false);
  useEffect(() => setDemoState(isDemo()), []);

  function toggleDemo() {
    setDemo(!demo);
    window.location.reload();
  }

  return (
    <div className="mb-6 space-y-2">
      <nav className="flex items-center gap-1 overflow-x-auto rounded-card border border-surface-border bg-surface p-1 shadow-card">
        <span className="px-3 text-sm font-bold text-ink">🏃 AI Trainer</span>
        <div className="ml-auto flex items-center gap-1">
          {links.map((l) => {
            const active = pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  active ? "bg-accent text-accent-foreground" : "text-ink-soft hover:bg-surface-muted"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={toggleDemo}
            title="Демо-режим: изолированные тестовые данные"
            className={`ml-1 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
              demo
                ? "border-tone-warning bg-tone-warning/10 text-tone-warning"
                : "border-surface-border text-ink-faint hover:bg-surface-muted"
            }`}
          >
            {demo ? "● Демо" : "Демо"}
          </button>
          <ThemeToggle />
        </div>
      </nav>
      {demo ? (
        <div className="rounded-lg bg-tone-warning/10 px-3 py-1.5 text-xs text-tone-warning">
          Демо-режим: показаны тестовые данные из изолированной базы. Реальные данные не затронуты.
        </div>
      ) : null}
    </div>
  );
}
