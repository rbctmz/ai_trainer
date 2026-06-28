# Coach Approval-Gated Mutations: Propose → Confirm → Execute

This ExecPlan is a living document. Sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Right now the AI coach can only read data — it cannot touch the training plan even when the user explicitly asks it to. If the user says "помоги собрать план на Half Ironman к октябрю", the coach makes up prose and nothing is saved. After this change, the coach generates a real plan preview from the planning engine, the web UI shows a confirmation card ("Подтвердить / Отменить"), and clicking "Подтвердить" actually saves the plan — the same plan the Planning page would build. Similarly, when the user says "скорректируй план на эту неделю", the coach previews what the adjustment looks like and the user can confirm.

**How to see it working:** start `./run_web.sh`, open `http://localhost:3000/coach`, type "помоги собрать план для Half Ironman на 2026-10-01, у меня 10 часов в неделю". The coach should call a tool, and a blue confirmation card should appear with plan summary and two buttons. Clicking "Подтвердить" should POST to `/api/planning/build`, after which navigating to `/planning` shows the newly saved plan.


## Progress

- [x] Milestone 1: Add `propose_plan_build` and `propose_plan_adjustment` tools to `models/ai_tools.py`
- [x] Milestone 2: Update system prompt in `models/ai_coach_runtime.py` to mandate proposal tools
- [x] Milestone 3: Emit `proposal` SSE event in `api/routers/coach.py` when tool result has `is_proposal: True`
- [x] Milestone 4: Add `ProposalCard` component and handle `proposal` event in `web/app/coach/page.tsx`
- [ ] Milestone 5: Smoke tests in `tests/smoke/test_ai_tools_proposal.py`; verify `python -m pytest tests/smoke -q` stays at 232 pass (running)


## Surprises & Discoveries

- `AITools.execute_tool()` historically assumed every successful tool returns an arbitrary payload and wraps it into `{"success": True, "result": ...}`. Proposal tools need graceful domain errors (`missing event_date`, `no active plan`) without throwing, so `execute_tool()` now preserves explicit `{"success": False, "error": ...}` results instead of re-wrapping them as success.
- The original ExecPlan suggested a smoke test against `Settings.DATABASE_PATH`. That is brittle for contributor-safe CI because it depends on a populated local cache. The implementation switched to temp SQLite fixtures seeded with synthetic activities, then exercised the real planning engine on top of that fixture.
- The web contract already had `tool_call` chips and streaming final tokens; adding a separate `proposal` SSE event let the UI show a persistent confirm/cancel card without parsing assistant markdown or inventing frontend heuristics.


## Decision Log

- Decision: Import `api/planning_service` from `models/ai_tools.py` (cross-layer dependency).
  Rationale: `api/planning_service` only imports from `models/`, `data/`, and `config/` — no circular dependency results. Duplicating the orchestration logic (banister metrics, constraint solving, daily expansion) inside `models/ai_tools.py` would be far worse. If this becomes a problem later, move the orchestration to `models/planning_orchestrator.py` and have both `api/planning_service` and `models/ai_tools.py` call it.
  Date/Author: 2026-06-28 / Claude Code

- Decision: `propose_plan_build` calls `planning_service.build_plan(persist=False)` (same as the Planning page, with persisting disabled).
  Rationale: Reusing the production path guarantees the coach proposes exactly what Planning would save, no divergence. The `persist=False` flag is already supported by both `build_plan` and `apply_adjustment`.
  Date/Author: 2026-06-28 / Claude Code

- Decision: `propose_plan_adjustment` auto-discovers reconciliation rows from the DB, does not ask the coach to supply them.
  Rationale: The coach has no way to know which sessions were completed vs missed. `planning_service.reconciliation(db)` already computes this from `db.get_activities(30)`. The tool simply calls reconciliation then previews the adjustment with `persist=False`.
  Date/Author: 2026-06-28 / Claude Code

- Decision: Proposal data is surfaced to the frontend via a new `{"type": "proposal", ...}` SSE event, not via inline text.
  Rationale: The coach text response should explain the proposal in natural language while the UI renders the structured preview and confirm/cancel buttons. Mixing structured data into the markdown text would be fragile.
  Date/Author: 2026-06-28 / Claude Code

