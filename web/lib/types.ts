// Mirrors the JSON shape returned by GET /api/dashboard/summary.
// Source of truth: ui/pages/dashboard.py::_build_dashboard_v2_summary.

export type Tone = "danger" | "warning" | "success" | "neutral";

export interface TodayState {
  date: string;
  state_label: string;
  tone: Tone;
  readiness: number;
  tsb: number;
  ctl: number;
  hrv: number | null;
}

export interface WorkoutCard {
  title: string;
  subtitle?: string;
  tss: number;
  sport: string;
  action: string;
  button: string;
}

export interface WeekLoad {
  planned_tss: number;
  actual_tss: number;
  remaining_tss: number;
  forecast_tss: number;
  status: string;
}

export type DayStatus = "today" | "planned" | "done" | "rest" | "empty";

export interface NextDay {
  date: string;
  label: string;
  status: DayStatus;
  status_label: string;
  sport: string;
  tss: number;
}

export interface PlanCard {
  title: string;
  subtitle?: string;
  status: string;
  button: string;
}

export interface NextAction {
  icon: string;
  title: string;
  button: string;
  desc: string;
  reason: string;
  action: string;
}

export interface DashboardSummary {
  today: TodayState;
  workout: WorkoutCard;
  week: WeekLoad;
  next_days: NextDay[];
  plan: PlanCard;
  next_action: NextAction;
}

export interface DashboardResponse {
  has_data: boolean;
  summary: DashboardSummary | null;
}

// --- HRV ---
export interface HrvSignal {
  severity: "warning" | "success" | "neutral";
  label: string;
}

export interface HrvSummary {
  has_data: boolean;
  latest: {
    date: string;
    rmssd: number;
    recovery_score: number | null;
    recovery_info: string;
  } | null;
  baseline: { rmssd: number; window_days: number } | null;
  trend: { date: string; rmssd: number }[];
  signals: HrvSignal[];
}

// --- Activities ---
export interface Activity {
  activity_id: string;
  date: string;
  date_label?: string;
  sport: string;
  sport_label?: string;
  duration_minutes: number | null;
  moving_duration_minutes?: number | null;
  distance_km: number | null;
  tss: number | null;
  garmin_training_load?: number | null;
  source_tss?: number | null;
  tss_method?: string | null;
  tss_source?: "power" | "heart_rate" | "heuristic" | "none" | "unknown";
  avg_hr: number | null;
  max_hr: number | null;
  elevation_gain: number | null;
  calories: number | null;
}

export interface ActivitiesResponse {
  has_data: boolean;
  count: number;
  totals: {
    count?: number;
    distance_km?: number | null;
    duration_hours?: number | null;
    tss?: number | null;
  };
  items: Activity[];
}

// --- Coach ---
export interface ChatSummary {
  id: string;
  title: string;
  date: string | null;
  message_count: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string | null;
}

export type CoachProposalAction = "build_plan" | "adjust_plan";

export interface CoachProposalEvent {
  type: "proposal";
  action: CoachProposalAction;
  params: Record<string, unknown>;
  preview: Record<string, unknown>;
}

// Event protocol (after the agentic finalize refactor): meta → tool_call(s) →
// streamed token(s) of the final synthesized answer → done. No `replace`.
export type CoachEvent =
  | { type: "meta"; chat_id: string }
  | { type: "tool_call"; name: string; tool_name?: string; status: string }
  | CoachProposalEvent
  | { type: "token"; content: string }
  | { type: "done"; message_id: string; chat_id: string }
  | { type: "error"; message: string };

// --- Sleep ---
export interface SleepSummary {
  has_data: boolean;
  latest: {
    date: string;
    hours: number | null;
    score: number | null;
    efficiency: number | null;
    awakenings: number | null;
    stages: { deep: number | null; light: number | null; rem: number | null };
  } | null;
  averages: { hours: number | null; score: number | null; window_days: number } | null;
  trend: { date: string; hours: number; score: number | null }[];
}

// --- Sync ---
export interface SyncResult {
  title: string;
  summary: string;
  severity: "success" | "warning" | "error" | string;
  [key: string]: unknown;
}

// --- Planning ---
export interface PlanningStatus {
  metrics: { ctl: number; atl: number; tsb: number; form: string };
  has_plan: boolean;
  checkpoint: Record<string, unknown> | null;
}

export interface PlanWeek {
  index: number;
  week_start: string;
  phase: string;
  weekly_tss: number;
  capacity_tss: number | null;
  bike: number;
  run: number;
  swim: number;
  adjustment_note: string;
}

export interface ForecastPoint {
  date: string;
  ctl: number;
  atl: number;
  tsb: number;
}

export interface BuiltPlan {
  plan_id: string | null;
  goal: {
    goal_type: string;
    distance: string;
    event_date: string;
    weeks_to_race: number;
  };
  weekly_target: {
    target_weekly_tss: number;
    range_min: number;
    range_max: number;
    history: { last_week: number; avg_4: number; best_8: number };
  };
  totals: { peak_tss: number; total_tss: number };
  weeks: PlanWeek[];
  forecast: { points: ForecastPoint[]; final_tsb: number; message: string };
}

// --- Planning: export ---
export interface PlanDay {
  index: number;
  date: string;
  sport: string;
  sport_label: string;
  tss: number;
  name: string;
  phase: string;
}

export interface PlanExport {
  has_plan: boolean;
  goal: { goal_type: string; distance: string } | null;
  days: PlanDay[];
}

// --- Dashboard Widgets ---
export interface TrainingScoreSub {
  score: number;
  label: string;
  detail: string;
}

export interface TrainingScoreData {
  total: number;
  label: string;
  fitness: TrainingScoreSub;
  progression: TrainingScoreSub;
  consistency: TrainingScoreSub;
  load_mgmt: TrainingScoreSub;
}

export interface DailyOutlookData {
  text: string;
  tone: "warning" | "neutral";
}

export interface RaceProjectionData {
  event_date: string;
  days_to_race: number;
  projected_ctl: number;
  projected_tsb: number;
  fresh_for_race: boolean;
  status: "on_track" | "behind";
  label: string;
}

export interface DashboardWidgets {
  has_data: boolean;
  training_score: TrainingScoreData;
  daily_outlook: DailyOutlookData;
  race_projection: RaceProjectionData | null;
}

// --- Planning: adjust (execution feedback) ---
export type Outcome = "as_planned" | "skipped" | "reduced" | "unavailable";

export interface ReconRow {
  index: number;
  date: string;
  date_label?: string;
  sport_label: string;
  session_role_label?: string;
  planned_total_tss: number;
  actual_total_tss: number;
  outcome: Outcome;
  [key: string]: unknown; // round-tripped back to the backend untouched
}

export interface ReconResponse {
  has_plan: boolean;
  weeks?: number;
  rows: ReconRow[];
}

export interface AdjustResult {
  plan_id: string | null;
  adjustment: {
    status: string;
    label: string;
    missed_sessions: number;
    completion_share: number;
  };
  totals: { peak_tss: number; total_tss: number };
  weeks: PlanWeek[];
  forecast: { points: ForecastPoint[]; final_tsb: number; message: string };
}
