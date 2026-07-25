"""Общие входные контракты планирования для service/API/web-потоков."""
from __future__ import annotations

PLANNING_MODES = ("event_goal", "training_goal", "manual")
PLANNING_INTENTS = ("maintain", "develop")

# English (API) → internal Russian labels used by the planner.
GOAL_TYPE_MAP = {
    "triathlon": "Триатлон",
    "tri": "Триатлон",
    "run": "Бег",
    "running": "Бег",
    "bike": "Вело",
    "cycling": "Вело",
    "cycle": "Вело",
}
DISTANCE_MAP = {
    # triathlon
    "sprint": "Спринт",
    "olympic": "Олимпийка",
    "half": "Half (70.3)",
    "70.3": "Half (70.3)",
    "ironman": "Ironman",
    "full": "Ironman",
    # run
    "5k": "5 км",
    "10k": "10 км",
    "half_marathon": "Полумарафон",
    "marathon": "Марафон",
    "ultra": "Ультра",
    # bike
    "40k_tt": "40 км TT",
    "100k": "100 км",
    "100mi": "100 миль",
    "brevet": "200 км (бревет)",
    "stage_race": "Этапная гонка",
}
DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

MIN_AVAILABLE_HOURS = 3.0
MAX_AVAILABLE_HOURS = 20.0
MIN_HORIZON_WEEKS = 1
MAX_HORIZON_WEEKS = 52

__all__ = [
    "DAY_MAP",
    "DISTANCE_MAP",
    "GOAL_TYPE_MAP",
    "MAX_AVAILABLE_HOURS",
    "MAX_HORIZON_WEEKS",
    "MIN_AVAILABLE_HOURS",
    "MIN_HORIZON_WEEKS",
    "PLANNING_INTENTS",
    "PLANNING_MODES",
]
