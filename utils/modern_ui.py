"""
Улучшенные UI компоненты с полной поддержкой темной темы
"""

import textwrap

import streamlit as st
import plotly.graph_objects as go
from typing import Dict, Optional, Sequence, Tuple

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
        /* Импорт современного шрифта */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
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
        }}
        
        /* Базовые стили приложения */
        .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: {theme['bg_primary']} !important;
            color: {theme['text_primary']} !important;
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
        
        /* Кнопки с адаптацией к теме */
        .stButton > button {{
            background-color: {'#2D2D2D' if dark_mode else '#FFFFFF'} !important;
            color: {theme['text_primary']} !important;
            border: 1px solid {theme['border_gray']} !important;
            transition: all 0.2s ease;
        }}
        
        .stButton > button:hover {{
            background-color: {'#3D3D3D' if dark_mode else '#F5F5F5'} !important;
            border-color: var(--primary-blue) !important;
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
        .stSelectbox > div > div,
        .stTextArea > div > div > textarea {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
            border: 1px solid {theme['border_gray']} !important;
        }}
        
        /* Expander */
        .streamlit-expanderHeader {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Dataframe */
        .dataframe {{
            background-color: {theme['metric_bg']} !important;
            color: {theme['text_primary']} !important;
        }}
        
        /* Sidebar */
        section[data-testid="stSidebar"] {{
            background-color: {theme['surface_dark'] if dark_mode else '#F0F2F6'} !important;
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
        """Горизонтальная навигация с адаптацией к теме"""
        
        theme = ModernUI.get_theme()
        
        st.markdown(f"""
        <div style="background: {theme['primary_gradient']};
                   border-radius: 20px; padding: 20px; margin-bottom: 30px;
                   box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0; color: white;">AI Trainer</h2>
                <div style="color: white;">{current_page}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
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
