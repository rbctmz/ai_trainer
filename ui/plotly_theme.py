"""Plotly chart theme helpers (extracted from the legacy ``ui/theme.py``).

These provide the dark/light color contract for charts independently of the
application theme engine, so the Material ``ui/theme.py`` could be removed
without breaking charts on activities / dashboard / hrv / sleep pages.
"""
from __future__ import annotations

from typing import Optional


def get_plotly_theme(dark_mode: Optional[bool] = None):
    """Получение темы для графиков Plotly"""
    if dark_mode is None:
        from state import get_state_manager

        dark_mode = get_state_manager().dark_mode
    if dark_mode:
        return {
            # Aligned to the cockpit palette in utils/modern_ui.py (--ic-*).
            'template': 'plotly_dark',
            'paper_bgcolor': '#101411',  # --ic-bg
            'plot_bgcolor': '#19221D',   # --ic-surface
            'font_color': '#F4F0E7',     # --ic-ink
            'gridcolor': 'rgba(244,240,231,0.12)',  # --ic-hairline
        }
    else:
        return {
            'template': 'plotly_white',
            'paper_bgcolor': '#FFFDF7',  # --ic-surface (light)
            'plot_bgcolor': '#FFFDF7',
            'font_color': '#18251F',     # --ic-ink (light)
            'gridcolor': 'rgba(24,37,31,0.12)',  # --ic-hairline (light)
        }


def create_dark_table_html(df, max_height=400):
    """Создает HTML таблицу для темной темы"""
    html_table = f"""
    <div style="background-color: #1E1E1E; border: 1px solid #2B2B2B; border-radius: 8px; padding: 10px; max-height: {max_height}px; overflow-y: auto;">
    <table style="width: 100%; color: #F5F5F5; border-collapse: collapse;">
    <thead>
    <tr style="background-color: #2B2B2B;">
    """

    # Добавляем заголовки
    for col in df.columns:
        html_table += f'<th style="padding: 8px; border: 1px solid #2B2B2B; color: #F5F5F5; font-weight: bold; text-align: left;">{col}</th>'
    html_table += "</tr></thead><tbody>"

    # Добавляем строки данных
    for idx, row in df.iterrows():
        bg_color = "#1A1A1A" if idx % 2 == 1 else "#1E1E1E"
        html_table += f'<tr style="background-color: {bg_color};">'
        for value in row:
            html_table += f'<td style="padding: 8px; border: 1px solid #2B2B2B; color: #F5F5F5;">{value}</td>'
        html_table += "</tr>"

    html_table += "</tbody></table></div>"
    return html_table


def apply_plotly_theme(fig, dark_mode: Optional[bool] = None):
    """Применяет тему к графику Plotly"""
    theme = get_plotly_theme(dark_mode)
    fig.update_layout(
        template=theme['template'],
        paper_bgcolor=theme['paper_bgcolor'],
        plot_bgcolor=theme['plot_bgcolor'],
        font=dict(color=theme['font_color']),
        xaxis=dict(gridcolor=theme['gridcolor']),
        yaxis=dict(gridcolor=theme['gridcolor'])
    )
    return fig


__all__ = [
    'apply_plotly_theme',
    'create_dark_table_html',
    'get_plotly_theme',
]