- Decision: Proposal smoke coverage uses temp seeded SQLite databases instead of the real `Settings.DATABASE_PATH`.
  Rationale: This keeps `tests/smoke` contributor-safe and CI-stable while still exercising the real planning path (`build_plan`, `reconciliation`, `apply_adjustment`) end to end. The test now validates planner behavior, not local machine state.
  Date/Author: 2026-06-28 / Codex


## Outcomes & Retrospective

(fill at completion)


## Context and Orientation

**Repository layout you need to know:**

    ai_trainer/
    ├── models/ai_tools.py          ← all coach read/write tools (class AITools)
    ├── models/ai_coach_runtime.py  ← system prompts + two-pass streaming pipeline
    ├── api/planning_service.py     ← headless planning engine (build_plan, apply_adjustment, reconciliation)
    ├── api/routers/coach.py        ← FastAPI SSE streaming endpoint /api/coach/chat
    ├── api/routers/planning.py     ← existing /api/planning/build and /api/planning/adjust
    ├── web/app/coach/page.tsx      ← Next.js coach chat page (handles SSE events)
    └── tests/smoke/                ← smoke test suite (run with: python -m pytest tests/smoke -q)

**How the coach pipeline works today (two-pass streaming):**

1. POST `/api/coach/chat` — request arrives at `api/routers/coach.py`.
2. First pass: `generate_ai_chat_response(provider, ai_tools, user_input, history)` — LLM produces hidden text containing `[TOOL: tool_name, param=value, ...]` markers.
3. Tool execution: `collect_tool_results(raw, ai_tools, format_tool_result)` — scans for `[TOOL: ...]` markers, calls `ai_tools.execute_tool(name, **params)` for each, returns formatted results.
4. SSE: for each tool that ran, `{"type": "tool_call", "name": label, ...}` is emitted.
5. Second pass (synthesis): LLM synthesizes a final human-readable answer from the tool results. Tokens stream as `{"type": "token", "content": delta}`.
6. `{"type": "done", ...}` closes the stream.

**Tool marker syntax** (the LLM writes these in its first-pass output):

    [TOOL: tool_name, param1=value, param2=value]

For simple values: `days=7`, `goal_type=Триатлон`. For strings with spaces: `event_date=2026-10-01`. No quotes needed; the parser splits on `, ` and `=`.

**`AITools` class in `models/ai_tools.py`:**

- `__init__(self, database: Database)` — receives a `Database` instance; stores as `self.db`.
- `self.tools` dict — maps tool name (string) to bound method.
- `get_available_tools()` — returns a dict of `{name: description}` for the system prompt.
- `format_tool_descriptions_for_ai()` — formats tool descriptions + example markers for the first-pass prompt.
- `execute_tool(name, **kwargs)` — dispatches to the named method, catches exceptions.

Every tool method returns `{"success": True, "result": {...}}` on success or `{"success": False, "error": "..."}` on failure. Nothing else.

**`api/planning_service.py` functions you will call:**

`build_plan(db, *, goal_type, distance, event_date, available_hours, available_days=None, persist=True)`:
- `goal_type`: one of `"Триатлон"`, `"Бег"`, `"Вело"`, `"Плавание"`.
- `distance`: one of `"Sprint"`, `"Olympic"`, `"Half"`, `"Full"` (triathlon) or `"5K"`, `"10K"`, `"21K"`, `"42K"` (running).
- `event_date`: `"YYYY-MM-DD"` string.
- `available_hours`: float, e.g. `10.0`.
- `available_days`: optional list of day abbreviations `["mon","tue","wed","thu","fri","sat","sun"]`.
- `persist=False`: builds the plan in memory and returns it, does not save to DB.
- Returns a large dict with keys: `plan_id`, `goal`, `totals`, `weeks`, `forecast`.

`reconciliation(db, weeks=1)`:
- Returns `{"has_plan": True, "weeks": 1, "rows": [...]}` where rows are execution comparison rows (planned vs actual TSS, completion fraction, etc.).
- Returns `{"has_plan": False, "rows": []}` if no active plan.

