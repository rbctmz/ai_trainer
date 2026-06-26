"""Lazy page exports for the Streamlit UI package."""


def render_data_management_page(*args, **kwargs):
    from .admin import render_data_management_page as impl

    return impl(*args, **kwargs)


def render_sync_logs_page(*args, **kwargs):
    from .admin import render_sync_logs_page as impl

    return impl(*args, **kwargs)


def render_activities_page(*args, **kwargs):
    from .activities import render_activities_page as impl

    return impl(*args, **kwargs)


def render_ai_coaching_page(*args, **kwargs):
    from .ai_coaching import render_ai_coaching_page as impl

    return impl(*args, **kwargs)


def render_dashboard_page(*args, **kwargs):
    from .dashboard import render_dashboard_page as impl

    return impl(*args, **kwargs)


def render_hrv_page(*args, **kwargs):
    from .hrv import render_hrv_page as impl

    return impl(*args, **kwargs)


def render_planning_page(*args, **kwargs):
    from .planning import render_planning_page as impl

    return impl(*args, **kwargs)


def render_sleep_page(*args, **kwargs):
    from .sleep import render_sleep_page as impl

    return impl(*args, **kwargs)


def render_welcome_page(*args, **kwargs):
    from .welcome import render_welcome_page as impl

    return impl(*args, **kwargs)


__all__ = [
    "render_activities_page",
    "render_ai_coaching_page",
    "render_data_management_page",
    "render_dashboard_page",
    "render_hrv_page",
    "render_planning_page",
    "render_sleep_page",
    "render_sync_logs_page",
    "render_welcome_page",
]
