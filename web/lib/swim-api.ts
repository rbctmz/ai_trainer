import { ApiError, postJSON, withDemo } from "./api";
import type { SwimCoachEvent, SwimCoachTurnRequest } from "./types";

export function swimError(error: unknown): string {
  const nested = error instanceof ApiError ? error.data?.detail : undefined;
  const code = nested && typeof nested === "object" && "code" in nested ? String(nested.code) : error instanceof ApiError ? error.code : undefined;
  const messages: Record<string, string> = {
    swim_import_stale: "Черновик изменился. Обновите его и проверьте изменения.",
    swim_program_stale: "В библиотеке появилась новая версия. Подготовьте новый предпросмотр.",
    swim_program_preview_expired: "Срок предпросмотра истёк. Подготовьте его заново.",
    swim_import_not_ready: "Есть неразобранные фрагменты или несовместимый вариант упражнения. Проверьте вопросы и исходник.",
    swim_coach_provider_unavailable: "Коуч сейчас недоступен. Исходник сохранён; структуру можно создать вручную.",
    swim_coach_native_required: "Этот провайдер не поддерживает разбор программы. Можно выбрать другой в настройках или создать структуру вручную.",
    swim_coach_unverified_claim: "Коуч сообщил неподтверждённый результат. Проверьте актуальный черновик.",
    swim_coach_no_change: "Разбор или правка не выполнены. Проверьте исходник или уточните запрос.",
    swim_import_invalid_document: "Проверьте поля структуры и привязки к исходнику.",
    swim_import_invalid_request: "Проверьте введённые значения.",
    swim_coach_invalid_request: "Проверьте текст запроса.",
    swim_exercise_invalid_request: "Проверьте название, вариант, инструкцию, среду и границы видео-фрагментов.",
    swim_exercise_stale: "В справочнике появилась новая версия. Откройте её перед следующей правкой.",
    swim_coach_history_unavailable: "История диалога недоступна. Обновите черновик и проверьте результат перед продолжением.",
    swim_coach_chat_not_found: "Диалог не найден. Очистите буфер диалога и повторите запрос; исходник и черновик сохранены отдельно.",
  };
  if (code && messages[code]) return messages[code];
  if (error instanceof ApiError && error.status === 404) return "Программа не найдена. Выберите её из списка или сохраните новый исходник.";
  if (error instanceof ApiError && error.status === 503) return "Хранилище временно недоступно. Повторите чтение; введённый текст остаётся у вас.";
  return "Не удалось получить подтверждение сервера. Повторите действие или обновите данные.";
}

export async function swimPost<T>(path: string, body: unknown): Promise<T> {
  return postJSON<T>(path, body);
}

export async function streamSwimCoach(payload: SwimCoachTurnRequest, onEvent: (event: SwimCoachEvent) => void, signal?: AbortSignal): Promise<void> {
  const response = await fetch(withDemo("/api/coach/swim-import"), {
    method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body: JSON.stringify(payload), signal,
  });
  if (!response.ok || !response.body) {
    let data: Record<string, unknown> | undefined;
    try { data = await response.json(); } catch { /* Keep a safe generic error. */ }
    throw new ApiError(response.status, "swim turn failed", undefined, undefined, data);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  try {
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const line = frame.split(/\r?\n/).find(value => value.startsWith("data:"));
        if (!line) continue;
        const event = JSON.parse(line.slice(5).trim()) as SwimCoachEvent;
        if (event.type === "done") completed = true;
        onEvent(event);
      }
      if (chunk.done) break;
    }
    if (!completed) throw new Error("incomplete swim response");
  } finally { reader.releaseLock(); }
}
