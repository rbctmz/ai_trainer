"use client";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button
      type="button"
      onClick={toggle}
      title={dark ? "Светлая тема" : "Тёмная тема"}
      className="rounded-lg border border-surface-border px-2.5 py-1.5 text-sm text-ink-faint transition hover:bg-surface-muted"
    >
      {dark ? "☀️" : "🌙"}
    </button>
  );
}
