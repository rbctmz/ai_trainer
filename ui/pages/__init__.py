"""Page renderers for the Streamlit UI."""

from .admin import render_data_management_page, render_sync_logs_page
from .activities import render_activities_page
from .dashboard import render_dashboard_page
from .welcome import render_welcome_page

__all__ = [
    "render_activities_page",
    "render_data_management_page",
    "render_dashboard_page",
    "render_sync_logs_page",
    "render_welcome_page",
]
