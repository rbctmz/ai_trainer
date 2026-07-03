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

// --- Decisions ---
export type CoachDecisionType = "Push" | "Moderate" | "Recovery" | "Monitor";

export interface CoachDecision {
  id: number;
  date: string;
  time: string;
  decision_type: CoachDecisionType;
  reason: string;
  workout_id?: string | null;
  chat_id?: string | null;
  message_id?: string | null;
  created_at?: string | null;
}

export interface CoachDecisionDay {
  date: string;
  decisions: CoachDecision[];
}

export interface CoachDecisionsResponse {
  has_data: boolean;
  count: number;
  days: CoachDecisionDay[];
  operational_state?: Record<string, unknown>;
}

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
  sync_state?: "succeeded" | "partial" | "running" | "failed" | "idle" | string;
  title: string;
  summary: string;
  severity: "success" | "warning" | "error" | string;
  mode?: "incremental" | "full" | string;
  counts?: { new: number; updated: number; skipped: number };
  [key: string]: unknown;
}

export interface SyncProgress {
  percent: number;
  message: string;
  step_text?: string | null;
  stats_message?: string | null;
}

export interface SyncJobResponse {
  job_id: string | null;
  sync_state: "idle" | "running" | "succeeded" | "partial" | "failed" | string;
  status?: string;
  started_at?: string | null;
  finished_at?: string | null;
  days?: number | null;
  progress?: SyncProgress | null;
  result?: SyncResult | null;
  error?: { message?: string } | null;
  reused?: boolean;
  operational_state?: Record<string, unknown>;
}

// --- Planning ---
export interface PlanningStatus {
  metrics: { ctl: number; atl: number; tsb: number; form: string };
  has_plan: boolean;
  checkpoint: Record<string, unknown> | null;
  demand?: PlanningDemand;
  demand_options?: PlanningDemand[];
}

export interface PlanningDemand {
  level: string;
  label: string;
  multiplier: number;
  description?: string;
}

export interface WeeklyTargetRow {
  key: "goal_need" | "availability_cap" | "recent_load" | "base_weekly_tss" | string;
  label: string;
  value: number;
  unit: string;
  detail: string;
}

export interface WeeklyTargetBreakdown {
  rows: WeeklyTargetRow[];
  availability: Record<string, unknown>;
  recent_load: Record<string, unknown>;
}

export interface PlanningWeeklyTarget {
  target_weekly_tss: number;
  base_weekly_tss?: number;
  final_target_weekly_tss?: number;
  range_min: number;
  range_max: number;
  history: { last_week: number; avg_4: number; best_8: number };
  demand?: PlanningDemand;
  breakdown?: WeeklyTargetBreakdown;
}

export interface TargetPreview {
  goal: { goal_type: string; distance: string };
  weekly_target: PlanningWeeklyTarget;
  breakdown: WeeklyTargetBreakdown;
  demand: PlanningDemand;
  options: PlanningDemand[];
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
  } & PlanningWeeklyTarget;
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
  tone: "danger" | "warning" | "neutral" | "success";
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

export interface PlanningHistoryItem {
  checkpoint_id: number | null;
  date: string;
  date_label: string;
  type: "reduce" | "swap" | "regenerate" | string;
  type_label: string;
  source: string;
  source_label: string;
  outcome_note: string;
  title: string;
  total_tss: number;
  peak_tss: number;
}

export interface PlanningHistory {
  has_history: boolean;
  items: PlanningHistoryItem[];
}