`apply_adjustment(db, *, rows, weeks=1, persist=True)`:
- `rows`: the list returned by `reconciliation(db, weeks)["rows"]`.
- `persist=False`: previews the adjustment without saving.
- Raises `ValueError("no active plan to adjust")` if no active plan.
- Returns a dict with keys: `plan_id`, `adjustment`, `totals`, `weeks`, `forecast`.

**Existing FastAPI planning endpoints** (already in production, frontend already calls them):

    POST /api/planning/build   — body: BuildRequest (goal_type, distance, event_date, available_hours, available_days, persist)
    POST /api/planning/adjust  — body: AdjustRequest (rows, weeks, persist)

The confirm action in the web UI will POST to these endpoints with `persist=True` (the default).

**SSE event types the frontend currently handles** (`web/app/coach/page.tsx`):

    {"type": "meta",      "chat_id": "..."}
    {"type": "tool_call", "name": "...", "tool_name": "...", "status": "done"}
    {"type": "token",     "content": "..."}
    {"type": "done",      "message_id": "...", "chat_id": "..."}
    {"type": "error",     "message": "..."}

After this plan, you will add:

    {"type": "proposal", "action": "build_plan"|"adjust_plan", "params": {...}, "preview": {...}}

**Test baseline:** `python -m pytest tests/smoke -q` → 232 passed, 1 pre-existing fail (`test_google_provider_uses_google_genai_client`). Do not introduce new failures.


## Plan of Work

### Milestone 1 — Backend: proposal tools

Open `models/ai_tools.py`. Near the top, add an import for the planning service:

    from api import planning_service

In `AITools.__init__`, add two entries to `self.tools`:

    "propose_plan_build": self.propose_plan_build,
    "propose_plan_adjustment": self.propose_plan_adjustment,

In `get_available_tools()`, add two entries to the dict:

    "propose_plan_build": (
        "Предложить собрать новый план подготовки. Параметры: goal_type (Триатлон/Бег/Вело/Плавание), "
        "distance (Sprint/Olympic/Half/Full или 5K/10K/21K/42K), event_date (YYYY-MM-DD), "
        "available_hours (часов/неделю), available_days (необязательно, через запятую: mon,tue,...)."
    ),
    "propose_plan_adjustment": (
        "Предложить корректировку активного плана на основе выполненных тренировок текущей недели. "
        "Параметры: weeks (целое, по умолчанию 1)."
    ),

In `format_tool_descriptions_for_ai()`, add two example lines after existing examples (find the block where other examples like `[TOOL: get_active_plan]` are listed):

    [TOOL: propose_plan_build, goal_type=Триатлон, distance=Half, event_date=2026-10-01, available_hours=10]
    [TOOL: propose_plan_adjustment, weeks=1]

Add the two method implementations anywhere after the existing tool methods (before `format_tool_descriptions_for_ai`):

    def propose_plan_build(
        self,
        goal_type: str = "Триатлон",
        distance: str = "Half",
        event_date: str = "",
        available_hours: float = 10.0,
        available_days: str = "",
    ) -> Dict[str, Any]:
        if not event_date:
            return {"success": False, "error": "Укажи дату старта (event_date), например 2026-10-01"}
        days_list = [d.strip() for d in available_days.split(",") if d.strip()] or None
        try:
            preview = planning_service.build_plan(
                self.db,
                goal_type=goal_type,
                distance=distance,
                event_date=event_date,
                available_hours=float(available_hours),
                available_days=days_list,
                persist=False,
            )
        except (ValueError, Exception) as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "is_proposal": True,
            "action": "build_plan",
            "params": {
                "goal_type": goal_type,
                "distance": distance,
                "event_date": event_date,
                "available_hours": float(available_hours),
                "available_days": days_list,
            },
            "preview": {
                "total_weeks": len(preview.get("weeks", [])),
                "peak_tss": preview.get("totals", {}).get("peak_tss"),
                "total_tss": preview.get("totals", {}).get("total_tss"),
                "goal": preview.get("goal", {}),
            },
        }

    def propose_plan_adjustment(self, weeks: int = 1) -> Dict[str, Any]:
        try:
            recon = planning_service.reconciliation(self.db, weeks=int(weeks))
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        if not recon.get("has_plan"):
            return {"success": False, "error": "Нет активного плана для корректировки"}
        rows = recon.get("rows", [])
        try:
            preview = planning_service.apply_adjustment(
                self.db,
                rows=rows,
                weeks=int(weeks),
                persist=False,
            )
        except (ValueError, Exception) as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "is_proposal": True,
            "action": "adjust_plan",
            "params": {"rows": rows, "weeks": int(weeks)},
            "preview": {
                "adjustment_status": preview.get("adjustment", {}).get("status"),
                "adjustment_label": preview.get("adjustment", {}).get("label"),
                "missed_sessions": preview.get("adjustment", {}).get("missed_sessions"),
                "completion_share": preview.get("adjustment", {}).get("completion_share"),
                "peak_tss": preview.get("totals", {}).get("peak_tss"),
                "total_tss": preview.get("totals", {}).get("total_tss"),
            },
        }

