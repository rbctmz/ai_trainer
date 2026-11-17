import { input, panel } from "./styles";

export function SourceView({ text }: { text: string }) {
  return <section className={panel} aria-label="Исходник тренера">
    <label htmlFor="swim-source-original" className="block font-semibold text-ink">Исходный текст</label>
    <p className="mt-1 text-sm text-ink-soft">Сравните структуру со всеми заданиями тренера.</p>
    <textarea id="swim-source-original" className={`${input} mt-3 min-h-52 lg:min-h-96`} readOnly value={text} />
  </section>;
}
