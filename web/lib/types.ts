// Mirrors the JSON shape returned by GET /api/dashboard/summary.
// Source of truth: models/dashboard_summary.py through the FastAPI contract.

export type Tone = "danger" | "warning" | "success" | "neutral";

export type ReadinessSnapshotStatus = "unknown" | "low" | "limited" | "ready" | "strong" | "stale";

export interface ReadinessSnapshotFactor {
  key: string;
  label: string;
  score: number | null;
  raw_value: number | null;
  source: string;
}

export interface ReadinessSnapshot {
  score: number | null;
  status: ReadinessSnapshotStatus | string;
  computed_at: string | null;
  is_provisional: boolean;
  source_completeness: number;
  factors: ReadinessSnapshotFactor[];
  missing_inputs: string[];
  stale: boolean;
  reason: string;
}

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
  readiness_snapshot?: ReadinessSnapshot;
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
  tss_ftp_used?: number | null;
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

export type CoachProposalAction = "build_plan" | "adjust_plan" | "recovery_replan";

export interface CoachProposalEvent {
  type: "proposal";
  proposal_id: number;
  action: CoachProposalAction;
  status: "pending" | "approved" | "rejected" | "failed" | "rolled_back" | string;
  params: Record<string, unknown>;
  preview: Record<string, unknown>;
}

// Event protocol (after the agentic finalize refactor): meta → tool_call(s) →
// streamed token(s) of the final synthesized answer → done. No `replace`.
export type CoachEvent =
  | {
      type: "meta";
      chat_id: string;
      readiness_snapshot?: ReadinessSnapshot;
      readiness_conflicts?: Record<string, unknown>;
      recovery_replan?: Record<string, unknown>;
    }
  | { type: "tool_call"; name: string; tool_name?: string; status: string }
  | CoachProposalEvent
  | { type: "token"; content: string }
  | { type: "done"; message_id: string; chat_id: string }
  | { type: "error"; message: string; readiness_snapshot?: ReadinessSnapshot };

// --- Decisions ---
export type CoachDecisionType = "Push" | "Moderate" | "Recovery" | "Monitor";

export interface CoachDecision {
  id: number;
  date: string;
  time: string;
  decision_type: CoachDecisionType;
  reason: string;
  count?: number;
  first_time?: string;
  workout_id?: string | null;
  chat_id?: string | null;
  message_id?: string | null;
  created_at?: string | null;
}

export interface CoachProposal {
  id: number;
  date: string;
  time?: string;
  action: CoachProposalAction;
  status: "pending" | "approved" | "rejected" | "failed" | "rolled_back" | string;
  params: Record<string, unknown>;
  preview: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: string | null;
  chat_id?: string | null;
  message_id?: string | null;
  resolved_at?: string | null;
  created_at?: string | null;
  source?: string | null;
  source_key?: string | null;
}

export interface RecoveryDecision {
  id: number;
  fingerprint: string;
  date: string;
  time?: string;
  outcome: "silence" | "data_gap" | "conflict" | string;
  reason: string;
  report: Record<string, unknown>;
  plan_checkpoint_id?: number | null;
  proposal_id?: number | null;
  created_at?: string | null;
}

export interface RecoveryDecisionDay {
  date: string;
  recovery_decisions: RecoveryDecision[];
}

export interface CoachDecisionDay {
  date: string;
  decisions: CoachDecision[];
}

export interface CoachProposalDay {
  date: string;
  proposals: CoachProposal[];
}

