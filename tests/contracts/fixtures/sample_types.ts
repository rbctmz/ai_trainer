/**
 * Образец всех синтаксических конструкций web/lib/types.ts, поддерживаемых
 * экстрактором контракта (web/scripts/extract-contract.mjs).
 * Используется юнит-тестами tests/smoke/test_contract_extractor.py.
 * Orphan намеренно не достижим от Root — экстрактор обязан его не извлекать.
 */

export type Tone = "danger" | "warning" | string;

export interface Factor {
  key: string;
  score: number | null;
}

export interface Snapshot {
  tone: Tone;
  factor: Factor | null;
  factors: Factor[];
  optional_note?: string;
  meta: Record<string, unknown>;
  raw: unknown;
  lit: true;
  nums: 1 | 2;
}

export interface Profile {
  mode: "a" | "b";
  base: { x: number };
}

export interface Suggestion<T> {
  value: T;
  basis: "derived" | "fallback";
}

export interface Pickable {
  a: string;
  b: number;
  c: boolean;
}

export interface Extended extends Factor {
  label: string;
}

export interface Root {
  snapshot: Snapshot;
  mode: Profile["mode"];
  pick: Pick<Pickable, "a" | "b">;
  merged: { extra: string } & Pickable;
  suggestion: Suggestion<Profile["mode"]>;
  extended: Extended;
  list: Array<{ inner: string }>;
}

export interface Orphan {
  x: string;
}
