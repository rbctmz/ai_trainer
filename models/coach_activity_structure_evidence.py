"""Bounded activity claim checks; not a general natural-language fact checker."""
from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Any, Iterable, Mapping

_NUMBERS = ("duration_minutes", "distance_km", "avg_hr", "avg_power", "tss")
_INTERVAL_NUMBERS = ("index", "duration_seconds", "distance_km", "avg_watts", "avg_hr", "avg_cadence")
_ACTIVITY = re.compile(r"отрезк|интервал|структур|кэш|карточк|активност", re.I)
_CHECK = re.compile(r"проверк|карточк|открыти|запрос|синхронизац", re.I)
_FUTURE = re.compile(r"\b(?:подтвердит|докажет|появятся|появится|попадут|выгрузятся|"
                     r"материализуются|станет\s+доступ\w*|станут\s+доступ\w*|будут\s+доступ\w*)\b", re.I)
_NAMING = re.compile(r"\b(?:назову|перечислю|покажу|разберу|получим|получите)\b", re.I)
_UNCERTAIN = re.compile(r"(?:может|могут|могла\s+бы|возможно|не\s+факт,?\s+что|"
                        r"нельзя\s+(?:утверждать|гарантировать),?\s+что|не\s+означает,?\s+что|"
                        r"не\s+обещаю,?\s+что)\b", re.I)
_DENIED_GUARANTEES = (
    re.compile(r"\bне\s+могу\s+гарантировать\s*,?\s*что\s+(?P<claim>[^,;.!?\n]+)", re.I),
    re.compile(r"\bгарантировать\s*,?\s*что\s+(?P<claim>[^,;.!?\n]+?)\s*(?:,|[—–])?"
               r"\s+не\s+могу\b(?!\s+не\b)", re.I),
)
_ABSENCE = re.compile(r"\b(?:отрезков|интервалов)(?:\s+(?!не\b|нет\b)[\w.-]+){0,9}\s+(?:нет|не\s+было)\b|"
                      r"\bнет\s+(?:отрезков|интервалов)\b", re.I)
_ANALYZER_EMPTY = re.compile(r"\bне\s+(?:наш[её]л|выявил)\s+(?:отрезков|интервалов)\b|"
                             r"\b(?:отрезки|интервалы)\s+не\s+(?:найдены|выявлены)\b", re.I)
_POSITIVE_STRUCTURE = re.compile(
    r"\b(?:вижу|видны|найдены|обнаружены)\s+\d+\s+(?:отрезк\w*|интервал\w*)\b|"
    r"\bфактическая\s+структура\s*:\s*\d+\s*[×xх*]\s*\d+|"
    r"\b(?:первый|второй|третий|\d+[-й]*)\s+(?:отрезок|интервал)\s+"
    r"(?:длился|занял|продолжался)\s+\d+", re.I)
_CLAIM_SOURCE = re.compile(r"\b(?:(?P<plan>в\s+плане|по\s+плану|планов\w*)|"
                           r"(?P<actual>фактическ\w*|выполненн\w*|активност\w*))", re.I)
_CONTRAST = re.compile(r",\s*(?:а|но|однако|зато)\b\s*", re.I)
_REAL_ABSENCE = re.compile(r"(?:сесси\w*|трениров\w*).{0,30}(?:прошл\w*|был\w*|выполнен\w*)"
                           r"\s+без\s+(?:интервал\w*|отрезк\w*)", re.I)
_EFFORT = re.compile(r"(?:сесси\w*|трениров\w*|бег).{0,24}(?:был\w*|прошл\w*).{0,20}"
                     r"(?:ровн\w*|равномерн\w*|л[её]гк\w*)", re.I)


def _numeric_fields(row: Mapping[str, Any], names: Iterable[str]) -> dict[str, int | float]:
    values = {}
    for key in names:
        value = row.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            continue
        try:
            if math.isfinite(value):
                values[key] = value
        except OverflowError:
            pass
    return values


