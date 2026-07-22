"use client";

import { AdherenceRibbon } from "@/components/AdherenceRibbon";

// Deep-link route only — «План vs факт» left the top nav in #253 and now lives as
// a tab inside «План» (#255). The ribbon itself is the shared AdherenceRibbon
// component so the route and the tab never diverge.
export default function AdherencePage() {
  return (
    <main className="space-y-5">
      <AdherenceRibbon />
    </main>
  );
}
