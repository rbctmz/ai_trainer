"""State schema definitions for the Streamlit app."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class UIState:
    """Visual and navigation preferences."""
    dark_mode: bool = False
    selected_page: str = "📊 Дашборд"
    confirm_clear: bool = False
    sidebar_expanded: bool = True


@dataclass
class IntegrationState:
    """External integrations and connection-related flags."""
    garmin_authenticated: bool = False
    demo_mode: bool = False
    last_sync_status: Optional[Dict[str, Any]] = None
    syncing_in_progress: bool = False


@dataclass
class DataState:
    """Cached datasets and computed outputs."""
    activities_range_days: int = 30
    hrv_range_days: int = 90
    sleep_range_days: int = 7
    cache: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppState:
    """Top-level container for app state slices."""
    ui: UIState = field(default_factory=UIState)
    integrations: IntegrationState = field(default_factory=IntegrationState)
    data: DataState = field(default_factory=DataState)


__all__ = ["AppState", "UIState", "IntegrationState", "DataState"]
