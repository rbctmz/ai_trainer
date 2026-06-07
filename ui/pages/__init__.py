"""Page renderers for the Streamlit UI."""

from .admin import render_data_management_page, render_sync_logs_page
from .activities import render_activities_page
from .ai_coaching import render_ai_coaching_page
from .dashboard import render_dashboard_page
from .hrv import render_hrv_page
from .sleep import render_sleep_page
from .welcome import render_welcome_page

__all__ = [
    "render_activities_page",
    "render_ai_coaching_page",
    "render_data_management_page",
    "render_dashboard_page",
    "render_hrv_page",
    "render_sleep_page",
    "render_sync_logs_page",
    "render_welcome_page",
]