def activity_structure_evidence(tools: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Allowlist and deterministically merge successful raw activity tool data."""
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for tool in tools:
        raw = tool.get("raw_result")
        if tool.get("success") is not True or tool.get("tool_name") != "get_activity_structure" or not isinstance(raw, Mapping):
            continue
        activities = raw.get("activities")
        if not isinstance(activities, list):
            continue
        for activity in activities:
            if not isinstance(activity, Mapping):
                continue
            activity_id, day = activity.get("activity_id"), activity.get("date")
            try:
                if not isinstance(activity_id, str) or not activity_id.strip() or not isinstance(day, str):
                    continue
                day = date.fromisoformat(day).isoformat()
            except ValueError:
                continue
            status = activity.get("structure_status")
            if not isinstance(status, str) or status not in {"unavailable", "empty", "structured"}:
                status = "unavailable"
            row: dict[str, Any] = {"activity_id": activity_id, "date": day, "structure_status": status,
                                   **_numeric_fields(activity, _NUMBERS)}
            if isinstance(activity.get("sport"), str) and activity["sport"] in {"run", "bike", "swim"}:
                row["sport"] = activity["sport"]
            if isinstance(activity.get("source"), str) and activity["source"] in {"intervals", "garmin"}:
                row["source"] = activity["source"]
            if isinstance(activity.get("reason"), str) and activity["reason"] in {"not_fetched", "no_provider_link", "corrupt_cache"}:
                row["reason"] = activity["reason"]
            analyzed = activity.get("analyzed")
            if isinstance(analyzed, str):
                try:
                    row["analyzed"] = datetime.fromisoformat(analyzed.replace("Z", "+00:00")).isoformat()
                except ValueError:
                    pass
            intervals = activity.get("intervals")
            count = activity.get("interval_count", len(intervals) if isinstance(intervals, list) else None)
            if status == "structured" and isinstance(intervals, list) and intervals and all(isinstance(i, Mapping) for i in intervals):
                row["intervals"] = [_numeric_fields(item, _INTERVAL_NUMBERS) for item in intervals]
                row["interval_count"] = len(intervals)
                if (any(not item for item in row["intervals"]) or not isinstance(count, int)
                        or isinstance(count, bool) or count != len(intervals)
                        or activity.get("has_structure", True) is not True):
                    row = {"activity_id": activity_id, "date": day, "structure_status": "unavailable", "reason": "invalid_evidence"}
            elif status == "empty" and isinstance(count, int) and not isinstance(count, bool) and count == 0 and intervals in (None, []) and activity.get("has_structure", False) is False:
                row["interval_count"] = 0
            elif status != "unavailable":
                row = {"activity_id": activity_id, "date": day, "structure_status": "unavailable", "reason": "invalid_evidence"}
            key = (activity_id, day)
            if key in records and records[key] != row:
                records[key] = {"activity_id": activity_id, "date": day, "structure_status": "unavailable", "reason": "conflicting_evidence"}
            else:
                records[key] = row
    return [records[key] for key in sorted(records)]


def _qualified(prefix: str) -> bool:
    # Only the local clause can qualify a claim. Earlier "вероятно" does not
    # excuse a later assertion that a future check WILL confirm a hypothesis.
    prefix = re.split(r"\b(?:но|однако|зато)\b", prefix, flags=re.I)[-1]
    qualifiers = list(_UNCERTAIN.finditer(prefix))
    if not qualifiers:
        return False
    # A modal qualifies its own predicate, not an independent coordinated one.
    # An introductory uncertainty marker can include a nested if/when premise.
    tail = re.sub(r"^\s*,\s*", "", prefix[qualifiers[-1].end():])
    if re.fullmatch(r"может|могут|могла\s+бы", qualifiers[-1].group(), re.I):
        if re.search(r"\b(?:и|а)\b", tail, re.I):
            return False
    tail = re.sub(r"^\s*(?:если|когда)\b[^,;:—]+,\s*", "", tail, flags=re.I)
    return not re.search(r"[,;:—]", tail)


def _conditional_premise(prefix: str) -> bool:
    return bool(re.search(r"\b(?:если|когда)\b", re.split(r"[,—:]", prefix)[-1], re.I))


def _denied_guarantee(text: str, claim: re.Match[str]) -> bool:
    # Exempt only the proposition inside the explicit denial, not a later
    # assertion in the same sentence or an unrelated use of "не могу".
    for pattern in _DENIED_GUARANTEES:
        for denial in pattern.finditer(text):
            start, end = denial.span("claim")
            if start <= claim.start() and claim.end() <= end:
                if not re.search(r"\b(?:но|однако|зато|а)\b", text[start:claim.start()], re.I):
                    return True
    return False


def _cache_condition(text: str) -> bool:
    text = re.split(r"\b(?:но|однако|зато)\b", text, flags=re.I)[-1]
    condition = re.search(r"(?:если|когда|после|при\s+условии).{0,180}"
                          r"(?:получ|загруж|выгруж|сохран)\w*.{0,35}(?:в\s+кэш|кэш)", text, re.I)
    if not condition or re.search(r"\bне\s+(?:получ|загруж|выгруж|сохран)", condition.group(), re.I):
        return False
    if re.search(r"инструмент(?:\s+(?:get_?activity_?structure|уже|успешно)){0,3}\s+"
                 r"(?:вернул|верн[её]т|подтвер\w*)\s+"
                 r"(?:отрезки|интервалы|наличие\s+(?:отрезков|интервалов)|непустую\s+структуру)\b", text, re.I):
        return True
    for status in re.finditer(r"structure_?status\s*=\s*structured\b", text, re.I):
        prefix = re.split(r"[,;]|\b(?:и|а)\b", text[:status.start()], flags=re.I)[-1]
        if not re.search(r"\bне\b", prefix, re.I) and not re.match(r"\s+не\b", text[status.end():], re.I):
            return True
    return False


def _activity_scope(text: str, records: list[Mapping[str, Any]],
                    inherited: list[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], bool]:
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}\.\d{2}(?:\.\d{4})?\b", text)
    ids = re.findall(r"activity_?id\s*[:=]\s*([\w-]+)", text)
    explicit_ids = [row["activity_id"] for row in records if not row["activity_id"].isdecimal()
                    and re.search(rf"(?<![\w-]){re.escape(row['activity_id'])}(?![\w-])", text)]
    if not (dates or ids or explicit_ids):
        return inherited, False
    return [row for row in records if
            (not dates or row["date"] in dates or date.fromisoformat(row["date"]).strftime("%d.%m") in dates
             or date.fromisoformat(row["date"]).strftime("%d.%m.%Y") in dates)
            and (not ids or row["activity_id"].replace("_", "") in [item.replace("_", "") for item in ids])
            and (not explicit_ids or row["activity_id"] in explicit_ids)], True


def activity_claim_unsupported(text: str, records: list[Mapping[str, Any]], *, attempted: bool = False) -> bool:
    """Recognize saved assurance/absence forms with activity/date scoped proof."""
    if not records and not attempted:
        return False
    scope = records if len(records) == 1 else []
    activity_context = len(records) == 1
    for clause in re.split(r"\n|;|(?<=[.!?])\s+", text):
        scope, explicit_scope = _activity_scope(clause, records, scope)
        if explicit_scope:
            activity_context = True
        local_activity = bool(_ACTIVITY.search(clause))
        if local_activity:
            activity_context = True
        for match in _FUTURE.finditer(clause):
            prefix = clause[:match.start()]
            if _qualified(prefix) or _conditional_premise(prefix) or _denied_guarantee(clause, match):
                continue
            is_confirmation = match.group().lower() in {"подтвердит", "докажет"}
            if is_confirmation:
                if _CHECK.search(clause) and (local_activity or activity_context) and re.search(r"карточк|отрезк|интервал|активност", clause, re.I):
                    return True
            elif (local_activity or (activity_context and re.search(r"\b(?:она|они)\b", clause, re.I))) and not _cache_condition(clause):
                return True
        if (_NAMING.search(clause) and local_activity
                and re.search(r"запрос|синхронизац|карточк|тогда", clause, re.I)
                and not (scope and all(row["structure_status"] == "structured" for row in scope)
                         and not re.search(r"повтор|после|когда|если|синхронизац|открыти|тогда", clause, re.I))
                and not _qualified(clause[:_NAMING.search(clause).start()]) and not _cache_condition(clause)):
            if not _denied_guarantee(clause, _NAMING.search(clause)):
                return True
        for match in _REAL_ABSENCE.finditer(clause):
            if not _qualified(clause[:match.start()]) and not _conditional_premise(clause[:match.start()]):
                return True
        for match in _POSITIVE_STRUCTURE.finditer(clause):
            # Bind only this matched claim to its contrasting proposition's
            # source and identity; later dates/plan facts cannot taint it.
            boundaries = list(_CONTRAST.finditer(clause))
            start = max((item.end() for item in boundaries if item.end() <= match.start()), default=0)
            end = min((item.start() for item in boundaries if item.start() >= match.end()), default=len(clause))
            sources = list(_CLAIM_SOURCE.finditer(clause[start:match.end()]))
            if sources and sources[-1].lastgroup == "plan":
                continue
            claim_scope, _ = _activity_scope(clause[start:end], records, scope)
            if claim_scope and all(row["structure_status"] == "structured" for row in claim_scope):
                continue
            prefix = clause[start:match.start()]
            if not (_qualified(prefix) or _conditional_premise(prefix) or re.search(r"\bне\s*$", prefix, re.I)):
                return True
        if not scope or any(row["structure_status"] != "structured" for row in scope):
            for match in _EFFORT.finditer(clause):
                if not _qualified(clause[:match.start()]) and not _conditional_premise(clause[:match.start()]):
                    return True
        for match in _ANALYZER_EMPTY.finditer(clause):
            prefix = clause[:match.start()]
            if not (_qualified(prefix) or _conditional_premise(prefix)):
                if not scope or any(row["structure_status"] != "empty" for row in scope):
                    return True
        for match in _ABSENCE.finditer(clause):
            prefix = clause[:match.start()]
            if _qualified(prefix) or re.search(r"\bесли\b", prefix, re.I):
                continue
            if re.search(r"кэш", prefix[-60:], re.I) or re.match(r"\s+в\s+кэш", clause[match.end():], re.I):
                continue
            if not scope or any(row["structure_status"] != "empty" for row in scope):
                return True
    return False


def activity_factual_bullets(records: list[Mapping[str, Any]]) -> list[str]:
    """Safe, bounded facts from allowlisted evidence, never from model prose."""
    lines = ["- Проверка может подтвердить или опровергнуть гипотезу; её результат заранее неизвестен."]
    if not records:
        lines.append("- Структура активности недоступна: нет подтверждённых данных для ответа.")
    for row in records[:6]:
        summary = []
        for key, unit in (("duration_minutes", "мин"), ("distance_km", "км"), ("tss", "TSS")):
            if key in row:
                summary.append(f"{row[key]:g} {unit}")
        label = f"- Активность за {row['date']}"
        if summary:
            label += f" ({', '.join(summary)})"
        status = row["structure_status"]
        if status == "unavailable":
            lines.append(label + ": структура недоступна. Данных недостаточно, чтобы назвать отрезки.")
        elif status == "empty":
            lines.append(label + ": анализ сохранённых данных не выявил отрезков.")
        else:
            lines.append(label + f": в кэше сохранено отрезков: {row['interval_count']}.")
            for index, interval in enumerate(row["intervals"][:12], start=1):
                facts = [f"{interval[key]:g} {unit}" for key, unit in
                         (("duration_seconds", "с"), ("avg_watts", "Вт"), ("distance_km", "км")) if key in interval]
                lines.append(f"  Отрезок {index}: " + ", ".join(facts))
    return lines