export interface CoachDecisionsResponse {
  has_data: boolean;
  count: number;
  days: CoachDecisionDay[];
  proposal_count?: number;
  proposal_days?: CoachProposalDay[];
  pending_proposal_count?: number;
  pending_proposal_days?: CoachProposalDay[];
  recovery_count?: number;
  recovery_days?: RecoveryDecisionDay[];
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

// --- Athlete profile ---
export interface AthleteProfile {
  ftp: number | null;
  weight_kg: number | null;
  lthr: number | null;
  source: string | null;
  synced_at: string | null;
}

export interface AthleteProfileResponse {
  has_data: boolean;
  profile: AthleteProfile | null;
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
export type CoachConstraintKind =
  | "sick"
  | "unavailable"
  | "forced_rest"
  | "manual_delete"
  | "disabled_plan_day"
  | string;

export interface CoachConstraint {
  id: number;
  date: string;
  kind: CoachConstraintKind;
  status: "active" | "inactive" | string;
  source: string;
  note?: string | null;
  plan_id?: string | null;
  session_id?: string | null;
  metadata: Record<string, unknown>;
  resolved_at?: string | null;
  created_at?: string | null;
}

export interface ConstraintApplication {
  applied_count: number;
  protected_dates: string[];
  constraints: Array<{
    date: string;
    constraint_id?: number | null;
    kind?: CoachConstraintKind;
    source?: string;
  }>;
}

export interface PlanningStatus {
  metrics: { ctl: number; atl: number; tsb: number; form: string };
  readiness_snapshot?: ReadinessSnapshot;
  active_constraint_count?: number;
  active_constraints?: CoachConstraint[];
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

export interface RaceEvent {
  date: string;
  priority: "A" | "B" | "C";
  label: string;
  source?: "user" | "intervals_icu" | "legacy_checkpoint" | string;
  source_id?: string;
  category?: string;
  discipline?: "triathlon" | "bike" | "run" | "swim" | null;
  discipline_provenance?: string;
  discipline_confidence?: number;
  priority_provenance?: string;
  confirmed?: boolean;
  requires_confirmation?: boolean;
}

export interface PlanningEventsResponse {
  oldest: string;
  newest: string;
  count: number;
  events: RaceEvent[];
  read_only: true;
}

export interface BuiltPlan {
  plan_id: string | null;
  planning_mode: "event_goal" | "training_goal" | "manual";
  confirmation_required: boolean;
  preview: {
    base_checkpoint_id: number;
    events_before: RaceEvent[];
    events_after: RaceEvent[];
    phases_before: string[];
    phases_after: string[];
    weekly_tss_before: number[];
    weekly_tss_after: number[];
    weekly_tss_delta: number;
  };
  goal: {
    goal_type: string;
    distance: string;
    event_date: string;
    events: RaceEvent[];
    weeks_to_race: number | null;
    macrocycle_event_date: string;
  };
  event_overlay: {
    rule_version: string;
    protected_dates: string[];
    overlays: Array<{ date: string; priority: "A" | "B" | "C"; label: string; affected_dates: string[] }>;
  };
  weekly_target: {
    target_weekly_tss: number;
  } & PlanningWeeklyTarget;
  totals: { peak_tss: number; total_tss: number };
  constraint_application?: ConstraintApplication;
  weeks: PlanWeek[];
  forecast: { points: ForecastPoint[]; final_tsb: number; message: string };
}

// --- Planning: export ---
export interface WorkoutTarget {
  type?: string;
  unit?: string;
  low?: number;
  high?: number;
  fast?: number;
  slow?: number;
  [key: string]: unknown;
}

export interface WorkoutStep {
  name: string | null;
  intensity: string | null;
  duration_seconds: number | null;
  target: WorkoutTarget | null;
}

export interface WorkoutLeg {
  leg_index: number | null;
  leg_id: string | null;
  sport: string | null;
  template_name: string | null;
  duration_minutes: number | null;
  target_tss: number | null;
  target_provenance: Record<string, unknown> | null;
  steps: WorkoutStep[];
}

export interface PlanDay {
  index: number;
  date: string;
  sport: string;
  sport_label: string;
  tss: number;
  name: string;
  phase: string;
  kind: string;
  catalog_version: string | null;
  template_key: string | null;
  template_version: number | null;
  template_name: string | null;
  stimulus: string | null;
  fatigue_cost: number[];
  expected_recovery_hours: number | null;
  materialization_status: string | null;
  target_provenance: Record<string, unknown> | null;
  selection_evidence: Record<string, unknown> | null;
  steps: WorkoutStep[];
  legs: WorkoutLeg[];
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
  readiness_snapshot?: ReadinessSnapshot;
  training_score: TrainingScoreData;
  daily_outlook: DailyOutlookData;
  race_projection: RaceProjectionData | null;
}

// --- Planning: evidence reconciliation + future-only rebalance ---
export type MatchStatus = "matched" | "ambiguous" | "unmatched" | "unplanned";
export type PlanAdherence = "exact" | "substituted" | "major_deviation" | "unknown";

export interface ReconActivity {
  activity_id: string;
  date: string;
  sport: string;
  tss: number;
  duration_minutes: number;
  name: string;
}

export interface ReconRow {
  index: number;
  session_id: string;
  date: string;
  name: string;
  sport: string;
  role: string;
  tss: number;
  duration_minutes: number;
  match_status: MatchStatus;
  match_method: string;
  confidence: number;
  evidence: string[];
  adherence: PlanAdherence;
  actual_activity_ids: string[];
  actual_activities: ReconActivity[];
  candidate_activities: ReconActivity[];
  actual_total_tss: number;
  actual_duration_minutes: number;
}

export interface ReconResponse {
  has_plan: boolean;
  rule_version?: string;
  base_checkpoint_id?: number;
  as_of?: string;
  window?: { start: string; end: string; weeks: number };
  rows: ReconRow[];
  unplanned_activities: ReconActivity[];
  data_quality?: {
    status: "sufficient" | "data_gap";
    planned_session_count: number;
    matched_count: number;
    ambiguous_count: number;
    unmatched_count: number;
    coverage: number;
    reasons: string[];
  };
  metrics?: {
    planned_tss: number;
    matched_actual_tss: number;
    unplanned_tss: number;
    total_actual_tss: number;
    exact_count: number;
    substituted_count: number;
    major_deviation_count: number;
    unknown_count: number;
  };
  provider?: { status: string; activity_count?: number; workout_event_count?: number; error?: string };
}

export interface RebalanceChange {
  index: number;
  date: string;
  session_id: string;
  session_role: string;
  before_tss: number;
  after_tss: number;
  delta_tss: number;
}

export interface RebalancePreview {
  rule_version: string;
  base_checkpoint_id: number;
  as_of: string;
  status: "proposal" | "no_change";
  reason: string;
  preview_fingerprint: string;
  overage_tss?: number;
  reduction_budget_tss: number;
  future_tss_delta: number;
  unused_reduction_tss: number;
  changes: RebalanceChange[];
}

export interface RebalancePreviewResult {
  has_plan: boolean;
  reconciliation: ReconResponse;
  preview: RebalancePreview | null;
}

export interface RebalanceConfirmResult {
  plan_id: string;
  applied_checkpoint_id: number;
  base_checkpoint_id: number;
  checkpoint_source: "weekly_rebalance";
  preview: RebalancePreview;
}

// Compatibility result for existing Coach `adjust_plan` proposals. The Planning
// Adjust tab uses RebalancePreviewResult/RebalanceConfirmResult instead.
export interface AdjustResult {
  plan_id: string | null;
  adjustment: {
    status: string;
    label: string;
    missed_sessions: number;
    completion_share: number;
  };
  totals: { peak_tss: number; total_tss: number };
  constraint_application?: ConstraintApplication;
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

// --- Экран «Сегодня» (issues #158/#174) -----------------------------------

export type TodayScreenState =
  | "silence"
  | "conflict_actionable"
  | "conflict_unactionable"
  | "data_gap"
  | "no_plan";

export type TodayPrimaryActionKind =
  | "follow_plan"
  | "review_proposal"
  | "inspect_evidence"
  | "sync_or_wait"
  | "open_planning";

export interface TodayPrimaryAction {
  kind: TodayPrimaryActionKind | string;
  enabled: boolean;
  reason: string;
}

export interface TodayReadiness {
  score: number;
  status: string;
  confidence: number | null;
  computed_at?: string | null;
  source_completeness?: number | null;
  drivers: Array<Record<string, unknown>>;
  factors: Array<Record<string, unknown>>;
  missing_inputs?: string[];
  tsb: { ctl: number | null; atl: number | null; tsb: number | null; window_days: number } | null;
  stale: boolean;
  reason: string | null;
}

export interface TodaySession {
  session_id?: string | null;
  date: string;
  name: string;
  role: string;
  role_label: string;
  tss: number;
  sport_label: string;
  is_key: boolean;
  duration_minutes?: number | null;
  phase?: string | null;
  transition_minutes?: number | null;
  kind?: string;
  catalog_version?: string | null;
  template_key?: string | null;
  template_version?: number | null;
  template_name?: string | null;
  stimulus?: string | null;
  fatigue_cost?: number[];
  expected_recovery_hours?: number | null;
  materialization_status?: string | null;
  target_provenance?: Record<string, unknown> | null;
  steps?: WorkoutStep[];
  legs?: WorkoutLeg[];
}

export interface TodayYesterday {
  status: "available" | "empty" | "unavailable" | string;
  reason: string | null;
  date: string;
  planned_sessions: number;
  matched_sessions: number;
  adherence: Record<"exact" | "substituted" | "major_deviation" | "unknown", number>;
  planned_tss: number;
  matched_actual_tss: number;
  unplanned_tss: number;
  total_actual_tss: number;
  rows: ReconRow[];
  unplanned_activities: ReconActivity[];
  data_quality: Record<string, unknown>;
  rule_version: string | null;
  base_checkpoint_id: number | null;
  activities: number;
  minutes: number;
  tss: number;
  sports: string[];
}

export interface TodayGateConflict {
  date?: string;
  days_until?: number;
  severity?: string;
  kind?: string;
  session?: Record<string, unknown>;
  evidence?: string[];
}

export interface TodayGate {
  outcome: string | null;
  reason: string | null;
  data_gap: boolean;
  silence: boolean;
  conflicts: TodayGateConflict[];
  sessions_evaluated: Array<Record<string, unknown>>;
  readiness: Record<string, unknown> | null;
  proposal_gap: string | null;
  decision: {
    id: number | null;
    fingerprint: string | null;
    plan_checkpoint_id: number | null;
  };
  forecast_error?: string | null;
}

export interface TodayProposalResolution {
  relation: "current" | "stale" | "resolved" | "none" | "unavailable" | string;
  proposal: CoachProposal | null;
  base_checkpoint_id: number | null;
  active_checkpoint_id: number | null;
  reason: string;
}

export interface TodayForecastPrediction {
  id: number;
  target_key: string;
  revision: number;
  rule_version: string;
  target_date: string;
  plan_checkpoint_id: number;
  plan_session_index: number;
  planned_role: string;
  planned_sport: string;
  planned_tss: number;
  planned_duration_minutes: number | null;
  prediction_pct: number;
  prediction_band: string;
  evidence: string[];
  status: string;
  created_at: string;
}

export interface TodayForecast {
  mode: "shadow";
  affects_decision: false;
  relation: "current_checkpoint" | "stale_checkpoint" | "none" | "unavailable" | string;
  prediction: TodayForecastPrediction | null;
  session_id: string | null;
  target_time_provenance: "date_only" | string;
  prestart_status: string;
  error: string | null;
}

export interface SessionFeedbackRecord {
  id: number;
  fingerprint: string;
  target_key: string;
  revision: number;
  supersedes_feedback_id: number | null;
  session_id: string;
  parent_session_id: string | null;
  match_revision_id: number | null;
  actual_activity_ids: string[];
  completion_status: string;
  completion_pct: number | null;
  session_rpe_1_10: number | null;
  quality_rating_1_5: number | null;
  note: string | null;
  source: "user_web" | "admin_resolve" | string;
  provenance_label: "athlete-entered" | "admin-entered" | string;
  session_end_at_utc: string | null;
  session_end_provenance: string;
  status: "active" | "tombstone" | string;
  rule_version: string;
  submitted_at: string;
  created_at: string;
}

export interface SessionFeedbackPrompt {
  prompt_fingerprint: string;
  session_id: string;
  parent_session_id: string | null;
  date: string;
  name: string;
  role: string;
  kind: "single" | "composite" | string;
  state:
    | "not_eligible"
    | "pending_match"
    | "ready"
    | "submitted"
    | "superseded"
    | "dismissed"
    | string;
  reason: string;
  is_primary: boolean;
  match_status: string;
  match_method: string;
  match_confidence: number;
  adherence: string;
  actual_activity_ids: string[];
  actual_activities: ReconActivity[];
  session_end_at_utc: string | null;
  session_end_provenance: string;
  allowed_completion_statuses: string[];
  feedback: SessionFeedbackRecord | null;
  provenance_label: string | null;
}

export interface TodayFeedback {
  status: "available" | "unavailable" | string;
  reason?: string | null;
  rule_version: string | null;
  prompts: SessionFeedbackPrompt[];
  primary: SessionFeedbackPrompt | null;
  metrics: {
    eligible?: number;
    submitted?: number;
    dismissed?: number;
    pending_match?: number;
  };
}

export interface SessionFeedbackHistoryResponse {
  session_id: string;
  history: SessionFeedbackRecord[];
  current: SessionFeedbackRecord | null;
  evaluations: Array<Record<string, unknown>>;
}

export interface TodayResponse {
  snapshot_version: "today_decision_snapshot_v2" | string;
  date: string;
  state: TodayScreenState | string;
  reason: string;
  primary_action: TodayPrimaryAction;
  readiness: TodayReadiness | null;
  readiness_source: string;
  session: TodaySession | null;
  gate: TodayGate;
  proposal: TodayProposalResolution;
  forecast: TodayForecast;
  pending_proposal: CoachProposal | null;
  yesterday: TodayYesterday;
  feedback: TodayFeedback;
  loop_outcome: string | null;
  provenance: Record<string, unknown>;
  operational_state?: Record<string, unknown>;
}

// --- Prospective personal recovery analytics (shadow-only) ---
export type RecoveryMaturity =
  | "collection_only"
  | "early_signal"
  | "exploratory"
  | "shadow_pattern";

export interface RecoveryCurvePoint {
  day: 1 | 2 | 3;
  n_observed: number;
  missing: number;
  median: number | null;
  q1: number | null;
  q3: number | null;
  interval: { low: number; high: number } | null;
}

export interface RecoveryCohort {
  cohort_id: string;
  dimensions: {
    stimulus_family: string;
    sport: string;
    load_bucket: string;
    adherence: string;
  };
  n: number;
  distinct_weeks: number;
  maturity: RecoveryMaturity;
  publishable: boolean;
  points: RecoveryCurvePoint[];
  last_observation: string | null;
  rpe_overlays: Record<
    "low" | "moderate" | "high",
    {
      n: number;
      distinct_weeks: number;
      maturity: RecoveryMaturity;
      publishable: boolean;
      points: RecoveryCurvePoint[];
    }
  >;
  included_episode_ids: number[];
}

export interface RecoveryAnalyticsResponse {
  rule_version: string;
  bootstrap_rule_version: string;
  capture_mode: "prospective";
  maturity: RecoveryMaturity;
  generated_at: string | null;
  coverage: {
    total_latest: number;
    eligible: number;
    excluded: number;
    backfilled_excluded: number;
    exclusion_counts: Record<string, number>;
  };
  snapshot_coverage: {
    total: number;
    eligible: number;
    ineligible: number;
    distinct_days: number;
  };
  registry: RecoveryCohort[];
  guardrails: {
    shadow_mode: true;
    affects_decisions: false;
    provider_writeback: false;
    causal_claim: false;
    message: string;
  };
}