**Verify Milestone 1:**

Run from the project root (with `source ai_trainer_env/bin/activate`):

    python -c "
    from data.database import Database
    from config.settings import Settings
    from models.ai_tools import AITools
    db = Database(Settings.DATABASE_PATH)
    t = AITools(db)
    print('propose_plan_build' in t.tools)   # must print True
    print('propose_plan_adjustment' in t.tools)  # must print True
    r = t.execute_tool('propose_plan_build', goal_type='Триатлон', distance='Half', event_date='2026-10-01', available_hours=10)
    print(r.get('success'), r.get('result', {}).get('is_proposal'))  # True True
    "

Expected output: three lines, all `True`. If you see `False` or an exception, debug the import or the method body before proceeding.


### Milestone 2 — Prompt rules

Open `models/ai_coach_runtime.py`. Find the `ДАННЫЕ И ИНСТРУМЕНТЫ:` block in `create_chat_system_prompt_with_tools`. Add two bullet points at the end of that block, before the closing triple-quote:

    • Для предложения собрать новый план ОБЯЗАТЕЛЬНО вызывай **propose_plan_build** с параметрами (goal_type, distance, event_date, available_hours). НЕ ОПИСЫВАЙ план словами — вызывай инструмент, он покажет реальный план.
    • Для предложения скорректировать план по итогам недели ОБЯЗАТЕЛЬНО вызывай **propose_plan_adjustment**. НЕ обещай корректировку без вызова инструмента.
    • НИКОГДА не говори «я составлю план» или «план будет готов» без вызова propose_plan_build или propose_plan_adjustment. Если ты не вызвал эти инструменты, ты не можешь предлагать план.

**Verify Milestone 2:**

    python -c "
    from models.ai_coach_runtime import create_chat_system_prompt_with_tools
    p = create_chat_system_prompt_with_tools(None)
    print('propose_plan_build' in p)  # True
    print('propose_plan_adjustment' in p)  # True
    "

Both must print `True`.


### Milestone 3 — SSE proposal event

Open `api/routers/coach.py`. Find the loop that emits `tool_call` events:

    for item in tool_results:
        yield _sse(
            {
                "type": "tool_call",
                "name": tool_label(item["tool_name"]),
                "tool_name": item["tool_name"],
                "status": "done",
            }
        )

Replace this loop with the following (the structure is the same, but proposals get a separate event type and also still emit a `tool_call`):

    for item in tool_results:
        yield _sse(
            {
                "type": "tool_call",
                "name": tool_label(item["tool_name"]),
                "tool_name": item["tool_name"],
                "status": "done",
            }
        )
        raw_result = item.get("raw_result") or {}
        if raw_result.get("is_proposal"):
            yield _sse(
                {
                    "type": "proposal",
                    "action": raw_result.get("action"),
                    "params": raw_result.get("params", {}),
                    "preview": raw_result.get("preview", {}),
                }
            )

Now you need `raw_result` to be included in `item`. Open `models/ai_coach_runtime.py` and find the `collect_tool_results` function. It currently builds `tool_results` as a list of dicts. Find where each result dict is assembled and add `"raw_result"` alongside `"formatted_result"`. The relevant code is in the inner `replace_tool_call` function (called by `re.sub`). After the line:

    formatted_result = tool_result_formatter(tool_name, data)

