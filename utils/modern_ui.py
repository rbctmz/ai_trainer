"""Улучшенные UI компоненты с полной поддержкой темной темы."""

import html
import textwrap

import streamlit as st
import plotly.graph_objects as go
from typing import Any, Dict, Optional, Sequence, Tuple

class ModernUI:
    """Современные UI компоненты для AI Trainer с улучшенной поддержкой тем"""
    
    # Цветовые схемы для светлой и темной тем
    LIGHT_THEME = {
        'primary_gradient': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'surface_white': '#FFFFFF',
        'surface_light': '#E8F0FF',
        'surface_dark': '#1A2B4D',
        'text_primary': '#1E293B',
        'text_secondary': '#64748B',
        'border_gray': '#E2E8F0',
        'bg_primary': '#F8FAFF',
        'metric_bg': '#FFFFFF',
        'metric_border': '#E2E8F0',
        'is_dark': False
    }
    
    DARK_THEME = {
        'primary_gradient': 'linear-gradient(135deg, #4C5FD5 0%, #5E3B8E 100%)',
        'surface_white': '#1E1E1E',
        'surface_light': '#2D2D2D',
        'surface_dark': '#0F172A',
        'text_primary': '#F5F5F5',
        'text_secondary': '#A0A0A0',
        'border_gray': '#2B2B2B',
        'bg_primary': '#121212',
        'metric_bg': '#1E1E1E',
        'metric_border': '#2B2B2B',
        'is_dark': True
    }
    
    @classmethod
    def get_theme(cls):
        """Получить текущую тему из session state"""
        return cls.DARK_THEME if st.session_state.get('dark_mode', False) else cls.LIGHT_THEME
    
    @staticmethod
    def apply_modern_styles(dark_mode=False):
        """Применяет современную CSS-стилизацию с полной поддержкой тем"""
        
        theme = ModernUI.DARK_THEME if dark_mode else ModernUI.LIGHT_THEME
        
        # CSS с динамическими значениями из темы
        css = f"""
        <style>
        /* Purposeful app typography. Manrope is the intended face; SF/Avenir are local fallbacks. */
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&display=swap');
        
        /* Переменные темы */
        :root {{
            --primary-gradient: {theme['primary_gradient']};
            --surface-white: {theme['surface_white']};
            --surface-light: {theme['surface_light']};
            --surface-dark: {theme['surface_dark']};
            --text-primary: {theme['text_primary']};
            --text-secondary: {theme['text_secondary']};
            --border-gray: {theme['border_gray']};
            --bg-primary: {theme['bg_primary']};
            --metric-bg: {theme['metric_bg']};
            --metric-border: {theme['metric_border']};
            
            /* Совместимость со старым кодом */
            --primary-blue: #667eea;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);

            /* Visual V2 cockpit palette */
            --ic-bg: {'#101411' if dark_mode else '#F3EFE6'};
            --ic-bg-soft: {'#151C18' if dark_mode else '#FBF7EE'};
            --ic-surface: {'#19221D' if dark_mode else '#FFFDF7'};
            --ic-surface-raised: {'#202B25' if dark_mode else '#FFFFFF'};
            --ic-ink: {'#F4F0E7' if dark_mode else '#18251F'};
            --ic-muted: {'#A7B4A9' if dark_mode else '#67736B'};
            --ic-hairline: {'rgba(244,240,231,0.12)' if dark_mode else 'rgba(24,37,31,0.12)'};
            --ic-green: #0D8F68;
            --ic-teal: #0F6F73;
            --ic-amber: #E6A01A;
            --ic-red: #C94B42;
            --ic-blue: #2E6FBB;
            --ic-shadow: {'0 20px 70px rgba(0,0,0,0.34)' if dark_mode else '0 22px 70px rgba(75,63,38,0.14)'};
            --ic-button-bg: {'rgba(255,255,255,0.055)' if dark_mode else '#FFFFFF'};
            --ic-button-hover: {'rgba(13,143,104,0.18)' if dark_mode else 'rgba(13,143,104,0.08)'};
            --ic-input-bg: {'#18231D' if dark_mode else '#FFFFFF'};
            --ic-sidebar-width: 300px;
            --ic-sidebar-bg: linear-gradient(180deg, {'#121A16' if dark_mode else '#EAE4D8'}, {'#101411' if dark_mode else '#F6F0E5'});
        }}
        
        /* Базовые стили приложения */
        .stApp {{
            font-family: 'Manrope', 'Avenir Next', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            background:
                radial-gradient(circle at 12% 8%, {'rgba(13,143,104,0.18)' if dark_mode else 'rgba(13,143,104,0.13)'}, transparent 34rem),
                radial-gradient(circle at 88% 2%, {'rgba(230,160,26,0.14)' if dark_mode else 'rgba(230,160,26,0.18)'}, transparent 30rem),
                linear-gradient(180deg, var(--ic-bg-soft), var(--ic-bg)) !important;
            color: {theme['text_primary']} !important;
        }}

        .block-container {{
            max-width: 1240px;
            padding-top: 2.1rem;
            padding-bottom: 5rem;
        }}

        #MainMenu,
        footer,
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        .stDeployButton {{
            display: none !important;
        }}

        header[data-testid="stHeader"] {{
            background: transparent !important;
            box-shadow: none !important;
        }}

        div[data-testid="stToolbar"] {{
            background: transparent !important;
            pointer-events: none !important;
        }}

        div[data-testid="stToolbar"] button:not([data-testid="stExpandSidebarButton"]),
        div[data-testid="stToolbar"] div[data-testid="stStatusWidget"],
        div[data-testid="stToolbar"] .stDeployButton {{
            display: none !important;
        }}

        div[data-testid="stToolbar"] button[data-testid="stExpandSidebarButton"] {{
            pointer-events: auto !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 2rem !important;
            height: 2rem !important;
            min-height: 2rem !important;
            border-radius: 999px !important;
            background: var(--ic-button-bg) !important;
            border: 1px solid var(--ic-hairline) !important;
            color: var(--ic-ink) !important;
            box-shadow: {'0 10px 28px rgba(0,0,0,0.18)' if dark_mode else '0 10px 28px rgba(75,63,38,0.10)'} !important;
        }}

        div[data-testid="stAlert"] {{
            border-radius: 20px !important;
            border: 1px solid var(--ic-hairline) !important;
            box-shadow: {'0 12px 34px rgba(0,0,0,0.12)' if dark_mode else '0 12px 34px rgba(76,63,38,0.08)'};
            overflow: hidden;
        }}
        
        /* Современные карточки */
        .modern-card {{
            background: {theme['metric_bg']} !important;
            border-radius: 16px;
            box-shadow: var(--shadow-sm);
            border: 1px solid {theme['metric_border']} !important;
            padding: 24px;
            margin-bottom: 16px;
            color: {theme['text_primary']} !important;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .modern-card:hover {{
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }}
        
        /* Метрические карточки */
        .metric-card {{
            background: {theme['metric_bg']} !important;
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow-sm);
            border: 1px solid {theme['metric_border']} !important;
            color: {theme['text_primary']} !important;
            height: 100%;
            transition: all 0.2s ease;
        }}
        
        .metric-card:hover {{
            box-shadow: var(--shadow-md);
        }}
        
        .metric-value {{
            font-size: 2.25rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
            color: {theme['text_primary']} !important;
        }}
        
        .metric-label {{
            font-size: 0.875rem;
            color: {theme['text_secondary']} !important;
            font-weight: 500;
            margin-bottom: 0.75rem;
        }}
        
        .metric-description {{
            font-size: 0.75rem;
            color: {theme['text_secondary']} !important;
        }}
        
        /* AI панель с адаптивным градиентом */
        .ai-panel {{
            background: {theme['primary_gradient']};
            border-radius: 20px;
            padding: 32px;
            color: white !important;
            margin: 24px 0;
            box-shadow: var(--shadow-lg);
        }}
        
        .ai-recommendation {{
            background: rgba(255, 255, 255, {'0.1' if dark_mode else '0.15'});
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
            backdrop-filter: blur(10px);
            color: white !important;
        }}
        
        /* Статус-карточки с цветными индикаторами */
        .status-card {{
            position: relative;
            overflow: hidden;
            background: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        .status-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}
        
        .status-excellent::before {{ background: var(--success-green); }}
        .status-good::before {{ background: var(--warning-yellow); }}
        .status-warning::before {{ background: var(--danger-red); }}
        .status-critical::before {{ background: #991B1B; }}
        
        /* Кнопки с адаптацией к теме. Streamlit меняет внутренние data-testid,
           поэтому держим и старый, и новый контракт селекторов. */
        .stButton > button,
        button[data-testid="stBaseButton-secondary"],
        button[data-testid="stBaseButton-tertiary"],
        button[data-testid="stBaseButton-minimal"] {{
            background: var(--ic-button-bg) !important;
            color: {theme['text_primary']} !important;
            border: 1px solid var(--ic-hairline) !important;
            border-radius: 14px !important;
            min-height: 2.75rem;
            box-shadow: none !important;
            font-weight: 750 !important;
            white-space: nowrap !important;
            transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
        }}
        
        .stButton > button:hover,
        button[data-testid="stBaseButton-secondary"]:hover,
        button[data-testid="stBaseButton-tertiary"]:hover,
        button[data-testid="stBaseButton-minimal"]:hover {{
            background: var(--ic-button-hover) !important;
            border-color: rgba(13,143,104,0.45) !important;
            transform: translateY(-1px);
        }}

        button[data-testid="stBaseButton-primary"],
        div[data-testid="stBaseButton-primary"] > button,
        .stButton > button[kind="primary"],
        button[kind="primary"] {{
            background: linear-gradient(135deg, var(--ic-green), #14C38E) !important;
            color: white !important;
            border-color: rgba(20,195,142,0.45) !important;
        }}

        .stButton > button *,
        button[data-testid="stBaseButton-secondary"] *,
        button[data-testid="stBaseButton-tertiary"] *,
        button[data-testid="stBaseButton-minimal"] * {{
            color: var(--ic-ink) !important;
        }}

        button[data-testid="stBaseButton-primary"] *,
        .stButton > button[kind="primary"] * {{
            color: white !important;
        }}
        
        /* Табы и селекторы */
        .stTabs [data-baseweb="tab"] {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: var(--primary-blue) !important;
            color: white !important;
        }}
        
        /* Поля ввода */
        .stTextInput > div > div > input,
        .stNumberInput input,
        .stDateInput input,
        .stSelectbox > div > div,
        .stTextArea > div > div > textarea,
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div {{
            background-color: var(--ic-input-bg) !important;
            color: {theme['text_primary']} !important;
            border: 1px solid var(--ic-hairline) !important;
            border-radius: 14px !important;
        }}

        div[data-baseweb="select"] span,
        div[data-baseweb="input"] input,
        .stTextInput input,
        .stNumberInput input,
        .stDateInput input,
        .stTextArea textarea {{
            color: var(--ic-ink) !important;
        }}

        div[data-baseweb="tag"] {{
            background: {'rgba(13,143,104,0.22)' if dark_mode else 'rgba(13,143,104,0.12)'} !important;
            color: var(--ic-ink) !important;
            border: 1px solid rgba(13,143,104,0.24) !important;
        }}

        /* Radio groups inherit native Streamlit theme colors aggressively.
           Keep page-mode and planning strategy labels readable on V2 surfaces. */
        div[data-testid="stRadio"],
        div[data-testid="stRadio"] > label,
        div[data-testid="stRadio"] label,
        div[data-testid="stRadio"] p,
        div[data-testid="stRadio"] span,
        div[role="radiogroup"],
        div[role="radiogroup"] label,
        div[role="radiogroup"] p,
        div[role="radiogroup"] span {{
            color: var(--ic-ink) !important;
        }}

        div[data-testid="stRadio"] [role="radio"],
        div[role="radiogroup"] [role="radio"] {{
            color: var(--ic-ink) !important;
        }}

        div[data-testid="stRadio"] svg,
        div[role="radiogroup"] svg {{
            color: var(--ic-ink) !important;
            fill: currentColor !important;
        }}
        
        /* Expander */
        .streamlit-expanderHeader {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}

        div[data-testid="stExpander"] {{
            background: {'rgba(255,255,255,0.035)' if dark_mode else 'rgba(255,253,247,0.58)'} !important;
            border: 1px solid var(--ic-hairline) !important;
            border-radius: 14px !important;
        }}

        div[data-testid="metric-container"] {{
            background:
                linear-gradient(180deg, {'rgba(255,255,255,0.045)' if dark_mode else 'rgba(255,255,255,0.92)'}, {'rgba(255,255,255,0.025)' if dark_mode else 'rgba(255,253,247,0.86)'}) !important;
            border: 1px solid var(--ic-hairline) !important;
            border-top: 3px solid var(--ic-teal) !important;
            border-radius: 20px !important;
            color: var(--ic-ink) !important;
            box-shadow: {'0 10px 30px rgba(0,0,0,0.13)' if dark_mode else '0 14px 34px rgba(76,63,38,0.08)'} !important;
            padding: 1rem !important;
        }}

        div[data-testid="metric-container"] * {{
            color: var(--ic-ink) !important;
        }}
        
        /* Dataframe */
        .dataframe {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background: var(--ic-sidebar-bg) !important;
            border-right: 1px solid var(--ic-hairline);
            color: var(--ic-ink) !important;
            box-shadow: {'18px 0 54px rgba(0,0,0,0.20)' if dark_mode else '18px 0 54px rgba(75,63,38,0.10)'} !important;
            z-index: 999991 !important;
        }}

        section[data-testid="stSidebar"] > div,
        div[data-testid="stSidebarContent"],
        div[data-testid="stSidebarUserContent"] {{
            background: transparent !important;
            color: var(--ic-ink) !important;
        }}

        div[data-testid="stSidebarContent"] {{
            background: var(--ic-sidebar-bg) !important;
            border-right: 1px solid var(--ic-hairline) !important;
            height: 100vh !important;
            min-height: 100vh !important;
            overflow-y: auto !important;
            padding: 0 0.78rem 1rem !important;
        }}

        div[data-testid="stSidebarUserContent"] {{
            padding: 0.75rem 0.45rem 1.2rem !important;
        }}

        section[data-testid="stSidebar"] *,
        div[data-testid="stSidebarContent"] *,
        div[data-testid="stSidebarUserContent"] * {{
            color: var(--ic-ink) !important;
        }}

        section[data-testid="stSidebar"] h1 {{
            color: var(--ic-ink) !important;
            font-size: 1.35rem !important;
            line-height: 1.08 !important;
            letter-spacing: -0.045em !important;
            margin-bottom: 0.25rem !important;
        }}

        section[data-testid="stSidebar"] .stButton > button {{
            background: {'rgba(255,255,255,0.05)' if dark_mode else 'rgba(255,255,255,0.74)'} !important;
        }}

        section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, var(--ic-green), #14C38E) !important;
        }}

        section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] *,
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] * {{
            color: white !important;
        }}

        div[data-testid="collapsedControl"],
        div[data-testid="stSidebarCollapseButton"] {{
            z-index: 999999 !important;
        }}

        div[data-testid="collapsedControl"] button,
        div[data-testid="stSidebarCollapseButton"] button {{
            background: var(--ic-button-bg) !important;
            border: 1px solid var(--ic-hairline) !important;
            color: var(--ic-ink) !important;
        }}

        /* Visual V2 app shell */
        .ic-app-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin: 0.25rem 0 1.35rem;
            padding: 0.82rem 1rem;
            border: 1px solid var(--ic-hairline);
            border-radius: 24px;
            background: {'rgba(25,34,29,0.72)' if dark_mode else 'rgba(255,253,247,0.74)'};
            backdrop-filter: blur(18px);
            box-shadow: var(--ic-shadow);
        }}

        .ic-brand-lockup {{
            display: flex;
            align-items: center;
            gap: 0.85rem;
        }}

        .ic-brand-mark {{
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 16px;
            color: white;
            font-weight: 900;
            background:
                radial-gradient(circle at 30% 20%, rgba(255,255,255,0.42), transparent 26px),
                linear-gradient(145deg, var(--ic-green), var(--ic-teal));
            box-shadow: 0 14px 34px rgba(13,143,104,0.28);
        }}

        .ic-brand-title {{
            margin: 0;
            color: var(--ic-ink);
            font-size: clamp(1.45rem, 2.2vw, 2.35rem);
            font-weight: 850;
            letter-spacing: -0.05em;
            line-height: 0.98;
        }}

        .ic-brand-subtitle,
        .ic-caption {{
            color: var(--ic-muted);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}

        .ic-sync-pill,
        .ic-kicker {{
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            width: fit-content;
            border-radius: 999px;
            padding: 0.42rem 0.72rem;
            background: {'rgba(13,143,104,0.16)' if dark_mode else 'rgba(13,143,104,0.10)'};
            color: var(--ic-green);
            border: 1px solid rgba(13,143,104,0.26);
            font-size: 0.72rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.09em;
        }}

        .ic-page-context {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 0.35rem 0 1.35rem;
            padding: 0.72rem 0.88rem;
            border: 1px solid var(--ic-hairline);
            border-radius: 18px;
            background: {'rgba(255,255,255,0.04)' if dark_mode else 'rgba(255,253,247,0.62)'};
            color: var(--ic-muted);
        }}

        .ic-page-hero {{
            position: relative;
            overflow: hidden;
            margin: 0.4rem 0 1.2rem;
            padding: clamp(1.25rem, 3vw, 2.1rem);
            border-radius: 30px;
            border: 1px solid var(--ic-hairline);
            background:
                radial-gradient(circle at 88% 18%, rgba(230,160,26,0.22), transparent 18rem),
                linear-gradient(135deg, {'#17221D' if dark_mode else '#FFFCF4'}, {'#20352C' if dark_mode else '#EDF7EE'});
            box-shadow: var(--ic-shadow);
        }}

        .ic-page-hero::after {{
            content: "";
            position: absolute;
            right: -4rem;
            bottom: -6rem;
            width: 18rem;
            height: 18rem;
            border-radius: 999px;
            border: 2.5rem solid rgba(13,143,104,0.08);
        }}

        .ic-page-title {{
            position: relative;
            z-index: 1;
            margin: 0.55rem 0 0.55rem;
            color: var(--ic-ink);
            font-size: clamp(2rem, 5vw, 4.5rem);
            font-weight: 900;
            line-height: 0.92;
            letter-spacing: -0.075em;
        }}

        .ic-page-subtitle {{
            position: relative;
            z-index: 1;
            max-width: 58rem;
            margin: 0;
            color: var(--ic-muted);
            font-size: clamp(0.95rem, 1.4vw, 1.12rem);
            line-height: 1.6;
            font-weight: 650;
        }}

        .ic-section-title {{
            margin: 1.45rem 0 0.7rem;
            color: var(--ic-ink);
            font-size: clamp(1.2rem, 2vw, 1.65rem);
            font-weight: 880;
            letter-spacing: -0.045em;
        }}

        .ic-section-caption {{
            margin: -0.35rem 0 0.75rem;
            color: var(--ic-muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }}

        .ic-card,
        .ic-stat-card,
        .ic-day-chip {{
            background:
                linear-gradient(180deg, {'rgba(255,255,255,0.045)' if dark_mode else 'rgba(255,255,255,0.92)'}, {'rgba(255,255,255,0.025)' if dark_mode else 'rgba(255,253,247,0.86)'});
            border: 1px solid var(--ic-hairline);
            border-radius: 24px;
            box-shadow: {'0 12px 38px rgba(0,0,0,0.16)' if dark_mode else '0 16px 42px rgba(76,63,38,0.09)'};
        }}

        .ic-card {{
            padding: 1.05rem;
            min-height: 100%;
        }}

        .ic-card-title {{
            margin: 0.25rem 0 0.35rem;
            color: var(--ic-ink);
            font-size: 1.15rem;
            font-weight: 850;
            letter-spacing: -0.035em;
        }}

        .ic-card-body {{
            margin: 0;
            color: var(--ic-muted);
            font-size: 0.88rem;
            line-height: 1.55;
            font-weight: 620;
        }}

        .ic-stat-card {{
            padding: 1rem;
            min-height: 8.5rem;
            border-top: 3px solid var(--tone, var(--ic-green));
        }}

        .ic-stat-label {{
            color: var(--ic-muted);
            font-size: 0.73rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }}

        .ic-stat-value {{
            margin: 0.42rem 0 0.35rem;
            color: var(--ic-ink);
            font-size: clamp(1.55rem, 3vw, 2.45rem);
            font-weight: 900;
            line-height: 0.95;
            letter-spacing: -0.065em;
        }}

        .ic-stat-caption {{
            color: var(--ic-muted);
            font-size: 0.78rem;
            line-height: 1.35;
            font-weight: 650;
        }}

        .ic-day-chip {{
            padding: 0.8rem 0.72rem;
            min-height: 8.6rem;
            border-radius: 20px;
            border-top: 3px solid var(--tone, var(--ic-hairline));
        }}

        .ic-day-date {{
            color: var(--ic-muted);
            font-size: 0.72rem;
            font-weight: 850;
        }}

        .ic-day-load {{
            margin: 0.55rem 0 0.25rem;
            color: var(--ic-ink);
            font-size: 1.25rem;
            font-weight: 900;
            letter-spacing: -0.05em;
        }}

        .ic-day-meta {{
            color: var(--ic-muted);
            font-size: 0.76rem;
            line-height: 1.35;
            font-weight: 650;
        }}

        .ic-timeline-bar {{
            height: 0.62rem;
            overflow: hidden;
            border-radius: 999px;
            background: {'rgba(255,255,255,0.08)' if dark_mode else 'rgba(24,37,31,0.10)'};
            margin: 0.85rem 0 0.4rem;
        }}

        .ic-timeline-fill {{
            height: 100%;
            width: var(--fill, 0%);
            border-radius: inherit;
            background: linear-gradient(90deg, var(--ic-green), var(--ic-amber));
        }}
        
        /* Быстрые действия */
        .quick-action-btn {{
            background: {theme['metric_bg']} !important;
            border: 2px solid {theme['border_gray']} !important;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-sm);
            color: {theme['text_primary']} !important;
        }}
        
        .quick-action-btn:hover {{
            border-color: var(--primary-blue) !important;
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }}
        
        /* Анимации */
        @keyframes slideIn {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .animate-slide-in {{
            animation: slideIn 0.3s ease-out;
        }}
        
        /* Адаптивность */
        @media (max-width: 768px) {{
            .modern-card {{
                padding: 16px;
                margin-bottom: 12px;
            }}
            
            .ai-panel {{
                padding: 20px;
                margin: 16px 0;
            }}
            
            .metric-value {{
                font-size: 1.75rem;
            }}

            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}

            .ic-app-header,
            .ic-page-context {{
                align-items: flex-start;
                flex-direction: column;
            }}

            .ic-day-chip {{
                min-height: 7rem;
            }}
        }}
        </style>
        """
        
        st.markdown(css, unsafe_allow_html=True)
    
    @staticmethod
    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        """Конвертация HEX цвета в строку RGBA с защитой от неверных значений."""
        alpha = max(0.0, min(1.0, alpha))
        if not hex_color:
            return f"rgba(59,130,246,{alpha})"
        value = hex_color.lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) != 6:
            return f"rgba(59,130,246,{alpha})"
        try:
            r = int(value[0:2], 16)
            g = int(value[2:4], 16)
            b = int(value[4:6], 16)
        except ValueError:
            return f"rgba(59,130,246,{alpha})"
        return f"rgba({r},{g},{b},{alpha})"
    
    @staticmethod
    def _clean_html(html: str) -> str:
        """Удаляет лишние отступы, чтобы Markdown не превращал HTML в код."""
        return textwrap.dedent(html).strip()

    @staticmethod
    def _escape_html(value: Any) -> str:
        """Escape values before rendering custom Visual V2 HTML."""
        return html.escape(str(value if value is not None else "—"), quote=True)

    @staticmethod
    def _tone_color(tone: str | None = None) -> str:
        """Map semantic tone names to Visual V2 CSS colors."""
        tones = {
            "success": "var(--ic-green)",
            "good": "var(--ic-green)",
            "neutral": "var(--ic-teal)",
            "info": "var(--ic-blue)",
            "warning": "var(--ic-amber)",
            "danger": "var(--ic-red)",
            "rest": "var(--ic-muted)",
            "planned": "var(--ic-green)",
            "done": "var(--ic-green)",
            "empty": "var(--ic-hairline)",
        }
        return tones.get(str(tone or "neutral"), "var(--ic-teal)")

    @staticmethod
    def render_app_header(
        title: str = "AI Trainer",
        subtitle: str = "Персональный тренировочный cockpit",
        status: str | None = None,
    ) -> None:
        """Render the compact app-level chrome used above navigation."""
        status_html = ""
        if status:
            status_html = (
                f"<div class='ic-sync-pill'>"
                f"<span>●</span><span>{ModernUI._escape_html(status)}</span>"
                f"</div>"
            )
        st.markdown(
            ModernUI._clean_html(
                f"""
                <div class="ic-app-header">
                    <div class="ic-brand-lockup">
                        <div class="ic-brand-mark">AI</div>
                        <div>
                            <div class="ic-brand-title">{ModernUI._escape_html(title)}</div>
                            <div class="ic-brand-subtitle">{ModernUI._escape_html(subtitle)}</div>
                        </div>
                    </div>
                    {status_html}
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    @staticmethod
    def render_page_hero(
        title: str,
        subtitle: str,
        eyebrow: str | None = None,
        meta: str | None = None,
    ) -> None:
        """Render a Visual V2 page hero."""
        eyebrow_html = f"<div class='ic-kicker'>{ModernUI._escape_html(eyebrow)}</div>" if eyebrow else ""
        meta_html = f"<div class='ic-caption' style='margin-top:0.85rem;'>{ModernUI._escape_html(meta)}</div>" if meta else ""
        st.markdown(
            ModernUI._clean_html(
                f"""
                <section class="ic-page-hero">
                    {eyebrow_html}
                    <h1 class="ic-page-title">{ModernUI._escape_html(title)}</h1>
                    <p class="ic-page-subtitle">{ModernUI._escape_html(subtitle)}</p>
                    {meta_html}
                </section>
                """
            ),
            unsafe_allow_html=True,
        )

    @staticmethod
    def render_section_title(title: str, caption: str | None = None) -> None:
        """Render a Visual V2 section title."""
        caption_html = f"<p class='ic-section-caption'>{ModernUI._escape_html(caption)}</p>" if caption else ""
        st.markdown(
            ModernUI._clean_html(
                f"""
                <div class="ic-section-title">{ModernUI._escape_html(title)}</div>
                {caption_html}
                """
            ),
            unsafe_allow_html=True,
        )

    @staticmethod
    def render_stat_card(
        label: str,
        value: Any,
        caption: str | None = None,
        tone: str | None = None,
    ) -> None:
        """Render one Visual V2 stat card."""
        caption_html = f"<div class='ic-stat-caption'>{ModernUI._escape_html(caption)}</div>" if caption else ""
        st.markdown(
            ModernUI._clean_html(
                f"""
                <div class="ic-stat-card" style="--tone:{ModernUI._tone_color(tone)};">
                    <div class="ic-stat-label">{ModernUI._escape_html(label)}</div>
                    <div class="ic-stat-value">{ModernUI._escape_html(value)}</div>
                    {caption_html}
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    @staticmethod
    def render_text_card(
        title: str,
        body: str,
        eyebrow: str | None = None,
        tone: str | None = None,
        footer: str | None = None,
    ) -> None:
        """Render a narrative Visual V2 card."""
        eyebrow_html = f"<div class='ic-kicker'>{ModernUI._escape_html(eyebrow)}</div>" if eyebrow else ""
        footer_html = f"<div class='ic-caption' style='margin-top:0.85rem;'>{ModernUI._escape_html(footer)}</div>" if footer else ""
        # Keep this as one HTML fragment. Streamlit Markdown can treat indented
        # nested block tags inside custom HTML as literal code text.
        card_html = (
            f'<div class="ic-card" style="border-top:3px solid {ModernUI._tone_color(tone)};">'
            f"{eyebrow_html}"
            f'<div class="ic-card-title">{ModernUI._escape_html(title)}</div>'
            f'<div class="ic-card-body">{ModernUI._escape_html(body)}</div>'
            f"{footer_html}"
            "</div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)

    @staticmethod
    def render_day_chip(
        label: str,
        load: str,
        meta: str,
        tone: str | None = None,
    ) -> None:
        """Render a compact Visual V2 day chip."""
        st.markdown(
            ModernUI._clean_html(
                f"""
                <div class="ic-day-chip" style="--tone:{ModernUI._tone_color(tone)};">
                    <div class="ic-day-date">{ModernUI._escape_html(label)}</div>
                    <div class="ic-day-load">{ModernUI._escape_html(load)}</div>
                    <div class="ic-day-meta">{ModernUI._escape_html(meta)}</div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )

    @staticmethod
    def training_status_card(
        title: str,
        status_text: str,
        status_color: str,
        metrics: Sequence[Tuple[str, str]],
        load_ratio: Optional[Dict[str, str]] = None,
        feedback: Optional[Sequence[str]] = None,
    ) -> None:
        """Визуализация статуса тренировки в фирменном стиле темы."""
        
        theme = ModernUI.get_theme()
        safe_color = status_color or theme["text_primary"]
        card_bg = theme["metric_bg"]
        text_primary = theme["text_primary"]
        text_secondary = theme["text_secondary"]
        border_color = theme["metric_border"]
        shadow_color = "rgba(15,23,42,0.12)" if not theme["is_dark"] else "rgba(0,0,0,0.35)"
        tile_bg_color = ModernUI._hex_to_rgba(
            theme["text_primary"], 0.08 if not theme["is_dark"] else 0.18
        )

        metrics_html_parts = []
        for label, value in metrics:
            metrics_html_parts.append(
                ModernUI._clean_html(
                    f"""
                    <div style="
                        display:flex;
                        justify-content:space-between;
                        align-items:flex-end;
                        gap:12px;
                        padding:10px 14px;
                        border-radius:10px;
                        background:{tile_bg_color};
                    ">
                        <span style="font-size:0.85rem; color:{text_secondary}; white-space:nowrap;">
                            {label}
                        </span>
                        <span style="font-size:0.95rem; color:{text_primary}; font-weight:600;">
                            {value}
                        </span>
                    </div>
                    """
                )
            )

        ratio_badge = ""
        if load_ratio:
            ratio_label = load_ratio.get("label", "Load ratio")
            ratio_value = load_ratio.get("value", "—")
            ratio_color = load_ratio.get("color") or safe_color
            ratio_suffix = load_ratio.get("suffix", "")
            ratio_detail = load_ratio.get("badge")
            ratio_secondary_parts = []
            if ratio_detail:
                ratio_secondary_parts.append(ratio_detail)
            if ratio_suffix:
                ratio_secondary_parts.append(ratio_suffix.strip())
            ratio_secondary = ""
            if ratio_secondary_parts:
                ratio_secondary = (
                    ModernUI._clean_html(
                        f"""
                        <div style='font-size:0.75rem; margin-top:2px; color:{ratio_color}; font-weight:500;'>
                            {' '.join(ratio_secondary_parts)}
                        </div>
                        """
                    )
                )
            metrics_html_parts.append(
                ModernUI._clean_html(
                    f"""
                    <div style="
                        display:flex;
                        justify-content:space-between;
                        align-items:flex-start;
                        gap:12px;
                        padding:10px 14px;
                        border-radius:10px;
                        background:{tile_bg_color};
                    ">
                        <span style="font-size:0.85rem; color:{text_secondary}; white-space:nowrap;">
                            {ratio_label}
                        </span>
                        <div style="text-align:right;">
                            <span style="font-size:0.95rem; color:{ratio_color}; font-weight:600;">
                                {ratio_value}
                            </span>
                            {ratio_secondary}
                        </div>
                    </div>
                    """
                )
            )
            ratio_badge = ratio_detail or ""
            ratio_badge_color = ratio_color
        else:
            ratio_badge_color = safe_color

        metrics_html = "".join(metrics_html_parts)

        feedback_html = ""
        if feedback:
            feedback_items = [
                ModernUI._clean_html(
                    f"<div style='font-size:0.8rem; color:{text_secondary}; line-height:1.45;'>{text}</div>"
                )
                for text in feedback
                if text
            ]
            if feedback_items:
                feedback_html = ModernUI._clean_html(
                    "<div style='margin-top:16px; display:flex; flex-direction:column; gap:6px;'>"
                    + "".join(feedback_items)
                    + "</div>"
                )

        badge_text = ratio_badge or status_text
        badge_bg = ModernUI._hex_to_rgba(
            ratio_badge_color, 0.12 if not theme["is_dark"] else 0.24
        )

        header_html = ModernUI._clean_html(
            f"""
            <div style="
                display:flex;
                align-items:center;
                justify-content:space-between;
                margin-bottom:16px;
            ">
                <div style="display:flex; align-items:center; gap:10px;">
                    <span style="
                        width:36px;
                        height:36px;
                        border-radius:12px;
                        background:{ModernUI._hex_to_rgba(safe_color, 0.18 if not theme['is_dark'] else 0.4)};
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                    ">
                        <span style="
                            width:10px;
                            height:10px;
                            border-radius:999px;
                            background:{safe_color};
                            display:inline-block;
                        "></span>
                    </span>
                    <span style="
                        font-size:0.82rem;
                        font-weight:600;
                        letter-spacing:0.08em;
                        text-transform:uppercase;
                        color:{text_secondary};
                    ">{title}</span>
                </div>
                <span style="
                    padding:6px 14px;
                    border-radius:999px;
                    background:{badge_bg};
                    color:{ratio_badge_color};
                    font-size:0.78rem;
                    font-weight:600;
                ">{badge_text}</span>
            </div>
            """
        )

        status_html = ModernUI._clean_html(
            f"""
            <div style="
                font-size:1.8rem;
                font-weight:700;
                text-transform:uppercase;
                color:{safe_color};
                text-align:center;
                margin-bottom:18px;
            ">{status_text}</div>
            """
        )

        card_html = ModernUI._clean_html(
            f"""
            <div class="metric-card training-status-card" style="
                position:relative;
                background:{card_bg};
                border:1px solid {border_color};
                box-shadow:0 14px 28px -24px {shadow_color};
                padding:24px 22px;
            ">
                <div style="
                    position:absolute;
                    top:0;
                    left:0;
                    right:0;
                    height:4px;
                    background:{ModernUI._hex_to_rgba(safe_color, 0.5 if not theme['is_dark'] else 0.35)};
                "></div>
                {header_html}
                {status_html}
                <div style="display:flex; flex-direction:column; gap:8px;">
                    {metrics_html}
                </div>
                {feedback_html}
            </div>
            """
        )

        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def training_status_description() -> None:
        """Отображает справочную информацию Garmin о статусе тренировки."""
        
        info_text = ModernUI._clean_html(
            """
            Статус тренировки помогает оценить, как общий объем и качество ваших занятий влияет на форму.

            **Узнавайте о своих успехах.** При отслеживании активности с помощью устройств Garmin оценка обновляется на основе острой нагрузки, вариабельности частоты пульса и показателя VO₂ Max.

            Возможные статусы:
            - Высокая нагрузка
            - Пиковое значение
            - Производительная
            - Поддержание
            - Восстановление
            - Напряжение
            - Непроизводительная
            - Детренированность
            - Статус недоступен
            - Приостановлено

            Каждый статус сопровождается пояснениями, что привело к оценке, и подсказками по дальнейшим шагам, включая влияние VO₂ Max, состояния ВЧП и острой нагрузки.
            """
        )
        with st.expander("❓ Статус тренировки?"):
            st.markdown(info_text)
    
    @staticmethod
    def status_card(title, value, status_type, trend=None, description=None):
        """Карточка статуса в стиле AI Endurance с круговыми индикаторами

        Дополнительно поддерживает статус-типы: 'success', 'warning', 'danger', 'secondary', 'info'
        и строковые тренды (например, стрелки '↗️', '↘️').
        """
        
        if not st.session_state.get("use_custom_theme", True):
            display_value = value if isinstance(value, str) else f"{value}"
            st.metric(title, display_value)
            if description:
                st.caption(description)
            return

        # Получаем текущую тему
        theme = ModernUI.get_theme()
        
        # Безопасное преобразование значения в число для определения статуса
        try:
            if isinstance(value, str):
                # Убираем все не-числовые символы кроме точки и минуса
                numeric_str = ''.join(c for c in value if c.isdigit() or c in '.-')
                numeric_value = float(numeric_str) if numeric_str else 0
            else:
                numeric_value = float(value) if value else 0
        except:
            numeric_value = 0
        
        # Определяем статус, цвет и процент для кругового индикатора
        if status_type in ('success', 'warning', 'danger', 'secondary', 'info'):
            # Цвета в палитре AI Endurance
            color_map = {
                'success': ('#10B981', 'Good'),     # зеленый
                'warning': ('#F59E0B', 'Caution'),  # желтый
                'danger': ('#EF4444', 'Critical'),  # красный
                'secondary': ('#64748B', 'Info'),   # серый
                'info': ('#3B82F6', 'Info'),        # синий
            }
            color, status_badge = color_map.get(status_type, ('#8B5CF6', 'Status'))
            # Для категориальных статусов отображаем условный прогресс, чтобы кольцо выглядело завершенным
            progress_map = {
                'success': 90,
                'warning': 65,
                'danger': 35,
                'secondary': 50,
                'info': 75,
            }
            progress_percent = progress_map.get(status_type, 75)
        elif status_type == 'tsb':
            # TSB: -50 до +20 -> 0 до 100%
            progress_percent = max(0, min(100, ((numeric_value + 50) / 70) * 100))
            if numeric_value > 5:
                color = '#10B981'  # зеленый
                status_badge = "Peak Form"
            elif numeric_value > -10:
                color = '#3B82F6'  # синий
                status_badge = "Fresh"
            elif numeric_value > -30:
                color = '#F59E0B'  # желтый
                status_badge = "Tired"
            else:
                color = '#EF4444'  # красный
                status_badge = "Overtrained"
        elif status_type == 'readiness':
            progress_percent = min(100, max(0, numeric_value))
            if numeric_value > 80:
                color = '#10B981'  # зеленый
                status_badge = "Ready"
            elif numeric_value > 60:
                color = '#F59E0B'  # желтый
                status_badge = "Caution"
            else:
                color = '#EF4444'  # красный
                status_badge = "Not Ready"
        else:  # ctl
            # CTL: 0 до 200 -> 0 до 100%
            progress_percent = min(100, max(0, (numeric_value / 200) * 100))
            color = '#8B5CF6'  # фиолетовый
            status_badge = "Training Load"
        
        # Создаем круговой индикатор (упрощенный SVG) с адаптацией к теме
        bg_circle_color = "rgba(100,100,100,0.3)" if theme['is_dark'] else "rgba(200,200,200,0.3)"
        value_color = color
        
        circle_html = f"""
        <div style="width: 120px; height: 120px; margin: 20px auto; position: relative;">
            <svg width="120" height="120" viewBox="0 0 120 120" style="transform: rotate(-90deg);">
                <circle cx="60" cy="60" r="50" fill="none" 
                        stroke="{bg_circle_color}" stroke-width="8"/>
                <circle cx="60" cy="60" r="50" fill="none" 
                        stroke="{color}" stroke-width="8" 
                        stroke-dasharray="{2 * 3.14159 * 50}" 
                        stroke-dashoffset="{2 * 3.14159 * 50 * (1 - progress_percent / 100)}"
                        stroke-linecap="round"/>
            </svg>
            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); 
                        text-align: center; font-size: 24px; font-weight: bold; color: {value_color};">
                {value}
            </div>
        </div>
        """
        
        # Тренд
        trend_html = ""
        if trend is not None:
            try:
                # Если пришло число — отрисуем стрелку и величину
                if isinstance(trend, (int, float)) or (isinstance(trend, str) and trend.replace('.', '', 1).replace('-', '', 1).isdigit()):
                    trend_value = float(trend)
                    trend_direction = "↗" if trend_value > 0 else "↘" if trend_value < 0 else "→"
                    trend_text = f"{trend_direction} {abs(trend_value):.1f}"
                elif isinstance(trend, str) and trend.strip():
                    # Если пришла строка (например, '↗️') — показываем как есть
                    trend_text = trend.strip()
                else:
                    trend_text = None

                if trend_text:
                    trend_html = (
                        f"<div style=\"position: absolute; top: 15px; right: 15px; "
                        f"           background: rgba(255,255,255,0.9); padding: 4px 8px; border-radius: 12px;"
                        f"           font-size: 12px; font-weight: bold; color: {color};\">{trend_text}</div>"
                    )
            except:
                pass
        
        # Статус бейдж
        badge_html = (
            f"<div style=\"text-align: center; margin: 10px 0;\">"
            f"<span style=\"background: {color}; color: white; padding: 6px 12px; border-radius: 15px; font-size: 12px; font-weight: bold;\">{status_badge}</span>"
            f"</div>"
        )
        
        # AI Endurance стиль карточки с адаптацией к теме
        bg_color = "rgba(30,30,30,0.95)" if theme['is_dark'] else "rgba(255,255,255,0.95)"
        title_color = "#F5F5F5" if theme['is_dark'] else "#374151"
        desc_color = "#A0A0A0" if theme['is_dark'] else "#6B7280"
        box_shadow = "0 4px 20px rgba(255,255,255,0.1)" if theme['is_dark'] else "0 4px 20px rgba(0,0,0,0.1)"
        
        card_html = (
            f"<div style=\"background: {bg_color}; border-radius: 20px; padding: 25px; "
            f"            box-shadow: {box_shadow}; text-align: center; "
            f"            position: relative; margin: 10px 0; height: 320px; border: 1px solid rgba(128,128,128,0.2);\">"
            f"{trend_html}"
            f"<div style=\"margin: 0 0 15px 0; color: {title_color}; font-size: 16px; font-weight: 600;\">{title}</div>"
            f"{circle_html}"
            f"{badge_html}"
            f"<p style=\"margin: 10px 0 0 0; color: {desc_color}; font-size: 13px; line-height: 1.4;\">{(description or '')}</p>"
            f"</div>"
        )
        
        st.markdown(card_html, unsafe_allow_html=True)
    
    @staticmethod
    def ai_recommendation_panel(recommendations):
        """Панель AI рекомендаций с адаптацией к теме"""
        
        if not recommendations:
            return
        
        st.markdown("### 🤖 Персональные рекомендации")
        
        st.markdown("""
        <div class="ai-panel">
            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                <div style="width: 48px; height: 48px; background: rgba(255,255,255,0.2); 
                           border-radius: 50%; display: flex; align-items: center; 
                           justify-content: center; font-size: 24px;">
                    🧠
                </div>
                <div>
                    <h3 style="margin: 0; color: white;">AI Тренер</h3>
                    <p style="margin: 0; opacity: 0.9; font-size: 14px; color: white;">
                        Анализ на основе ваших данных
                    </p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        for rec in recommendations:
            priority_colors = {
                "high": "#EF4444",
                "medium": "#F59E0B", 
                "low": "#10B981"
            }
            color = priority_colors.get(rec['priority'], '#667eea')
            
            st.markdown(f"""
            <div class="ai-recommendation" style="border-left: 3px solid {color};">
                <div style="margin-bottom: 8px;">
                    <strong style="color: white;">{rec['title']}</strong>
                </div>
                <p style="margin: 0; font-size: 14px; color: white; opacity: 0.9;">
                    {rec['description']}
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    @staticmethod
    def create_circular_indicator(value, max_value, title, subtitle, color="#667eea"):
        """Круговой индикатор с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        percentage = (value / max_value) * 100 if max_value > 0 else 0
        
        # Адаптируем цвет фона под тему
        bg_color = 'rgba(102, 126, 234, 0.1)' if not st.session_state.get('dark_mode', False) else 'rgba(76, 95, 213, 0.2)'
        
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=percentage,
            number={'suffix': "%", 'font': {'size': 40, 'color': color}},
            domain={'x': [0, 1], 'y': [0, 1]},
            title={
                'text': f"{title}<br><span style='font-size:14px'>{subtitle}</span>",
                'font': {'color': theme['text_primary']}
            },
            gauge={
                'axis': {'range': [None, 100], 'visible': False},
                'bar': {'color': color, 'thickness': 0.15},
                'bgcolor': "rgba(0,0,0,0)",
                'borderwidth': 0,
                'bordercolor': "rgba(0,0,0,0)",
                'steps': [
                    {'range': [0, 100], 'color': bg_color}
                ]
            }
        ))
        
        fig.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=50, b=20),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'family': 'Inter, sans-serif', 'color': theme['text_primary']}
        )
        
        return fig
    
    @staticmethod
    def show_horizontal_nav(current_page="Dashboard"):
        """Render a compact page context strip.

        Historically this method rendered a large purple hero. Dashboard and
        Planning V2 now own their own hero surfaces, so this is intentionally
        quiet and only preserves lightweight page context for older call sites.
        """
        st.markdown(
            ModernUI._clean_html(
                f"""
                <div class="ic-page-context">
                    <span class="ic-caption">AI Trainer</span>
                    <span class="ic-sync-pill">{ModernUI._escape_html(current_page)}</span>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
    
    @staticmethod
    def show_weekly_training_calendar(activities_df=None):
        """Недельный календарь тренировок с адаптацией к теме.

        Если передан DataFrame, он используется напрямую, иначе данные подгружаются из базы.
        """
        from datetime import datetime, timedelta
        import pandas as pd

        theme = ModernUI.get_theme()
        st.markdown("### Тренировки на этой неделе")

        # Определяем текущую неделю (Пн–Вс)
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Понедельник
        week_dates = [week_start + timedelta(days=i) for i in range(7)]
        day_labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        cols = st.columns(7)

        # Загружаем активности при необходимости и фильтруем по неделе
        if activities_df is None:
            try:
                activities_df = st.session_state.database.get_activities(14)
            except Exception:
                activities_df = pd.DataFrame()

        if not activities_df.empty and 'date' in activities_df.columns:
            activities_df = activities_df.copy()
            activities_df['date'] = pd.to_datetime(activities_df['date'], errors='coerce')
            activities_df['date_only'] = activities_df['date'].dt.date
            activities_df = activities_df[
                (activities_df['date_only'] >= week_start) & (activities_df['date_only'] <= week_dates[-1])
            ]
        else:
            activities_df = pd.DataFrame(columns=['date_only', 'sport', 'duration_minutes', 'distance_km'])

        # Подготовка агрегатов по дням
        by_day = {}
        if not activities_df.empty:
            # Заполняем NaN нулями для безопасных сумм
            activities_df['distance_km'] = pd.to_numeric(activities_df.get('distance_km', 0), errors='coerce').fillna(0.0)
            activities_df['duration_minutes'] = pd.to_numeric(activities_df.get('duration_minutes', 0), errors='coerce').fillna(0.0)

            for d in week_dates:
                day_df = activities_df[activities_df['date_only'] == d]
                if day_df.empty:
                    by_day[d] = None
                else:
                    # Главная активность (по длительности, затем по дистанции)
                    main = day_df.sort_values(['duration_minutes','distance_km'], ascending=False).iloc[0].to_dict()
                    total_distance = float(day_df['distance_km'].sum()) if 'distance_km' in day_df else 0.0
                    total_duration = float(day_df['duration_minutes'].sum()) if 'duration_minutes' in day_df else 0.0
                    count = len(day_df)
                    by_day[d] = {
                        'main': main,
                        'total_distance': total_distance,
                        'total_duration': total_duration,
                        'count': count
                    }

        # Утилиты форматирования
        def fmt_distance(km: float) -> str:
            if km <= 0:
                return "—"
            return f"{km:.1f} км" if km >= 1 else f"{km*1000:.0f} м"

        def fmt_duration(mins: float) -> str:
            mins = int(round(mins or 0))
            h, m = divmod(mins, 60)
            return f"{h} ч {m} м" if h else f"{m} мин"

        def sport_icon(name: str) -> str:
            n = (name or '').lower()
            if 'run' in n or 'бег' in n:
                return '🏃‍♂️ Бег'
            if 'ride' in n or 'cycle' in n or 'вел' in n:
                return '🚴‍♂️ Велосипед'
            if 'swim' in n or 'плав' in n:
                return '🏊‍♂️ Плавание'
            if 'walk' in n or 'ход' in n:
                return '🚶 Ходьба'
            if 'hike' in n or 'поход' in n:
                return '🥾 Поход'
            if 'row' in n:
                return '🚣 Гребля'
            if 'ski' in n:
                return '🎿 Лыжи'
            if 'strength' in n or 'сил' in n:
                return '🏋️ Силовая'
            return f"⚪ {name or 'Другое'}"

        # Рендер по дням недели
        for i, day_date in enumerate(week_dates):
            day_label = day_labels[i]
            with cols[i]:
                data = by_day.get(day_date)
                if data:
                    bg_color = theme['surface_light']
                    text_color = theme['text_primary']
                    border_color = '#10B981'

                    main = data['main']
                    title = sport_icon(main.get('sport'))
                    totals = f"{fmt_distance(data['total_distance'])} • {fmt_duration(data['total_duration'])}"
                    more = f"+{data['count']-1} ещё" if data['count'] > 1 else ""

                    card_html = (
                        f"<div style=\"background: {bg_color}; border-radius: 15px; padding: 12px; height: 150px;"
                        f"           border-left: 4px solid {border_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.1);\">"
                        f"  <div style=\"text-align: center; font-weight: 700; margin-bottom: 6px; color: {text_color};\">{day_label} {day_date.day:02d}.{day_date.month:02d}</div>"
                        f"  <div style=\"margin-bottom: 6px; font-weight: 600; color: {text_color};\">{title}</div>"
                        f"  <div style=\"font-size: 12px; color: {theme['text_secondary']};\">{totals}</div>"
                        f"  <div style=\"font-size: 11px; color: {theme['text_secondary']}; margin-top: 6px;\">{more}</div>"
                        f"</div>"
                    )
                    st.markdown(card_html, unsafe_allow_html=True)
                else:
                    # День отдыха
                    bg_color = theme['surface_dark']
                    text_color = 'white' if not theme['is_dark'] else theme['text_secondary']
                    rest_html = (
                        f"<div style=\"background: {bg_color}; border-radius: 15px; padding: 12px; height: 150px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);\">"
                        f"  <div style=\"text-align: center; color: {text_color}; font-weight: 700;\">{day_label} {day_date.day:02d}.{day_date.month:02d}</div>"
                        f"  <div style=\"text-align: center; color: {text_color}; margin-top: 18px; font-size: 12px; opacity: 0.8;\">Отдых</div>"
                        f"</div>"
                    )
                    st.markdown(rest_html, unsafe_allow_html=True)
    
    @staticmethod
    def create_mini_trend_chart(data, title, color="#3B82F6", height=100):
        """Мини-график тренда с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        
        fig = go.Figure()
        
        # Основная линия
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines+markers',
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            showlegend=False,
            hovertemplate='%{y:.1f}<extra></extra>'
        ))
        
        # Заливка
        fig.add_trace(go.Scatter(
            y=data,
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Оформление
        fig.update_layout(
            height=height,
            margin=dict(l=0, r=0, t=25, b=0),
            xaxis=dict(
                showticklabels=False, 
                showgrid=False,
                showline=False,
                zeroline=False
            ),
            yaxis=dict(
                showticklabels=False, 
                showgrid=True,
                gridcolor='rgba(0,0,0,0.05)',
                showline=False,
                zeroline=False
            ),
            title=dict(
                text=title, 
                font=dict(size=12, color=theme['text_secondary']),
                x=0.5,
                y=0.95
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
