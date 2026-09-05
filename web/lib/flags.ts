// Build-time UI feature flags for the web surface.
//
// `showDevTools` gates research/shadow surfaces that are useful for development
// and evidence-gathering but should NOT be shown to beta testers, because they
// read as raw engineering (empty "shadow" pages, an agent audit log, component
// fixtures) rather than product. It hides: the /recovery, /decisions, and
// /showcase pages plus the inline "Прогноз качества сессии · shadow" module on
// /today (issues #254 and #548).
//
// NEXT_PUBLIC_* is inlined into the client bundle at build time by Next.js, so
// this is a static per-build constant (no runtime toggle). Default: OFF.
// Turn on for development with:  NEXT_PUBLIC_SHOW_DEV_TOOLS=true npm run dev
export const showDevTools = process.env.NEXT_PUBLIC_SHOW_DEV_TOOLS === "true";
