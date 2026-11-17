"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { swimError } from "@/lib/swim-api";
import type { SwimImportDraftResponse, SwimImportListResponse } from "@/lib/types";
import { SourceCapture } from "./SourceCapture";
import { DraftWorkspace } from "./DraftWorkspace";
import { ProgramLibrary, SavedProgram } from "./ProgramLibrary";
import { button, panel } from "./styles";

export function SwimWorkspace() {
  const router = useRouter();
  const params = useSearchParams();
  const selected = params.get("draft");
  const program = params.get("program");
  const { data: list, error: listError, mutate: refreshList } = useSWR<SwimImportListResponse>("/api/swim-imports", fetcher);
  // api-contract: exclude selected private UUID; populated HTTP/TS and browser readback cover this path.
  const { data: draft, error, mutate: refresh } = useSWR<SwimImportDraftResponse>(selected ? `/api/swim-imports/${encodeURIComponent(selected)}` : null, fetcher);
  return <main className="space-y-4">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><h1 className="text-2xl font-semibold text-ink">Программы плавания</h1><p className="mt-1 text-sm text-ink-soft">Исходник тренера, проверяемый черновик и сохранённая программа.</p></div>
      <Link href="/coach" className={button}>К диалогу с Коучем</Link>
    </header>
    {selected || program ? <>
      <div className="flex flex-wrap gap-2"><Link href="/coach/swim" className={button}>Все программы</Link></div>
      {program ? <SavedProgram key={`${program}/${params.get("revision")}`} programId={program} revision={params.get("revision")} /> : error ? <div role="alert" className={panel}>{swimError(error)} <button type="button" className={button} onClick={() => void refresh()}>Повторить чтение черновика</button></div> : !draft ? <p role="status" className="text-sm text-ink-soft">Загружаем исходник…</p> : <DraftWorkspace key={draft.import_id} draft={draft} reload={async () => {
        // api-contract: exclude: selected private UUID; populated HTTP and browser draft readback cover this path.
        const current = await fetcher<SwimImportDraftResponse>(`/api/swim-imports/${encodeURIComponent(draft.import_id)}`);
        await refresh(current, { revalidate: false }); void refreshList();
      }} onSaved={version => { router.push(`/coach/swim?program=${version.program_id}&revision=${version.revision}`); }} />}
    </> : <>
      <SourceCapture onCaptured={captured => { void refreshList(); router.replace(`/coach/swim?draft=${captured.import_id}`); }} />
      <section className={panel} aria-label="Черновики программ"><h2 className="text-lg font-semibold text-ink">Продолжить работу</h2>
        {listError ? <div role="alert" className="mt-2 text-sm text-tone-warning">{swimError(listError)} <button type="button" className={button} onClick={() => void refreshList()}>Повторить чтение</button></div> : !list ? <p role="status" className="mt-2 text-sm text-ink-soft">Загружаем список…</p> : list.items.length ? <ul className="mt-3 space-y-2">{list.items.map(item => <li key={item.import_id}><Link className="text-sm text-accent underline" href={`/coach/swim?draft=${item.import_id}`}>{item.document?.title || item.source_week_label || item.source_label || "Неразобранная программа"}</Link></li>)}</ul> : <p className="mt-2 text-sm text-ink-soft">Сохранённые исходники появятся здесь.</p>}
      </section>
      <ProgramLibrary />
    </>}
  </main>;
}
