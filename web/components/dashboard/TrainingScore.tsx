import { TrainingScoreData, TrainingScoreSub } from "@/lib/types";
import { InfoTip } from "@/components/ui/Tooltip";

function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-tone-success" : score >= 40 ? "bg-tone-warning" : "bg-tone-danger";
  return (
    <div className="h-1.5 w-full rounded-full bg-surface-muted overflow-hidden">
      <div
        className={`h-full rounded-full ${color} transition-all`}
        style={{ width: `${Math.max(2, score)}%` }}
      />
    </div>
  );
}

function SubScore({ label, data }: { label: string; data: TrainingScoreSub }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-ink-soft">{label}</span>
        <span className="text-xs font-semibold text-ink">{data.score}</span>
      </div>
      <ScoreBar score={data.score} />
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-ink-faint">{data.label}</span>
        <span className="text-[11px] text-ink-faint">{data.detail}</span>
      </div>
    </div>
  );
}

export function TrainingScore({ data }: { data: TrainingScoreData }) {
  const ringColor =
    data.total >= 70
      ? "text-tone-success"
      : data.total >= 40
      ? "text-tone-warning"
      : "text-tone-danger";

  return (
    <div className="rounded-card border border-surface-border bg-surface p-4 shadow-card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1 text-xs font-medium uppercase tracking-wide text-ink-faint">
          Training Score
          <InfoTip metric="training_score" />
        </div>
        <div className={`text-2xl font-bold ${ringColor}`}>
          {data.total}
          <span className="text-sm font-normal text-ink-faint ml-1">{data.label}</span>
        </div>
      </div>
      <div className="space-y-3">
        <SubScore label="Форма"         data={data.fitness} />
        <SubScore label="Прогресс"      data={data.progression} />
        <SubScore label="Регулярность"  data={data.consistency} />
        <SubScore label="Нагрузка"      data={data.load_mgmt} />
      </div>
    </div>
  );
}
