"""ACWR (acute:chronic workload ratio) поверх дневных EWMA.

Формула: ``ACWR = ATL / CTL``, где ATL и CTL — дневные экспоненциальные
средние нагрузки (Williams et al. 2017, EWMA-вариант). Пороги и статусы —
Gabbett 2016 (``0.8 / 1.3 / 1.5``).

Модуль намеренно чистый: никакого I/O, БД и сети. EWMA-константы берутся из
``models/banister.py``, чтобы не держать вторую копию чисел: ATL/CTL уже
считаются там для TSB, и ACWR обязан использовать ровно те же средние.

Issue #608: публичная шкала описывает положение относительно базы атлета
(``below_baseline`` / ``expected_band`` / ``elevated`` / ``strongly_elevated``),
а не риск: отношение острой нагрузки к хронической не устанавливает вероятность
травмы. Прежний словарь провайдера принимается только на входе шимом
совместимости и наружу не выходит.

Guard'ы важнее точности: при малой хронической нагрузке отношение взрывается
(CTL=1, ATL=3 -> ACWR 3.0 при мизерных абсолютных объёмах), поэтому вместо
ложной тревоги возвращается ``None``.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from models.banister import BanisterModel


# --- Пороги ---------------------------------------------------------------
#: Числа не меняются (non-goal #608) — переименованы только идентификаторы,
#: чтобы в модуле не оставалось риск-лексики вне шима совместимости.
ACWR_BELOW_BASELINE_THRESHOLD = 0.8
ACWR_EXPECTED_BAND_MAX = 1.3
ACWR_ELEVATED_MAX = 1.5

# --- Guard'ы -------------------------------------------------------------

#: Ниже этой хронической нагрузки отношение не интерпретируется.
ACWR_MIN_CHRONIC_LOAD = 5.0
#: Короче этого окна хроническая база не набрана, и отношение завышено.
#:
#: ATL (tau=7) выходит на плато примерно за три недели, а CTL (tau=42) отстаёт
#: структурно: на ровной нагрузке с нуля знаменатель отношения меньше
#: числителя просто потому, что среднее ещё не сошлось. Замеры на постоянных
#: 50 TSS/день при холодном старте:
#:
#:   42 дня  -> CTL 31.6, ACWR 1.58 (high_risk)   <- артефакт старта
#:   63 дня  -> CTL 38.8, ACWR 1.29 (optimal)
#:   84 дня  -> CTL 43.2, ACWR 1.16 (optimal)
#:  168 дней -> CTL 49.1, ACWR 1.02 (optimal)
#:
#: 84 дня = 2 x tau_CTL — точка, после которой ложная тревога на ровной
#: нагрузке не возникает, а реальная перегрузка (90 дней базы + 14 дней
#: удвоения) по-прежнему детектируется как high_risk. Совпадает с обычной
#: практикой: ACWR показывают атлету не раньше 8-12 недель истории.
ACWR_MIN_HISTORY_DAYS = 84

# --- Причины отказа ------------------------------------------------------

ACWR_REASON_SHORT_HISTORY = "insufficient_history"
ACWR_REASON_LOW_CHRONIC_LOAD = "chronic_load_too_low"

# --- Представление -------------------------------------------------------

#: Описательная шкала относительно базы атлета (issue #608).
ACWR_STATUS_BELOW_BASELINE = "below_baseline"
ACWR_STATUS_EXPECTED_BAND = "expected_band"
ACWR_STATUS_ELEVATED = "elevated"
ACWR_STATUS_STRONGLY_ELEVATED = "strongly_elevated"

#: Статус -> тон. Тон совместим с тонами signals_engine; это визуальный вес,
#: а не утверждение о здоровье.
ACWR_STATUS_TONE: dict[str, str] = {
    ACWR_STATUS_BELOW_BASELINE: "neutral",
    ACWR_STATUS_EXPECTED_BAND: "success",
    ACWR_STATUS_ELEVATED: "warning",
    ACWR_STATUS_STRONGLY_ELEVATED: "danger",
}

ACWR_STATUS_LABEL: dict[str, str] = {
    ACWR_STATUS_BELOW_BASELINE: "Ниже обычной базы",
    ACWR_STATUS_EXPECTED_BAND: "В пределах обычного",
    ACWR_STATUS_ELEVATED: "Повышенная нагрузка",
    ACWR_STATUS_STRONGLY_ELEVATED: "Значительно выше базы",
}

ACWR_STATUS_SEVERITY: dict[str, int] = {
    ACWR_STATUS_BELOW_BASELINE: 0,
    ACWR_STATUS_EXPECTED_BAND: 0,
    ACWR_STATUS_ELEVATED: 2,
    ACWR_STATUS_STRONGLY_ELEVATED: 3,
}

#: Порядок статусов для направления расхождения при сверке с провайдером.
#: Отдельно от ``ACWR_STATUS_SEVERITY``: там нижние две зоны намеренно одного
#: уровня, и по нему нельзя отличить нагрузку ниже базы от ожидаемого диапазона.
ACWR_STATUS_ORDER: dict[str, int] = {
    ACWR_STATUS_BELOW_BASELINE: 0,
    ACWR_STATUS_EXPECTED_BAND: 1,
    ACWR_STATUS_ELEVATED: 2,
    ACWR_STATUS_STRONGLY_ELEVATED: 3,
}

#: Провайдер (Intervals.icu) присылает прежний риск-словарь. Шим отображает его
#: в публичную шкалу **на входе**; наружу прежнее значение не выходит, иначе
#: риск-лексика возвращалась бы в DTO в обход acceptance criteria #608.
ACWR_PROVIDER_LEGACY_STATUS: dict[str, str] = {
    "safe": ACWR_STATUS_BELOW_BASELINE,
    "optimal": ACWR_STATUS_EXPECTED_BAND,
    "moderate_risk": ACWR_STATUS_ELEVATED,
    "high_risk": ACWR_STATUS_STRONGLY_ELEVATED,
}

#: Версия математики: формула, окна, пороги. Слайс #608 её не меняет.
ACWR_CALCULATION_VERSION = "acwr-ewma-v1"
#: Версия публичной интерпретации: словарь статусов и оговорка.
ACWR_SEMANTICS_VERSION = "descriptive-v2"

#: Постоянные времени обеих EWMA. Одного «окна» мало: модель экспоненциальная,
#: и без постоянных покрытие неоднозначно (issue #608).
_ACWR_TAU = BanisterModel()
ACWR_ACUTE_TAU_DAYS = int(_ACWR_TAU.tau2)
ACWR_CHRONIC_TAU_DAYS = int(_ACWR_TAU.tau1)

#: Постоянная оговорка о природе показателя.
ACWR_LIMITATION = (
    "ACWR — отношение острой нагрузки к хронической: описательный контекст "
    "относительно обычной базы атлета, а не прогноз травмы и не медицинская оценка."
)

#: Вердикт сверки нашего значения с провайдерским.
CROSS_CHECK_MATCH = "match"
CROSS_CHECK_MORE_ACUTE = "more_acute"
CROSS_CHECK_LESS_ACUTE = "less_acute"
CROSS_CHECK_NO_PROVIDER = "no_provider_value"
CROSS_CHECK_INSUFFICIENT = "insufficient_data"


def _safe_float(value: Any) -> float:
    """Привести значение к float; нечисловое и не-конечное считаем отсутствием нагрузки.

    ``NaN`` отвергался и раньше, но ``+inf`` проходил дальше: он утекал в EWMA,
    превращал отношение в ``NaN`` и валил сериализацию ответа FastAPI
    (``Out of range float values are not JSON compliant``) — то есть одно битое
    значение провайдера давало HTTP 500 на дашборде и в планировании.
    """
    try:
        if value is None:
            return 0.0
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):  # NaN, +inf, -inf
        return 0.0
    return numeric


def _alphas() -> tuple[float, float]:
    """EWMA-константы из канонической модели, без дублирования чисел."""
    model = BanisterModel()
    ctl_alpha = 1.0 - math.exp(-1.0 / model.tau1)
    atl_alpha = 1.0 - math.exp(-1.0 / model.tau2)
    return ctl_alpha, atl_alpha


def acwr_series(daily_load: Sequence[Any] | None) -> list[dict[str, float]]:
    """Дневной ряд ATL/CTL/ACWR по последовательности дневной нагрузки.

    ``daily_load`` — нагрузка за каждый день окна, включая нулевые дни отдыха,
    от самого старого к самому свежему. Пропущенные дни должны быть нулями:
    именно нули обеспечивают спад хронической нагрузки.

    Возвращает список той же длины, что и вход.
    """
    if not daily_load:
        return []

    ctl_alpha, atl_alpha = _alphas()
    ctl = 0.0
    atl = 0.0
    series: list[dict[str, float]] = []

    for raw in daily_load:
        load = _safe_float(raw)
        ctl = ctl_alpha * load + (1.0 - ctl_alpha) * ctl
        atl = atl_alpha * load + (1.0 - atl_alpha) * atl
        ratio = (atl / ctl) if ctl > 0 else 0.0
        series.append({"atl": atl, "ctl": ctl, "acwr": ratio})

    return series


def classify_acwr(ratio: float) -> str:
    """Описательная зона относительно базы атлета (issue #608).

    Пороги 0.8 / 1.3 / 1.5 не меняются: это non-goal #608, переименована только
    интерпретация. Классификация односторонняя по возрастанию: нижняя граница
    диапазона принадлежит этому диапазону, поэтому ``0.8`` — уже
    ``expected_band``.
    """
    if ratio < ACWR_BELOW_BASELINE_THRESHOLD:
        return ACWR_STATUS_BELOW_BASELINE
    if ratio < ACWR_EXPECTED_BAND_MAX:
        return ACWR_STATUS_EXPECTED_BAND
    if ratio < ACWR_ELEVATED_MAX:
        return ACWR_STATUS_ELEVATED
    return ACWR_STATUS_STRONGLY_ELEVATED


def _normalize_status(value: Any) -> str | None:
    """Привести статус к публичной шкале или вернуть None.

    Принимает и наш словарь, и прежний словарь провайдера: Intervals.icu
    по-прежнему присылает ``safe`` / ``optimal`` / ``moderate_risk`` /
    ``high_risk``. Отображение происходит **на входе**, поэтому наружу старое
    значение не выходит (issue #608).
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in ACWR_STATUS_TONE:
        return text
    return ACWR_PROVIDER_LEGACY_STATUS.get(text)


def compare_with_provider_status(
    local_status: str | None,
    provider_status: Any,
) -> str:
    """Сверить наш статус со значением из провайдера.

    Сверка не подменяет наш результат: она лишь говорит, в какую сторону
    расходятся оценки, чтобы расхождение было видно в диагностике.
    """
    provider = _normalize_status(provider_status)
    local = _normalize_status(local_status)

    if local is None:
        return CROSS_CHECK_INSUFFICIENT
    if provider is None:
        return CROSS_CHECK_NO_PROVIDER

    # Сначала точное равенство: по уровням severity ``safe`` и ``optimal``
    # неразличимы, поэтому прежняя проверка объявляла совпадением даже пару
    # «недостаточная нагрузка» ↔ «оптимальная зона».
    if local == provider:
        return CROSS_CHECK_MATCH

    if ACWR_STATUS_ORDER[local] > ACWR_STATUS_ORDER[provider]:
        return CROSS_CHECK_MORE_ACUTE
    return CROSS_CHECK_LESS_ACUTE


def effective_chronic_load(daily_load: Sequence[Any]) -> float:
    """Установившаяся хроническая нагрузка окна такой длины.

    ``tss_mean * (1 - exp(-n / tau_CTL))`` — уровень, к которому CTL сходится
    на данном окне. Именно он, а не последнее значение CTL, показывает,
    набрана ли хроническая база, при которой отношение осмысленно.
    """
    if not daily_load:
        return 0.0
    model = BanisterModel()
    decay = 1.0 - math.exp(-len(daily_load) / model.tau1)
    mean_load = sum(_safe_float(item) for item in daily_load) / len(daily_load)
    return mean_load * decay


def acwr_signal(
    daily_load: Sequence[Any] | None,
    *,
    provider_status: Any = None,
) -> dict[str, Any]:
    """Сигнал ACWR для окна дневной нагрузки.

    Возвращает словарь с ``value``/``status`` (``None`` при срабатывании
    guard'а), причиной отказа и вердиктом сверки с провайдером.
    """
    daily = list(daily_load or [])
    history_days = len(daily)
    provider_normalized = _normalize_status(provider_status)

    def _empty(reason: str | None, atl: float = 0.0, ctl: float = 0.0) -> dict[str, Any]:
        return {
            "value": None,
            "percent": None,
            "status": None,
            "tone": None,
            "label": None,
            "severity": None,
            "atl": round(atl, 1),
            "ctl": round(ctl, 1),
            "history_days": history_days,
            "reason": reason,
            "cross_check": compare_with_provider_status(None, provider_normalized),
            "provider_status": provider_normalized,
            "acute_tau_days": ACWR_ACUTE_TAU_DAYS,
            "chronic_tau_days": ACWR_CHRONIC_TAU_DAYS,
            "calculation_version": ACWR_CALCULATION_VERSION,
            "semantics_version": ACWR_SEMANTICS_VERSION,
            "limitation": ACWR_LIMITATION,
            #: ACWR-единственный вход не даёт права на предписывающее вмешательство:
            #: для него нужны свежие corroborating evidence (issue #608).
            "intervention_eligible": False,
        }

    # Один проход EWMA на весь сигнал: guard и значение обязаны читать одну
    # и ту же серию, иначе они разойдутся при правке модели.
    series = acwr_series(daily)
    if series:
        atl = series[-1]["atl"]
        ctl = series[-1]["ctl"]
    else:
        atl = ctl = 0.0

    if history_days < ACWR_MIN_HISTORY_DAYS:
        return _empty(ACWR_REASON_SHORT_HISTORY, atl, ctl)

    # Гейт по текущей CTL, а не только по средней нагрузке окна: после долгого
    # простоя (14 дней по 50 TSS, затем 70 дней отдыха) установившаяся оценка
    # окна остаётся выше порога, хотя текущая CTL уже упала до 2.7 — и детрени-
    # рованный атлет получал уверенный ``safe`` вместо отказа по низкой базе.
    if ctl < ACWR_MIN_CHRONIC_LOAD or effective_chronic_load(daily) < ACWR_MIN_CHRONIC_LOAD:
        return _empty(ACWR_REASON_LOW_CHRONIC_LOAD, atl, ctl)

    ratio = atl / ctl
    # Статус и публикуемое значение берутся из одного представления: раньше
    # классификация шла по неокруглённому отношению, а ``value`` округлялось до
    # двух знаков, поэтому наружу могло уйти ``value=1.3`` со статусом
    # ``optimal``, хотя ``classify_acwr(1.3)`` — уже ``moderate_risk``.
    value = round(ratio, 2)
    status = classify_acwr(value)

    return {
        "value": value,
        "percent": round(value * 100, 1),
        "status": status,
        "tone": ACWR_STATUS_TONE[status],
        "label": ACWR_STATUS_LABEL[status],
        "severity": ACWR_STATUS_SEVERITY[status],
        "atl": round(atl, 1),
        "ctl": round(ctl, 1),
        "history_days": history_days,
        "reason": None,
        "cross_check": compare_with_provider_status(status, provider_normalized),
        "provider_status": provider_normalized,
        "acute_tau_days": ACWR_ACUTE_TAU_DAYS,
        "chronic_tau_days": ACWR_CHRONIC_TAU_DAYS,
        "calculation_version": ACWR_CALCULATION_VERSION,
        "semantics_version": ACWR_SEMANTICS_VERSION,
        "limitation": ACWR_LIMITATION,
        #: ACWR-единственный вход не даёт права на предписывающее вмешательство:
        #: для него нужны свежие corroborating evidence (issue #608).
        "intervention_eligible": False,
    }


def provider_status_from_training_status(training_status: Any) -> str | None:
    """Достать провайдерский ACWR-статус из ``training_status``.

    Значение приходит от Intervals.icu (``acwr_status``); оно используется
    только для сверки и никогда не подменяет локальный расчёт.
    """
    if training_status is None:
        return None

    if isinstance(training_status, Mapping):
        return _normalize_status(training_status.get("acwr_status"))

    try:
        import pandas as pd  # локальный импорт: модуль остаётся чистым без pandas

        if isinstance(training_status, pd.DataFrame):
            if training_status.empty or "acwr_status" not in training_status.columns:
                return None
            frame = training_status
            if "date" in frame.columns:
                frame = frame.sort_values("date")
            for value in reversed(frame["acwr_status"].tolist()):
                normalized = _normalize_status(value)
                if normalized is not None:
                    return normalized
            return None
    except Exception:
        return None

    return _normalize_status(getattr(training_status, "acwr_status", None))
