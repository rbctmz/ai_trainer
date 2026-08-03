"use client";

import Link from "next/link";

/** Contextual detail-page header with an explicit return to «Обзор» (M1 #265). */
export function DrillDownHeader({ title }: { title: string }) {
  return (
    <div>
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1 text-sm font-medium text-ink-soft transition hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span aria-hidden="true">←</span> Обзор
      </Link>
      <h1 className="mt-1 text-2xl font-bold text-ink">{title}</h1>
    </div>
  );
}