add:

    tool_results.append({
        "tool_name": tool_name,
        "formatted_result": formatted_result,
        "raw_result": data,   # ← add this
    })

The existing `tool_results.append(...)` call should already exist nearby — modify it to add `"raw_result": data` as a new key. Do not create a second append.

**Verify Milestone 3:**

Start the API server in one terminal:

    uvicorn api.main:app --reload --port 8000

In another terminal, send a curl request and check that a `proposal` event appears in the SSE stream:

    curl -N -X POST http://localhost:8000/api/coach/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "помоги собрать план на Half Ironman на 2026-10-01, у меня 10 часов в неделю"}' \
      2>/dev/null | grep '"type"'

You should see lines including `"type": "tool_call"` and `"type": "proposal"` in the output, followed by `"type": "token"` lines and `"type": "done"`. If you see only tokens without a proposal event, the coach did not call `propose_plan_build`; check whether the system prompt rule was added correctly (Milestone 2) and whether the tool is registered in `self.tools` (Milestone 1).


### Milestone 4 — Web UI: ProposalCard and event handler

The web frontend is under `web/`. Run `cd web && npm install` if you haven't already, then `npm run dev` to start the Next.js dev server on port 3000.

**Step 4a — ProposalCard component**

Create `web/components/ui/ProposalCard.tsx`:

    "use client";

    import { useState } from "react";

    interface BuildPlanParams {
      goal_type: string;
      distance: string;
      event_date: string;
      available_hours: number;
      available_days?: string[] | null;
    }

    interface AdjustPlanParams {
      rows: unknown[];
      weeks: number;
    }

    interface PlanPreview {
      total_weeks?: number;
      peak_tss?: number;
      total_tss?: number;
      goal?: { goal_type?: string; distance?: string };
      adjustment_status?: string;
      adjustment_label?: string;
      missed_sessions?: number;
      completion_share?: number;
    }

    interface ProposalCardProps {
      action: "build_plan" | "adjust_plan";
      params: BuildPlanParams | AdjustPlanParams;
      preview: PlanPreview;
      onConfirmed: (message: string) => void;
      onCancelled: () => void;
    }

    export function ProposalCard({
      action,
      params,
      preview,
      onConfirmed,
      onCancelled,
    }: ProposalCardProps) {
      const [loading, setLoading] = useState(false);
      const [error, setError] = useState<string | null>(null);

      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

      async function handleConfirm() {
        setLoading(true);
        setError(null);
        try {
          const url =
            action === "build_plan"
              ? `${apiBase}/api/planning/build`
              : `${apiBase}/api/planning/adjust`;
          const body = { ...params, persist: true };
          const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (!res.ok) {
            const detail = await res.json().catch(() => ({}));
            throw new Error(detail?.detail ?? `HTTP ${res.status}`);
          }
          const label =
            action === "build_plan" ? "план сохранён" : "корректировка применена";
          onConfirmed(`✅ Отлично, ${label}! Переходи на страницу Планирование, чтобы увидеть его.`);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Ошибка");
          setLoading(false);
        }
      }

      function handleCancel() {
        onCancelled();
      }

      const title =
        action === "build_plan"
          ? `Собрать план: ${preview.goal?.goal_type ?? ""} ${preview.goal?.distance ?? ""}`
          : `Корректировка плана: ${preview.adjustment_label ?? preview.adjustment_status ?? ""}`;

      return (
        <div className="my-2 rounded-card border border-brand/40 bg-brand/5 p-4 shadow-card">
          <p className="mb-2 font-semibold text-brand">{title}</p>
          <ul className="mb-3 space-y-1 text-sm text-content-secondary">
            {action === "build_plan" && (
              <>
                {preview.total_weeks != null && <li>Недель: {preview.total_weeks}</li>}
                {preview.peak_tss != null && <li>Пик TSS/нед: {preview.peak_tss}</li>}
                {preview.total_tss != null && <li>Общий TSS: {preview.total_tss}</li>}
              </>
            )}
            {action === "adjust_plan" && (
              <>
                {preview.missed_sessions != null && (
                  <li>Пропущено сессий: {preview.missed_sessions}</li>
                )}
                {preview.completion_share != null && (
                  <li>Выполнение: {Math.round(preview.completion_share * 100)}%</li>
                )}
                {preview.peak_tss != null && <li>Новый пик TSS/нед: {preview.peak_tss}</li>}
              </>
            )}
          </ul>
          {error && <p className="mb-2 text-sm text-red-500">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={handleConfirm}
              disabled={loading}
              className="rounded-button bg-brand px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              {loading ? "Сохраняю…" : "Подтвердить"}
            </button>
            <button
              onClick={handleCancel}
              disabled={loading}
              className="rounded-button border border-surface-border px-4 py-1.5 text-sm text-content-secondary disabled:opacity-50"
            >
              Отменить
            </button>
          </div>
        </div>
      );
    }

**Step 4b — Handle proposal event in coach page**

Open `web/app/coach/page.tsx`. Near the top of the file, add an import for ProposalCard:

    import { ProposalCard } from "@/components/ui/ProposalCard";

Find the state declarations (where `useState` calls are) and add:

    const [proposal, setProposal] = useState<{
      action: "build_plan" | "adjust_plan";
      params: Record<string, unknown>;
      preview: Record<string, unknown>;
    } | null>(null);

In the SSE event handler (the callback passed to `streamCoachChat`), find the block of `if/else if` conditions and add a new branch after the `tool_call` branch:

    else if (e.type === "proposal") {
      setProposal({
        action: e.action as "build_plan" | "adjust_plan",
        params: e.params ?? {},
        preview: e.preview ?? {},
      });
    }

Also, in the `done` and `error` branches (where `setStreaming(false)` is called and `setPartial("")`), you do NOT need to clear the proposal — the proposal card persists until the user confirms or cancels.

Find where the chat messages are rendered (the JSX `return` block, inside the scroller div). After the block that renders `messages.map(...)` and before the streaming partial bubble, add:

    {proposal && (
      <ProposalCard
        action={proposal.action}
        params={proposal.params as BuildPlanParams}
        preview={proposal.preview}
        onConfirmed={(msg) => {
          setMessages((m) => [...m, { role: "assistant", content: msg }]);
          setProposal(null);
        }}
        onCancelled={() => setProposal(null)}
      />
    )}

You will need to import the `BuildPlanParams` type from `ProposalCard` (or redefine it inline). The simplest approach is to cast with `as Parameters<typeof ProposalCard>[0]["params"]` or simply use `unknown` cast.

Also, find the `newChat` function:

    function newChat() {
      chatId.current = null;
      setMessages([]);
      setPartial("");
      setTools([]);
    }

Add `setProposal(null);` inside it so switching to a new chat clears any pending proposal.

**Step 4c — TypeScript types for SSE events**

Open `web/lib/api.ts` (the file that defines `streamCoachChat` and the event types it emits). Find the discriminated union type for SSE events (it should have `type: "meta"`, `type: "tool_call"`, `type: "token"`, `type: "done"`, `type: "error"` variants). Add a new variant:

    | { type: "proposal"; action: string; params: Record<string, unknown>; preview: Record<string, unknown> }

**Verify Milestone 4:**

Start both servers:

    # Terminal 1
    uvicorn api.main:app --reload --port 8000

    # Terminal 2
    cd web && npm run dev

Open `http://localhost:3000/coach`. Type: "помоги собрать план на Half Ironman на 2026-10-01, у меня 10 часов в неделю"

Expected:
- Tool chip appears (propose_plan_build / "Предложение плана" label)
- Blue confirmation card appears with weeks, peak TSS, total TSS
- Coach text explains the proposed plan in natural language
- Clicking "Подтвердить" → card shows "Сохраняю…" → success message added to chat → card disappears
- Navigate to `http://localhost:3000/planning` → the new plan is visible

Also test cancellation: type "скорректируй план" → proposal card appears → click "Отменить" → card disappears, no plan saved.

If the ProposalCard does not render because `rounded-card`, `text-brand`, `bg-brand`, etc. CSS variables are not defined, check `web/tailwind.config.ts` for the project's design token names and adjust accordingly. These tokens are used throughout the codebase; grep for `text-brand` in `web/` to find examples.


### Milestone 5 — Smoke tests

Create `tests/smoke/test_ai_tools_proposal.py`. The file must start with:

    """Smoke coverage for proposal tools (propose_plan_build, propose_plan_adjustment)."""
    from __future__ import annotations

    import pytest

    from data.database import Database
    from models.ai_tools import AITools

    pytestmark = pytest.mark.smoke

Write the following tests:

**Test 1** — tools are registered:

    def test_proposal_tools_registered():
        from models.ai_tools import AITools
        import inspect
        src = inspect.getsource(AITools.__init__)
        assert "propose_plan_build" in src
        assert "propose_plan_adjustment" in src

**Test 2** — `propose_plan_build` with missing event_date returns error without crashing:

    def test_propose_plan_build_missing_event_date(tmp_path):
        db = Database(str(tmp_path / "t.db"))
        t = AITools(db)
        r = t.execute_tool("propose_plan_build", goal_type="Триатлон", distance="Half")
        assert r["success"] is False
        assert "event_date" in r.get("error", "").lower() or "дату" in r.get("error", "")

**Test 3** — `propose_plan_build` returns `is_proposal: True` with a real DB:

    def test_propose_plan_build_returns_proposal():
        from config.settings import Settings
        db = Database(Settings.DATABASE_PATH)
        t = AITools(db)
        r = t.execute_tool(
            "propose_plan_build",
            goal_type="Триатлон",
            distance="Half",
            event_date="2027-06-01",
            available_hours=10,
        )
        assert r["success"] is True, r.get("error")
        result = r["result"]
        assert result.get("is_proposal") is True
        assert result.get("action") == "build_plan"
        assert "params" in result
        assert "preview" in result
        assert result["preview"].get("total_weeks", 0) > 0

**Test 4** — `propose_plan_adjustment` on empty DB returns graceful error:

    def test_propose_plan_adjustment_no_plan(tmp_path):
        db = Database(str(tmp_path / "t.db"))
        t = AITools(db)
        r = t.execute_tool("propose_plan_adjustment", weeks=1)
        assert r["success"] is False
        assert "план" in r.get("error", "").lower() or "plan" in r.get("error", "").lower()

**Test 5** — system prompt contains proposal tool names:

    def test_system_prompt_contains_proposal_tools():
        from models.ai_coach_runtime import create_chat_system_prompt_with_tools
        prompt = create_chat_system_prompt_with_tools(None)
        assert "propose_plan_build" in prompt
        assert "propose_plan_adjustment" in prompt

Run:

    python -m pytest tests/smoke/test_ai_tools_proposal.py -v

Expected: 5 passed (Test 3 uses the real DB and may be slow; if it fails with "no activities" or a timeout, that is an environment issue, not a code bug — verify `Settings.DATABASE_PATH` points to a populated DB).

Then run the full suite to confirm no regressions:

    python -m pytest tests/smoke -q

Expected: 232+ passed, 1 pre-existing fail (`test_google_provider_uses_google_genai_client`).


## Concrete Steps

1. Activate the virtualenv: `source ai_trainer_env/bin/activate`
2. Edit `models/ai_tools.py` per Milestone 1.
3. Verify Milestone 1 with the inline python command above.
4. Edit `models/ai_coach_runtime.py` per Milestone 2.
5. Verify Milestone 2 with the inline python command above.
6. Edit `models/ai_coach_runtime.py` again for the `raw_result` addition, then edit `api/routers/coach.py` per Milestone 3.
7. Run `uvicorn api.main:app --reload --port 8000`, send the curl probe, verify a `proposal` event appears.
8. Create `web/components/ui/ProposalCard.tsx` per Milestone 4a.
9. Edit `web/app/coach/page.tsx` per Milestone 4b.
10. Edit `web/lib/api.ts` per Milestone 4c.
11. Run both servers, verify the full UI flow in a browser per Milestone 4 acceptance.
12. Create `tests/smoke/test_ai_tools_proposal.py` per Milestone 5.
13. Run `python -m pytest tests/smoke -q` and confirm 232+ pass, 1 pre-existing fail.
14. Commit all changed files on the current branch (`codex/web-migration-main-pr`).


## Validation and Acceptance

**Primary acceptance criterion:** From a fresh `./run_web.sh` start, a user can type "помоги собрать план для Half Ironman на 2026-10-01, у меня 10 часов в неделю" in the coach chat, see a blue confirmation card with real plan data, click "Подтвердить", see a success message in chat, and then navigate to `/planning` to confirm the plan was saved.

**Secondary criteria:**
- Clicking "Отменить" on the proposal card removes it without touching the DB.
- The coach text response explains the proposal in natural language (it synthesizes from the tool result, not from hallucinated prose).
- `python -m pytest tests/smoke -q` → 232+ pass, 1 pre-existing fail.
- The tool chip labeled "Предложение плана" (or similar) appears in the coach UI during processing.
- "propose_plan_adjustment" is callable and returns a proposal when an active plan exists.

**Regression guard:** The existing planning page (`/planning`) must still work independently — the user can still fill the form and build a plan without using the coach.


## Idempotence and Recovery

All edits are additive. If you partially implement and need to restart:
- Milestone 1 (tools): re-applying is safe; the tools either exist or don't.
- Milestone 3 (`raw_result`): the new field is ignored by existing code that doesn't look for it, so adding it is safe.
- Milestone 4 (UI): the `ProposalCard` will never render if no `proposal` SSE event is received, so the UI degrades gracefully.

If the curl probe in Milestone 3 shows no `proposal` event but the coach text says "я предлагаю", the coach is generating prose without calling the tool — this means the system prompt rule (Milestone 2) was not applied or the tool was not registered (Milestone 1). Debug those before touching the frontend.


## Artifacts and Notes

**`build_plan` return structure (partial):**

    {
      "plan_id": null,               # None when persist=False
      "goal": {"goal_type": "Триатлон", "distance": "Half", "event_date": "2026-10-01"},
      "totals": {"peak_tss": 380, "total_tss": 12400},
      "weeks": [...],                # list of week dicts with tss, phase, etc.
      "forecast": [...]              # Banister CTL/ATL/TSB projection
    }

**`apply_adjustment` return structure (partial):**

    {
      "plan_id": null,
      "adjustment": {
        "status": "corrective",
        "label": "Корректировка нагрузки",
        "missed_sessions": 2,
        "completion_share": 0.65
      },
      "totals": {"peak_tss": 360, "total_tss": 11800},
      "weeks": [...],
      "forecast": [...]
    }

**Tailwind CSS design tokens used in this repo** (check `web/tailwind.config.ts` for exact names):

    rounded-card, rounded-button — border radius tokens
    border-surface-border        — card border color
    bg-surface, shadow-card      — card background + shadow
    text-brand, bg-brand         — primary brand color (blue)
    text-content-secondary       — secondary text


## Interfaces and Dependencies

In `models/ai_tools.py`, the two new methods must have these signatures (types are soft — use `Dict[str, Any]` from the existing imports):

    def propose_plan_build(
        self,
        goal_type: str = "Триатлон",
        distance: str = "Half",
        event_date: str = "",
        available_hours: float = 10.0,
        available_days: str = "",
    ) -> Dict[str, Any]: ...

    def propose_plan_adjustment(self, weeks: int = 1) -> Dict[str, Any]: ...

Both must return `{"success": True, "is_proposal": True, "action": str, "params": dict, "preview": dict}` on success or `{"success": False, "error": str}` on failure.

In `models/ai_coach_runtime.py`, the `collect_tool_results` function must include `"raw_result": data` in each appended item dict (where `data` is the raw `result["result"]` from `execute_tool`).

In `api/routers/coach.py`, after the tool_call loop, the stream function must check `item.get("raw_result", {}).get("is_proposal")` and emit a `{"type": "proposal", "action": ..., "params": ..., "preview": ...}` event.

In `web/lib/api.ts`, the SSE event union type must include the `proposal` variant with fields `action: string`, `params: Record<string, unknown>`, `preview: Record<string, unknown>`.

In `web/components/ui/ProposalCard.tsx`, the component must accept props `action`, `params`, `preview`, `onConfirmed(msg: string): void`, `onCancelled(): void` and render a confirmation card that POSTs to the appropriate `/api/planning/*` endpoint on confirm.
