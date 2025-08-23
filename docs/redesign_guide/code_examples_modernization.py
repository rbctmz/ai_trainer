# =============================================================================
# ПРИМЕРЫ КОДА ДЛЯ МОДЕРНИЗАЦИИ AI TRAINER
# =============================================================================

# 1. НОВАЯ ФУНКЦИЯ СТАТУС-ПАНЕЛИ (заменить в app.py)
# =============================================================================

def calculate_current_status():
    """Расчет текущего статуса с приоритизацией проблем"""
    
    # Получаем все данные
    activities_df = st.session_state.database.get_activities(30)
    hrv_df = st.session_state.database.get_hrv_data(7)
    sleep_df = st.session_state.database.get_sleep_data(7)
    
    status = {
        'critical_status': None,
        'critical_action': None,
        'recommendations': [],
        'tsb': 0,
        'hrv': 0,
        'readiness': 0,
        'ctl': 0,
        'trends': {}
    }
    
    # Расчет TSB и модели Банистера
    if not activities_df.empty:
        banister = BanisterModel()
        
        # Безопасная подготовка данных
        tss_data = []
        dates = []
        
        for idx, row in activities_df.iterrows():
            tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
            if pd.isna(tss_val) or tss_val is None:
                tss_val = 0
            tss_data.append(float(tss_val))
            dates.append(row['date'])
        
        current_metrics = banister.get_current_metrics(tss_data, dates)
        status['tsb'] = current_metrics.get('tsb', 0)
        status['ctl'] = current_metrics.get('ctl', 0)
        
        # Определение критических состояний по TSB
        if status['tsb'] < -30:
            status['critical_status'] = "Критическое переутомление"
            status['critical_action'] = "Полный отдых 2-3 дня"
            status['recommendations'].append({
                'title': 'Немедленные действия',
                'description': 'Ваш организм в состоянии переутомления',
                'actions': ['День отдыха', 'Легкая прогулка', 'Массаж'],
                'priority': 'high'
            })
        elif status['tsb'] < -20:
            status['critical_status'] = "Сильная усталость"
            status['critical_action'] = "Только легкие восстановительные тренировки"
            status['recommendations'].append({
                'title': 'Восстановление',
                'description': 'Рекомендуется снизить интенсивность',
                'actions': ['Zone 1 тренировка', 'Стретчинг', 'Хороший сон'],
                'priority': 'medium'
            })
        elif status['tsb'] > 5:
            status['recommendations'].append({
                'title': 'Отличная форма!',
                'description': 'Готовы к интенсивным нагрузкам',
                'actions': ['Интервальная', 'Темповая', 'FTP тест'],
                'priority': 'low'
            })
    
    # HRV анализ
    if not hrv_df.empty:
        latest_hrv = hrv_df.iloc[0]['rmssd'] if pd.notna(hrv_df.iloc[0]['rmssd']) else 0
        baseline_hrv = hrv_df['rmssd'].mean()
        status['hrv'] = latest_hrv
        
        # Тренд HRV за последние 3 дня
        if len(hrv_df) >= 3:
            recent_trend = hrv_df.head(3)['rmssd'].pct_change().mean() * 100
            status['trends']['hrv'] = recent_trend
        
        # Дополнительная проверка по HRV
        if latest_hrv < baseline_hrv * 0.8 and status['critical_status'] is None:
            status['critical_status'] = "Низкий HRV - стресс или недовосстановление"
            status['critical_action'] = "Проверьте качество сна и уровень стресса"
    
    # Комплексный индекс готовности
    if not sleep_df.empty or not hrv_df.empty:
        from data.data_processor_phase1 import Phase1DataProcessor
        
        latest_sleep = sleep_df.iloc[0].to_dict() if not sleep_df.empty else {}
        latest_hrv = hrv_df.iloc[0].to_dict() if not hrv_df.empty else {}
        
        readiness_data = Phase1DataProcessor.calculate_comprehensive_readiness(
            latest_sleep, latest_hrv, {}, {}
        )
        
        if readiness_data and 'readiness_score' in readiness_data:
            status['readiness'] = readiness_data['readiness_score']
    
    return status

# =============================================================================
# 2. УЛУЧШЕННАЯ ФУНКЦИЯ ДАШБОРДА (заменить в app.py)
# =============================================================================

def show_dashboard():
    """Модернизированный дашборд с фокусом на статус и действия"""
    
    # Применяем современные стили
    ModernUI.apply_modern_styles()
    
    # Рассчитываем текущий статус
    status = calculate_current_status()
    
    # БЛОК 1: Критические уведомления
    if status['critical_status']:
        st.markdown(f"""
        <div class="modern-card status-critical">
            <div class="flex items-center gap-3 mb-3">
                <span class="text-2xl">🚨</span>
                <div>
                    <h3 class="text-lg font-semibold text-red-800">{status['critical_status']}</h3>
                    <p class="text-red-600">{status['critical_action']}</p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # БЛОК 2: Ключевые метрики (только 4 самые важные)
    st.markdown("### 📊 Текущее состояние")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # TSB с цветовым кодированием
        tsb_color = ("success" if status['tsb'] > 5 else "warning" 
                    if status['tsb'] > -10 else "danger")
        
        st.markdown(ModernUI.metric_card_html(
            "Форма (TSB)", 
            f"{status['tsb']:.1f}",
            tsb_color,
            trend=status['trends'].get('tsb'),
            description="Баланс нагрузки"
        ), unsafe_allow_html=True)
    
    with col2:
        # HRV с трендом
        hrv_status = ("success" if status['hrv'] > 40 else "warning" 
                     if status['hrv'] > 30 else "danger")
        
        st.markdown(ModernUI.metric_card_html(
            "HRV", 
            f"{status['hrv']:.1f} мс",
            hrv_status,
            trend=status['trends'].get('hrv'),
            description="Восстановление"
        ), unsafe_allow_html=True)
    
    with col3:
        # Комплексная готовность
        readiness_status = ("success" if status['readiness'] > 70 else "warning" 
                           if status['readiness'] > 50 else "danger")
        
        st.markdown(ModernUI.metric_card_html(
            "Готовность", 
            f"{status['readiness']:.0f}%",
            readiness_status,
            description="Общий индекс"
        ), unsafe_allow_html=True)
    
    with col4:
        # CTL (фитнес)
        st.markdown(ModernUI.metric_card_html(
            "Фитнес", 
            f"{status['ctl']:.1f}",
            "info",
            trend=status['trends'].get('ctl'),
            description="CTL"
        ), unsafe_allow_html=True)
    
    # БЛОК 3: AI-панель с рекомендациями
    show_ai_recommendations_panel(status)
    
    # БЛОК 4: Быстрые действия
    show_quick_actions(status)
    
    # БЛОК 5: Компактная аналитика (сворачиваемая)
    with st.expander("📈 Подробная аналитика", expanded=False):
        show_compact_analytics()

# =============================================================================
# 3. AI-ПАНЕЛЬ С РЕКОМЕНДАЦИЯМИ
# =============================================================================

def show_ai_recommendations_panel(status):
    """Панель AI рекомендаций с современным дизайном"""
    
    st.markdown("### 🤖 Персональные рекомендации")
    
    # Контейнер для AI-панели
    ai_container = st.container()
    
    with ai_container:
        # Градиентный фон для AI-секции
        st.markdown("""
        <div class="ai-panel">
            <div class="flex items-center gap-3 mb-4">
                <div class="w-12 h-12 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                    <span class="text-2xl">🧠</span>
                </div>
                <div>
                    <h3 class="text-xl font-bold">AI Тренер</h3>
                    <p class="text-sm opacity-90">Анализ на основе ваших данных</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Отображаем рекомендации
        for rec in status['recommendations']:
            priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            
            st.markdown(f"""
            <div class="ai-recommendation">
                <div class="flex items-center gap-2 mb-2">
                    <span>{priority_emoji.get(rec['priority'], '🔵')}</span>
                    <strong>{rec['title']}</strong>
                </div>
                <p class="text-sm mb-3">{rec['description']}</p>
            </div>
            """, unsafe_allow_html=True)
        
        # Быстрые AI-действия
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💬 Задать вопрос AI", use_container_width=True):
                st.session_state.ai_chat_open = True
                st.rerun()
        
        with col2:
            if st.button("📋 Создать план", use_container_width=True):
                st.session_state.selected_page = "📈 Планирование"
                st.rerun()
        
        with col3:
            if st.button("🔍 Анализ метрик", use_container_width=True):
                # Открываем модальное окно с объяснением метрик
                st.session_state.show_metrics_explanation = True
                st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 4. БЫСТРЫЕ ДЕЙСТВИЯ
# =============================================================================

def show_quick_actions(status):
    """Контекстные быстрые действия на основе статуса"""
    
    st.markdown("### ⚡ Быстрые действия")
    
    # Определяем действия на основе статуса
    if status['critical_status']:
        # Восстановительные действия
        actions = [
            {"title": "🛌 План восстановления", "desc": "Создать план отдыха", "action": "recovery_plan"},
            {"title": "💊 Советы по восстановлению", "desc": "Питание, сон, стресс", "action": "recovery_tips"},
            {"title": "📱 Настроить уведомления", "desc": "Напоминания об отдыхе", "action": "notifications"}
        ]
    elif status['tsb'] > 5:
        # Действия для хорошей формы
        actions = [
            {"title": "🚀 Интенсивная тренировка", "desc": "Воспользоваться формой", "action": "intense_workout"},
            {"title": "🎯 FTP тест", "desc": "Проверить текущий уровень", "action": "ftp_test"},
            {"title": "📈 Увеличить нагрузку", "desc": "Прогрессия тренировок", "action": "increase_load"}
        ]
    else:
        # Стандартные действия
        actions = [
            {"title": "📊 Анализ тренировки", "desc": "Разобрать последнюю", "action": "analyze_workout"},
            {"title": "📅 Планирование недели", "desc": "Создать план", "action": "weekly_plan"},
            {"title": "💓 Проверить HRV", "desc": "Состояние восстановления", "action": "check_hrv"}
        ]
    
    # Отображаем действия
    cols = st.columns(len(actions))
    
    for i, action in enumerate(actions):
        with cols[i]:
            st.markdown(f"""
            <div class="quick-action-btn" onclick="triggerAction('{action['action']}')">
                <div class="text-lg mb-2">{action['title']}</div>
                <div class="text-sm text-gray-600">{action['desc']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Streamlit кнопка как fallback
            if st.button(f"{action['title']}", key=f"action_{i}", help=action['desc']):
                handle_quick_action(action['action'])

def handle_quick_action(action_type):
    """Обработка быстрых действий"""
    
    if action_type == "recovery_plan":
        st.session_state.selected_page = "📈 Планирование"
        st.session_state.planning_focus = "recovery"
    elif action_type == "intense_workout":
        st.session_state.selected_page = "📈 Планирование"
        st.session_state.planning_focus = "intensity"
    elif action_type == "analyze_workout":
        st.session_state.selected_page = "🏃‍♂️ Активности"
        st.session_state.activities_focus = "analysis"
    elif action_type == "check_hrv":
        st.session_state.selected_page = "💓 Анализ HRV"
    # ... другие действия
    
    st.rerun()

# =============================================================================
# 5. МОДЕРНИЗИРОВАННЫЕ МЕТРИКИ (заменить в show_dashboard)
# =============================================================================

def display_metric_with_context(title, value, metric_type, trend=None):
    """Отображение метрики с контекстом и цветовым кодированием"""
    
    # Определяем статус и цвет
    status_config = get_metric_status_config(value, metric_type)
    
    # Расчет тренда
    trend_html = ""
    if trend is not None:
        trend_direction = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
        trend_color = "text-green-500" if trend > 0 else "text-red-500" if trend < 0 else "text-gray-500"
        trend_html = f'<div class="text-xs {trend_color}">{trend_direction} {abs(trend):.1f}</div>'
    
    # HTML карточки метрики
    metric_html = f"""
    <div class="metric-card {status_config['bg_class']} border-l-4 {status_config['border_class']} p-4 rounded-lg h-full">
        <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-600">{title}</span>
            <span class="text-lg">{status_config['emoji']}</span>
        </div>
        <div class="flex items-end justify-between">
            <div>
                <div class="text-2xl font-bold {status_config['text_class']}">{value}</div>
                <div class="text-xs text-gray-500">{status_config['description']}</div>
            </div>
            {trend_html}
        </div>
        
        <!-- Мини индикатор прогресса -->
        <div class="mt-3">
            <div class="w-full bg-gray-200 rounded-full h-1">
                <div class="{status_config['progress_class']} h-1 rounded-full transition-all duration-300" 
                     style="width: {status_config['progress_width']}%"></div>
            </div>
        </div>
    </div>
    """
    
    st.markdown(metric_html, unsafe_allow_html=True)

def get_metric_status_config(value, metric_type):
    """Получение конфигурации статуса для метрики"""
    
    if metric_type == "TSB":
        if value > 5:
            return {
                'emoji': '🟢', 'bg_class': 'bg-green-50', 'border_class': 'border-green-500',
                'text_class': 'text-green-600', 'progress_class': 'bg-green-500',
                'progress_width': min(100, (value + 50) * 1.2),
                'description': 'Отличная форма'
            }
        elif value > -10:
            return {
                'emoji': '🟡', 'bg_class': 'bg-yellow-50', 'border_class': 'border-yellow-500',
                'text_class': 'text-yellow-600', 'progress_class': 'bg-yellow-500',
                'progress_width': min(100, (value + 50) * 1.2),
                'description': 'Хорошая форма'
            }
        elif value > -30:
            return {
                'emoji': '🟠', 'bg_class': 'bg-orange-50', 'border_class': 'border-orange-500',
                'text_class': 'text-orange-600', 'progress_class': 'bg-orange-500',
                'progress_width': min(100, (value + 50) * 1.2),
                'description': 'Усталость'
            }
        else:
            return {
                'emoji': '🔴', 'bg_class': 'bg-red-50', 'border_class': 'border-red-500',
                'text_class': 'text-red-600', 'progress_class': 'bg-red-500',
                'progress_width': min(100, (value + 50) * 1.2),
                'description': 'Переутомление'
            }
    
    elif metric_type == "HRV":
        if value > 40:
            return {
                'emoji': '💚', 'bg_class': 'bg-green-50', 'border_class': 'border-green-500',
                'text_class': 'text-green-600', 'progress_class': 'bg-green-500',
                'progress_width': min(100, value * 1.5),
                'description': 'Отличное восстановление'
            }
        elif value > 30:
            return {
                'emoji': '💛', 'bg_class': 'bg-yellow-50', 'border_class': 'border-yellow-500',
                'text_class': 'text-yellow-600', 'progress_class': 'bg-yellow-500',
                'progress_width': min(100, value * 1.5),
                'description': 'Нормальное состояние'
            }
        else:
            return {
                'emoji': '❤️', 'bg_class': 'bg-red-50', 'border_class': 'border-red-500',
                'text_class': 'text-red-600', 'progress_class': 'bg-red-500',
                'progress_width': min(100, value * 1.5),
                'description': 'Требуется отдых'
            }
    
    # Готовность
    elif metric_type == "Готовность":
        if value > 80:
            return {
                'emoji': '🚀', 'bg_class': 'bg-blue-50', 'border_class': 'border-blue-500',
                'text_class': 'text-blue-600', 'progress_class': 'bg-blue-500',
                'progress_width': value,
                'description': 'Готов к нагрузкам'
            }
        elif value > 60:
            return {
                'emoji': '👍', 'bg_class': 'bg-green-50', 'border_class': 'border-green-500',
                'text_class': 'text-green-600', 'progress_class': 'bg-green-500',
                'progress_width': value,
                'description': 'Хорошая готовность'
            }
        else:
            return {
                'emoji': '⚠️', 'bg_class': 'bg-yellow-50', 'border_class': 'border-yellow-500',
                'text_class': 'text-yellow-600', 'progress_class': 'bg-yellow-500',
                'progress_width': value,
                'description': 'Низкая готовность'
            }
    
    # Фитнес (CTL) 
    else:  # CTL
        return {
            'emoji': '💪', 'bg_class': 'bg-purple-50', 'border_class': 'border-purple-500',
            'text_class': 'text-purple-600', 'progress_class': 'bg-purple-500',
            'progress_width': min(100, value * 1.5),
            'description': 'Хроническая нагрузка'
        }

# =============================================================================
# 6. ОБЪЕДИНЕННЫЙ AI-КОУЧИНГ (заменить show_ai_coaching)
# =============================================================================

def show_ai_coaching():
    """Объединенный интерфейс AI-коучинга"""
    
    st.header("🤖 AI Коучинг")
    
    # Проверяем настройку AI провайдера
    if not check_ai_provider_configured():
        st.warning("⚙️ Настройте AI провайдера в боковой панели")
        return
    
    # Табы для разных AI-функций (вместо отдельных страниц)
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💬 AI Чат", 
        "📊 Анализ состояния", 
        "📋 Недельный план",
        "🔍 Анализ тренировки",
        "❓ Объяснение метрик"
    ])
    
    with tab1:
        show_ai_chat_interface()
    
    with tab2:
        show_ai_status_analysis()
    
    with tab3:
        show_ai_weekly_planning()
    
    with tab4:
        show_ai_workout_analysis()
    
    with tab5:
        show_ai_metrics_explanation()

def show_ai_chat_interface():
    """Улучшенный интерфейс чата с AI"""
    
    # Контекстные быстрые вопросы
    st.markdown("#### 💡 Быстрые вопросы:")
    
    quick_questions = [
        "Как мое восстановление?",
        "Стоит ли тренироваться сегодня?", 
        "Что показывает мой HRV?",
        "Как улучшить форму?",
        "План на эту неделю?"
    ]
    
    # Отображаем быстрые вопросы как кнопки
    cols = st.columns(3)
    for i, question in enumerate(quick_questions):
        with cols[i % 3]:
            if st.button(f"💭 {question}", key=f"quick_q_{i}", use_container_width=True):
                # Автоматически отправляем вопрос в чат
                st.session_state.pending_question = question
                st.rerun()
    
    st.markdown("---")
    
    # Основной интерфейс чата
    st.markdown("#### 💬 Чат с AI тренером")
    
    # Инициализируем чат
    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []
    
    # Отображаем историю чата
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.ai_chat_history:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="flex justify-end mb-3">
                    <div class="bg-blue-500 text-white rounded-lg p-3 max-w-xs">
                        {message["content"]}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="flex justify-start mb-3">
                    <div class="bg-gray-100 rounded-lg p-3 max-w-md">
                        <div class="flex items-center gap-2 mb-1">
                            <span>🤖</span>
                            <strong>AI Тренер</strong>
                        </div>
                        {message["content"]}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    
    # Обработка отложенного вопроса
    if "pending_question" in st.session_state:
        user_input = st.session_state.pending_question
        del st.session_state.pending_question
        process_ai_chat_message(user_input)
        st.rerun()
    
    # Поле ввода
    user_input = st.chat_input("Задайте вопрос AI тренеру...")
    if user_input:
        process_ai_chat_message(user_input)
        st.rerun()

def process_ai_chat_message(user_input):
    """Обработка сообщения для AI чата"""
    
    # Добавляем сообщение пользователя
    st.session_state.ai_chat_history.append({
        "role": "user",
        "content": user_input
    })
    
    # Получаем контекст данных
    from models.ai_data_context import AIDataContext
    context = AIDataContext.get_training_context(st.session_state.database)
    
    # Отправляем в AI
    try:
        from models.ai_coach_universal import UniversalAICoach
        ai_coach = UniversalAICoach()
        
        response = ai_coach.get_response(
            user_input, 
            context=context,
            chat_history=st.session_state.ai_chat_history[-10:]  # Последние 10 сообщений
        )
        
        # Добавляем ответ AI
        st.session_state.ai_chat_history.append({
            "role": "assistant", 
            "content": response
        })
        
    except Exception as e:
        st.session_state.ai_chat_history.append({
            "role": "assistant",
            "content": f"Извините, произошла ошибка: {str(e)}"
        })

# =============================================================================
# 7. УЛУЧШЕННАЯ ВИЗУАЛИЗАЦИЯ ПЛАНИРОВАНИЯ
# =============================================================================

def show_planning_modern():
    """Модернизированное планирование с интерактивными элементами"""
    
    st.header("📈 Планирование тренировок")
    
    # Получаем данные
    activities_df = st.session_state.database.get_activities(90)
    
    if activities_df.empty:
        st.warning("📭 Нет данных для анализа. Синхронизируйте данные с Garmin Connect.")
        return
    
    # Инициализируем модель Банистера
    banister = BanisterModel()
    
    # Подготавливаем данные
    tss_data = []
    dates = []
    
    for idx, row in activities_df.iterrows():
        tss_val = row['tss'] if 'tss' in row and pd.notna(row['tss']) else 0
        if pd.isna(tss_val) or tss_val is None:
            tss_val = 0
        tss_data.append(float(tss_val))
        dates.append(row['date'])
    
    # Вычисляем метрики
    current_metrics = banister.get_current_metrics(tss_data, dates)
    
    # БЛОК 1: Текущее состояние с рекомендациями
    st.markdown("### 🎯 Текущая форма и рекомендации")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Компактные метрики Банистера
        st.markdown(f"""
        <div class="modern-card">
            <h4 class="text-lg font-semibold mb-4">Модель Банистера</h4>
            <div class="space-y-3">
                <div class="flex justify-between">
                    <span>CTL (Фитнес):</span>
                    <strong class="text-blue-600">{current_metrics['ctl']:.1f}</strong>
                </div>
                <div class="flex justify-between">
                    <span>ATL (Усталость):</span>
                    <strong class="text-red-600">{current_metrics['atl']:.1f}</strong>
                </div>
                <div class="flex justify-between">
                    <span>TSB (Форма):</span>
                    <strong class="text-purple-600">{current_metrics['tsb']:.1f}</strong>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # AI рекомендации по планированию
        st.markdown("#### 🤖 Рекомендации AI тренера")
        
        # Генерируем рекомендации на основе метрик
        recommendations = generate_training_recommendations(current_metrics)
        
        for rec in recommendations:
            st.markdown(f"""
            <div class="ai-recommendation bg-blue-50 border border-blue-200 rounded-lg p-3 mb-2">
                <div class="font-semibold text-blue-800">{rec['title']}</div>
                <div class="text-sm text-blue-700">{rec['description']}</div>
            </div>
            """, unsafe_allow_html=True)
    
    # БЛОК 2: Интерактивный график Банистера
    st.markdown("### 📊 Динамика формы (модель Банистера)")
    
    # Расчёт CTL, ATL, TSB
    dates_full, ctl_values, atl_values, tsb_values = banister.calculate_ctl_atl_tsb(tss_data, dates)
    
    if dates_full and ctl_values:
        # Создаем улучшенный график
        fig_banister = create_modern_banister_chart(dates_full, ctl_values, atl_values, tsb_values)
        st.plotly_chart(fig_banister, use_container_width=True)
    
    # БЛОК 3: Планирование на будущее
    st.markdown("### 🔮 Прогноз и планирование")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📅 Планирование недели")
        
        # Виджет для создания плана
        target_tss = st.slider("Целевой недельный TSS:", 0, 500, int(current_metrics['ctl'] * 7))
        target_days = st.multiselect("Дни тренировок:", 
                                   ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
                                   default=["Вторник", "Четверг", "Суббота"])
        
        if st.button("🎯 Создать план тренировок"):
            plan = generate_weekly_plan(target_tss, target_days, current_metrics)
            st.session_state.generated_plan = plan
            st.success("✅ План создан!")
    
    with col2:
        st.markdown("#### 🔮 Прогноз формы")
        
        # Прогноз на основе различных сценариев
        scenarios = {
            "Текущий темп": {"weekly_tss": current_metrics['ctl'] * 7},
            "Увеличение на 10%": {"weekly_tss": current_metrics['ctl'] * 7 * 1.1},
            "Снижение на 20%": {"weekly_tss": current_metrics['ctl'] * 7 * 0.8}
        }
        
        selected_scenario = st.selectbox("Выберите сценарий:", list(scenarios.keys()))
        
        if st.button("📈 Показать прогноз"):
            forecast = banister.forecast_metrics(scenarios[selected_scenario], days=14)
            st.session_state.forecast_data = forecast

# =============================================================================
# 8. КОМПАКТНАЯ АНАЛИТИКА ДЛЯ ДАШБОРДА
# =============================================================================

def show_compact_analytics():
    """Компактная аналитика для экспандера на дашборде"""
    
    # Получаем данные
    activities_df = st.session_state.database.get_activities(30)
    hrv_df = st.session_state.database.get_hrv_data(14)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if not activities_df.empty:
            st.markdown("**📊 Активности за месяц**")
            
            # Мини-статистика
            total_activities = len(activities_df)
            total_time = activities_df['duration_minutes'].sum() / 60
            avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns else 0
            
            stats_html = f"""
            <div class="grid grid-cols-3 gap-4 text-center">
                <div>
                    <div class="text-2xl font-bold text-blue-600">{total_activities}</div>
                    <div class="text-xs text-gray-500">Тренировок</div>
                </div>
                <div>
                    <div class="text-2xl font-bold text-green-600">{total_time:.1f}</div>
                    <div class="text-xs text-gray-500">Часов</div>
                </div>
                <div>
                    <div class="text-2xl font-bold text-purple-600">{avg_tss:.0f}</div>
                    <div class="text-xs text-gray-500">Ср. TSS</div>
                </div>
            </div>
            """
            st.markdown(stats_html, unsafe_allow_html=True)
            
            # Мини-график активности
            daily_tss = activities_df.groupby('date')['tss'].sum().tail(14)
            if len(daily_tss) > 1:
                mini_chart = ModernUI.create_mini_trend_chart(daily_tss.values, "TSS за 2 недели")
                st.plotly_chart(mini_chart, use_container_width=True)
    
    with col2:
        if not hrv_df.empty:
            st.markdown("**💓 Восстановление (HRV)**")
            
            current_hrv = hrv_df.iloc[0]['rmssd']
            avg_hrv = hrv_df['rmssd'].mean()
            hrv_trend = (current_hrv - avg_hrv) / avg_hrv * 100
            
            # HRV статистика
            hrv_stats_html = f"""
            <div class="grid grid-cols-2 gap-4 text-center mb-3">
                <div>
                    <div class="text-2xl font-bold text-green-600">{current_hrv:.1f}</div>
                    <div class="text-xs text-gray-500">Текущий RMSSD</div>
                </div>
                <div>
                    <div class="text-2xl font-bold text-blue-600">{hrv_trend:+.1f}%</div>
                    <div class="text-xs text-gray-500">От среднего</div>
                </div>
            </div>
            """
            st.markdown(hrv_stats_html, unsafe_allow_html=True)
            
            # Мини-график HRV
            if len(hrv_df) > 1:
                mini_hrv_chart = ModernUI.create_mini_trend_chart(
                    hrv_df['rmssd'].values, "HRV тренд", color="#10B981"
                )
                st.plotly_chart(mini_hrv_chart, use_container_width=True)

# =============================================================================
# 9. СОВРЕМЕННЫЙ ГРАФИК БАНИСТЕРА (обновить в visualizations.py)
# =============================================================================

def create_modern_banister_chart(dates, ctl_values, atl_values, tsb_values):
    """Модернизированный график модели Банистера"""
    
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.65, 0.35],
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]]
    )
    
    # === Верхний график: CTL и ATL ===
    
    # CTL с заливкой
    fig.add_trace(go.Scatter(
        x=dates, y=ctl_values,
        fill='tozeroy',
        mode='lines',
        name='CTL (Фитнес)',
        line=dict(color='#3B82F6', width=3),
        fillcolor='rgba(59, 130, 246, 0.15)',
        hovertemplate='<b>Фитнес (CTL)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=1, col=1)
    
    # ATL с заливкой
    fig.add_trace(go.Scatter(
        x=dates, y=atl_values,
        fill='tozeroy',
        mode='lines',
        name='ATL (Усталость)',
        line=dict(color='#EF4444', width=3),
        fillcolor='rgba(239, 68, 68, 0.15)',
        hovertemplate='<b>Усталость (ATL)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=1, col=1)
    
    # === Нижний график: TSB с цветовыми зонами ===
    
    # Создаем цветовые зоны для TSB
    fig.add_hrect(y0=5, y1=30, fillcolor="#10B981", opacity=0.1, 
                  annotation_text="Отличная форма", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-10, y1=5, fillcolor="#F59E0B", opacity=0.1,
                  annotation_text="Хорошая форма", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-30, y1=-10, fillcolor="#EF4444", opacity=0.1,
                  annotation_text="Усталость", annotation_position="top right",
                  row=2, col=1)
    fig.add_hrect(y0=-50, y1=-30, fillcolor="#991B1B", opacity=0.2,
                  annotation_text="Переутомление", annotation_position="top right",
                  row=2, col=1)
    
    # TSB линия с маркерами
    fig.add_trace(go.Scatter(
        x=dates, y=tsb_values,
        mode='lines+markers',
        name='TSB (Форма)',
        line=dict(color='#8B5CF6', width=4),
        marker=dict(size=6, color='#8B5CF6', line=dict(width=1, color='white')),
        hovertemplate='<b>Форма (TSB)</b><br>%{x}<br>%{y:.1f}<extra></extra>'
    ), row=2, col=1)
    
    # Нулевая линия для TSB
    fig.add_hline(y=0, line_dash="dot", line_color="#64748B", opacity=0.7, row=2, col=1)
    
    # Современное оформление
    fig.update_layout(
        height=600,
        title={
            'text': "Модель Банистера: Анализ фитнеса и формы",
            'x': 0.5,
            'font': {'size': 20, 'family': 'Arial, sans-serif'}
        },
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='#E2E8F0',
            borderwidth=1
        ),
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(l=0, r=0, t=80, b=0)
    )
    
    # Стилизация осей
    fig.update_yaxes(
        title_text="Тренировочная нагрузка", 
        row=1, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    fig.update_yaxes(
        title_text="TSB (Форма спортсмена)", 
        row=2, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    fig.update_xaxes(
        title_text="Дата", 
        row=2, col=1,
        gridcolor='#F1F5F9',
        title_font=dict(size=14)
    )
    
    return fig

def generate_training_recommendations(current_metrics):
    """Генерация рекомендаций на основе метрик Банистера"""
    
    recommendations = []
    tsb = current_metrics.get('tsb', 0)
    ctl = current_metrics.get('ctl', 0)
    atl = current_metrics.get('atl', 0)
    
    if tsb < -30:
        recommendations.append({
            'title': '🛌 Критическое переутомление',
            'description': 'Немедленный отдых на 2-3 дня. Избегайте любых интенсивных нагрузок.'
        })
    elif tsb < -20:
        recommendations.append({
            'title': '😴 Активное восстановление',
            'description': 'Легкие восстановительные тренировки в зоне 1 (60-70% от макс. ЧСС).'
        })
    elif tsb < -10:
        recommendations.append({
            'title': '⚖️ Сбалансированные нагрузки',
            'description': 'Умеренные тренировки. Можно добавить одну интенсивную сессию.'
        })
    elif tsb > 5:
        recommendations.append({
            'title': '🚀 Пиковая форма',
            'description': 'Отличное время для соревнований или тестирования FTP/LTHR.'
        })
    else:
        recommendations.append({
            'title': '💪 Стандартные тренировки',
            'description': 'Поддерживайте текущий объем. Можно постепенно увеличивать нагрузку.'
        })
    
    # Рекомендации по CTL
    if ctl < 30:
        recommendations.append({
            'title': '📈 Развитие базы',
            'description': 'Фокус на объемных тренировках для развития аэробной базы.'
        })
    elif ctl > 80:
        recommendations.append({
            'title': '🎯 Поддержание формы',
            'description': 'Высокий уровень фитнеса. Фокус на качестве, а не количестве.'
        })
    
    return recommendations

# =============================================================================
# 10. КЛАСС MODERNUI (создать новый файл utils/modern_ui.py)
# =============================================================================

class ModernUI:
    """Современные UI компоненты для AI Trainer"""
    
    @staticmethod
    def apply_modern_styles():
        """Применяет современную CSS-стилизацию"""
        st.markdown("""
        <style>
        /* Импорт современного шрифта */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Базовые переменные */
        :root {
            --primary-blue: #3B82F6;
            --primary-blue-dark: #2563EB;
            --secondary-gray: #64748B;
            --success-green: #10B981;
            --warning-yellow: #F59E0B;
            --danger-red: #EF4444;
            --background-gray: #F8FAFC;
            --surface-white: #FFFFFF;
            --border-gray: #E2E8F0;
            --text-primary: #1E293B;
            --text-secondary: #475569;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }
        
        /* Обновленная типографика */
        .stApp {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        
        /* Современные карточки */
        .modern-card {
            background: var(--surface-white);
            border-radius: 16px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border-gray);
            padding: 24px;
            margin-bottom: 16px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        .modern-card:hover {
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        
        /* Статус-карточки */
        .status-card {
            position: relative;
            overflow: hidden;
        }
        
        .status-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
            background: var(--accent-color, #3B82F6);
        }
        
        .status-excellent::before { background: var(--success-green); }
        .status-good::before { background: var(--warning-yellow); }
        .status-warning::before { background: var(--danger-red); }
        .status-critical::before { background: #991B1B; }
        
        /* Метрики */
        .metric-card {
            background: var(--surface-white);
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--shadow-sm);
            border: 1px solid var(--border-gray);
            height: 100%;
            transition: all 0.2s ease;
        }
        
        .metric-card:hover {
            box-shadow: var(--shadow-md);
        }
        
        .metric-value {
            font-size: 2.25rem;
            font-weight: 700;
            line-height: 1;
            margin-bottom: 0.5rem;
        }
        
        .metric-label {
            font-size: 0.875rem;
            color: var(--secondary-gray);
            font-weight: 500;
            margin-bottom: 0.75rem;
        }
        
        .metric-description {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }
        
        /* AI-панель */
        .ai-panel {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            padding: 32px;
            color: white;
            margin: 24px 0;
            box-shadow: var(--shadow-lg);
        }
        
        .ai-recommendation {
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 12px;
            padding: 16px;
            margin: 12px 0;
            backdrop-filter: blur(10px);
        }
        
        /* Кнопки */
        .modern-button {
            background: var(--primary-blue);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-sm);
        }
        
        .modern-button:hover {
            background: var(--primary-blue-dark);
            box-shadow: var(--shadow-md);
            transform: translateY(-1px);
        }
        
        .modern-button-secondary {
            background: white;
            color: var(--primary-blue);
            border: 2px solid var(--primary-blue);
        }
        
        .modern-button-secondary:hover {
            background: var(--primary-blue);
            color: white;
        }
        
        /* Быстрые действия */
        .quick-actions-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin: 24px 0;
        }
        
        .quick-action-item {
            background: var(--surface-white);
            border: 2px solid var(--border-gray);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: var(--shadow-sm);
        }
        
        .quick-action-item:hover {
            border-color: var(--primary-blue);
            box-shadow: var(--shadow-md);
            transform: translateY(-2px);
        }
        
        .quick-action-icon {
            font-size: 2rem;
            margin-bottom: 12px;
        }
        
        .quick-action-title {
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-primary);
        }
        
        .quick-action-desc {
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        /* Навигационные табы */
        .modern-tabs {
            display: flex;
            background: var(--surface-white);
            border-radius: 12px;
            box-shadow: var(--shadow-sm);
            padding: 8px;
            margin-bottom: 24px;
        }
        
        .modern-tab {
            flex: 1;
            text-align: center;
            padding: 12px 16px;
            border-radius: 8px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .modern-tab.active {
            background: var(--primary-blue);
            color: white;
            box-shadow: var(--shadow-sm);
        }
        
        .modern-tab:hover:not(.active) {
            background: var(--background-gray);
        }
        
        /* Прогресс-индикаторы */
        .progress-ring {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            background: conic-gradient(var(--accent-color, #3B82F6) 0deg 180deg, #E2E8F0 180deg 360deg);
        }
        
        .progress-ring::before {
            content: '';
            position: absolute;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: white;
        }
        
        .progress-value {
            position: relative;
            z-index: 1;
            font-weight: 700;
            font-size: 1.1rem;
        }
        
        /* Анимации */
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        
        .animate-slide-in {
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        
        .animate-pulse {
            animation: pulse 2s infinite;
        }
        
        /* Адаптивность */
        @media (max-width: 768px) {
            .modern-card {
                padding: 16px;
                margin-bottom: 12px;
            }
            
            .ai-panel {
                padding: 20px;
                margin: 16px 0;
            }
            
            .quick-actions-grid {
                grid-template-columns: 1fr;
                gap: 12px;
            }
            
            .metric-value {
                font-size: 1.75rem;
            }
        }
        </style>
        """, unsafe_allow_html=True)
    
    @staticmethod
    def create_mini_trend_chart(data, title, color="#3B82F6", height=100):
        """Создание мини-графика тренда"""
        
        import plotly.graph_objects as go
        
        fig = go.Figure()
        
        # Основная линия тренда
        fig.add_trace(go.Scatter(
            y=data,
            mode='lines+markers',
            line=dict(color=color, width=2),
            marker=dict(size=4, color=color),
            showlegend=False,
            hovertemplate='%{y:.1f}<extra></extra>'
        ))
        
        # Заливка под линией
        fig.add_trace(go.Scatter(
            y=data,
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1)',
            showlegend=False,
            hoverinfo='skip'
        ))
        
        # Минималистичное оформление
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
                gridcolor='rgba(0,0,0,0.1)',
                showline=False,
                zeroline=False
            ),
            title=dict(
                text=title, 
                font=dict(size=12, color='#64748B'),
                x=0.5,
                y=0.95
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig
    
    @staticmethod
    def metric_card_html(title, value, status, trend=None, description=None):
        """HTML для современной карточки метрики"""
        
        # Конфигурации статусов
        status_configs = {
            'success': {
                'bg': 'bg-green-50', 'border': 'border-green-200', 
                'text': 'text-green-700', 'emoji': '🟢'
            },
            'warning': {
                'bg': 'bg-yellow-50', 'border': 'border-yellow-200',
                'text': 'text-yellow-700', 'emoji': '🟡'
            },
            'danger': {
                'bg': 'bg-red-50', 'border': 'border-red-200',
                'text': 'text-red-700', 'emoji': '🔴'
            },
            'info': {
                'bg': 'bg-blue-50', 'border': 'border-blue-200',
                'text': 'text-blue-700', 'emoji': '🔵'
            }
        }
        
        config = status_configs.get(status, status_configs['info'])
        
        trend_html = ""
        if trend is not None:
            trend_direction = "📈" if trend > 0 else "📉" if trend < 0 else "➡️"
            trend_color = "text-green-500" if trend > 0 else "text-red-500" if trend < 0 else "text-gray-500"
            trend_html = f'''
            <div class="absolute top-4 right-4">
                <div class="text-xs {trend_color} font-medium">
                    {trend_direction} {abs(trend):.1f}
                </div>
            </div>
            '''
        
        desc_html = ""
        if description:
            desc_html = f'<div class="metric-description">{description}</div>'
        
        return f"""
        <div class="metric-card {config['bg']} border {config['border']} relative">
            <div class="flex items-center gap-2 mb-3">
                <span class="text-lg">{config['emoji']}</span>
                <div class="metric-label">{title}</div>
            </div>
            <div class="metric-value {config['text']}">{value}</div>
            {desc_html}
            {trend_html}
        </div>
        """
    
    @staticmethod
    def status_indicator(value, thresholds, title=""):
        """Создание кругового индикатора статуса"""
        
        # Определяем зону
        if value >= thresholds.get('excellent', 80):
            color = '#10B981'
            zone = 'Отлично'
        elif value >= thresholds.get('good', 60):
            color = '#F59E0B'
            zone = 'Хорошо'
        elif value >= thresholds.get('fair', 40):
            color = '#EF4444'
            zone = 'Удовлетворительно'
        else:
            color = '#991B1B'
            zone = 'Критично'
        
        import plotly.graph_objects as go
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = value,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': f"{title}<br><span style='font-size:0.8em'>{zone}</span>"},
            gauge = {
                'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': color, 'thickness': 0.3},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#E2E8F0",
                'steps': [
                    {'range': [0, thresholds.get('fair', 40)], 'color': "#FEE2E2"},
                    {'range': [thresholds.get('fair', 40), thresholds.get('good', 60)], 'color': "#FEF3C7"},
                    {'range': [thresholds.get('good', 60), thresholds.get('excellent', 80)], 'color': "#D1FAE5"},
                    {'range': [thresholds.get('excellent', 80), 100], 'color': "#A7F3D0"}
                ]
            }
        ))
        
        fig.update_layout(
            height=200, 
            margin=dict(l=20, r=20, t=40, b=20),
            font={'color': "#1E293B", 'family': "Inter"}
        )
        
        return fig

# =============================================================================
# 11. УЛУЧШЕННАЯ ФУНКЦИЯ АКТИВНОСТЕЙ
# =============================================================================

def show_activities_modern():
    """Модернизированная страница активностей"""
    
    st.header("🏃‍♂️ Анализ активностей")
    
    # Применяем стили
    ModernUI.apply_modern_styles()
    
    # Получаем данные
    activities_df = st.session_state.database.get_activities(60)
    
    if activities_df.empty:
        show_empty_activities_state()
        return
    
    # БЛОК 1: Фильтры в современном стиле
    with st.container():
        st.markdown("### 🎛️ Фильтры и настройки")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            selected_sports = st.multiselect(
                "🏃 Виды спорта:",
                options=activities_df['sport'].unique(),
                default=activities_df['sport'].unique()
            )
        
        with col2:
            period_options = {"Неделя": 7, "Месяц": 30, "Квартал": 90}
            period_label = st.selectbox("📅 Период:", list(period_options.keys()), index=1)
            period_days = period_options[period_label]
        
        with col3:
            sort_options = {
                "По дате": "date", 
                "По дистанции": "distance_km",
                "По времени": "duration_minutes", 
                "По TSS": "tss"
            }
            sort_label = st.selectbox("🔄 Сортировка:", list(sort_options.keys()))
            sort_by = sort_options[sort_label]
        
        with col4:
            view_mode = st.selectbox("👁️ Вид:", ["Карточки", "Таблица", "График"])
    
    # Фильтруем данные
    filtered_df = filter_activities_data(activities_df, selected_sports, period_days, sort_by)
    
    # БЛОК 2: Статистика в карточках
    show_activities_stats_cards(filtered_df)
    
    # БЛОК 3: Основной контент в зависимости от режима просмотра
    if view_mode == "Карточки":
        show_activities_cards_view(filtered_df)
    elif view_mode == "Таблица":
        show_activities_table_view(filtered_df)
    else:  # График
        show_activities_chart_view(filtered_df)
    
    # БЛОК 4: Детальный анализ выбранной тренировки
    show_workout_detail_analysis(filtered_df)

def show_activities_stats_cards(activities_df):
    """Отображение статистики в виде современных карточек"""
    
    st.markdown("### 📊 Статистика за период")
    
    # Рассчитываем метрики
    total_activities = len(activities_df)
    total_distance = activities_df['distance_km'].sum()
    total_time = activities_df['duration_minutes'].sum() / 60
    avg_tss = activities_df['tss'].mean() if 'tss' in activities_df.columns else 0
    total_tss = activities_df['tss'].sum() if 'tss' in activities_df.columns else 0
    
    # Отображаем в адаптивной сетке
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Всего тренировок</div>
            <div class="metric-value text-blue-600">{total_activities}</div>
            <div class="metric-description">За выбранный период</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Общая дистанция</div>
            <div class="metric-value text-green-600">{total_distance:.1f} км</div>
            <div class="metric-description">Суммарная дистанция</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Общее время</div>
            <div class="metric-value text-purple-600">{total_time:.1f} ч</div>
            <div class="metric-description">Время тренировок</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Общий TSS</div>
            <div class="metric-value text-orange-600">{total_tss:.0f}</div>
            <div class="metric-description">Тренировочный стресс</div>
        </div>
        """, unsafe_allow_html=True)

def show_activities_cards_view(activities_df):
    """Отображение активностей в виде карточек"""
    
    st.markdown("### 🏃‍♂️ Последние тренировки")
    
    # Показываем по 6 карточек за раз
    activities_to_show = activities_df.head(6)
    
    # Отображаем в сетке 2x3
    for i in range(0, len(activities_to_show), 2):
        col1, col2 = st.columns(2)
        
        for j, col in enumerate([col1, col2]):
            if i + j < len(activities_to_show):
                activity = activities_to_show.iloc[i + j]
                
                with col:
                    # Иконка спорта
                    sport_icons = {
                        'cycling': '🚴‍♂️',
                        'running': '🏃‍♂️', 
                        'walking': '🚶‍♂️',
                        'swimming': '🏊‍♂️',
                        'strength': '💪'
                    }
                    sport_icon = sport_icons.get(activity['sport'].lower(), '🏃‍♂️')
                    
                    # Карточка активности
                    st.markdown(f"""
                    <div class="modern-card activity-card">
                        <div class="flex items-center justify-between mb-3">
                            <div class="flex items-center gap-2">
                                <span class="text-2xl">{sport_icon}</span>
                                <div>
                                    <div class="font-semibold">{activity['sport']}</div>
                                    <div class="text-sm text-gray-500">{format_date(activity['date'], 'display')}</div>
                                </div>
                            </div>
                            <div class="text-right">
                                <div class="text-lg font-bold text-blue-600">{activity.get('tss', 0):.0f}</div>
                                <div class="text-xs text-gray-500">TSS</div>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-3 gap-2 text-center">
                            <div>
                                <div class="font-semibold">{activity['distance_km']:.1f}</div>
                                <div class="text-xs text-gray-500">км</div>
                            </div>
                            <div>
                                <div class="font-semibold">{activity['duration_minutes']:.0f}</div>
                                <div class="text-xs text-gray-500">мин</div>
                            </div>
                            <div>
                                <div class="font-semibold">{activity.get('avg_hr', 0):.0f}</div>
                                <div class="text-xs text-gray-500">ЧСС</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# =============================================================================
# 12. ПОЛНАЯ ЗАМЕНА НАВИГАЦИИ (обновить main() в app.py)
# =============================================================================

def main():
    """Обновленная главная функция с современной навигацией"""
    
    st.set_page_config(
        page_title="AI Trainer",
        page_icon="🏃‍♂️",
        layout="wide",
        initial_sidebar_state="collapsed"  # Скрываем боковую панель по умолчанию
    )
    
    # Применяем современные стили
    ModernUI.apply_modern_styles()
    
    # Инициализация состояния
    if 'garmin_client' not in st.session_state:
        st.session_state.garmin_client = GarminClient()
    if 'database' not in st.session_state:
        st.session_state.database = Database()
    
    # ГОРИЗОНТАЛЬНАЯ НАВИГАЦИЯ (вместо sidebar)
    if st.session_state.garmin_client.is_authenticated:
        show_horizontal_navigation()
    
    # Компактная боковая панель (только настройки)
    with st.sidebar:
        show_compact_sidebar()
    
    # Основной контент
    if st.session_state.garmin_client.is_authenticated:
        show_main_content()
    else:
        show_welcome_screen()

def show_horizontal_navigation():
    """Горизонтальная навигация в стиле современных веб-приложений"""
    
    # Определяем разделы
    sections = {
        'dashboard': {'title': 'Обзор', 'icon': '📊'},
        'activities': {'title': 'Активности', 'icon': '🏃‍♂️'},
        'planning': {'title': 'Планирование', 'icon': '📈'},
        'ai_coaching': {'title': 'AI Коучинг', 'icon': '🤖'},
        'data': {'title': 'Данные', 'icon': '⚙️'}
    }
    
    # Текущий раздел
    if 'current_section' not in st.session_state:
        st.session_state.current_section = 'dashboard'
    
    # HTML навигации
    nav_html = """
    <div class="modern-tabs">
    """
    
    for section_id, section_data in sections.items():
        active_class = "active" if section_id == st.session_state.current_section else ""
        nav_html += f"""
        <div class="modern-tab {active_class}" onclick="setActiveSection('{section_id}')">
            <span class="mr-2">{section_data['icon']}</span>
            {section_data['title']}
        </div>
        """
    
    nav_html += """
    </div>
    
    <script>
    function setActiveSection(sectionId) {
        // Отправляем сообщение Streamlit
        window.parent.postMessage({
            type: 'streamlit:componentReady',
            data: {section: sectionId}
        }, '*');
    }
    </script>
    """
    
    st.markdown(nav_html, unsafe_allow_html=True)
    
    # Fallback кнопки для Streamlit (скрытые)
    st.markdown("<div style='display: none;'>", unsafe_allow_html=True)
    cols = st.columns(len(sections))
    for i, (section_id, section_data) in enumerate(sections.items()):
        with cols[i]:
            if st.button(f"{section_data['icon']} {section_data['title']}", 
                        key=f"nav_{section_id}"):
                st.session_state.current_section = section_id
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def show_compact_sidebar():
    """Компактная боковая панель только с настройками"""
    
    st.markdown("### ⚙️ Настройки")
    
    # Подключение к Garmin (компактно)
    with st.expander("🔗 Garmin Connect"):
        show_garmin_connection_compact()
    
    # AI настройки
    with st.expander("🤖 AI Провайдер"):
        show_ai_settings_compact()
    
    # Синхронизация
    with st.expander("🔄 Синхронизация"):
        if st.button("🔄 Синхронизировать", use_container_width=True):
            sync_data(30)
        
        if st.button("🧪 Тестовые данные", use_container_width=True):
            add_test_phase1_data()
    
    # Тема
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Тема:**")
    with col2:
        if st.button("🌙" if not st.session_state.get('dark_mode', False) else "☀️",
                     help="Переключить тему"):
            st.session_state.dark_mode = not st.session_state.get('dark_mode', False)
            st.rerun()

def show_main_content():
    """Отображение основного контента в зависимости от выбранного раздела"""
    
    section = st.session_state.get('current_section', 'dashboard')
    
    if section == 'dashboard':
        show_dashboard()
    elif section == 'activities':
        show_activities_modern()
    elif section == 'planning':
        show_planning_modern()
    elif section == 'ai_coaching':
        show_ai_coaching()
    elif section == 'data':
        show_data_management()

# =============================================================================
# 13. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def filter_activities_data(activities_df, selected_sports, period_days, sort_by):
    """Фильтрация данных активностей"""
    
    # Фильтр по видам спорта
    filtered_df = activities_df[activities_df['sport'].isin(selected_sports)].copy()
    
    # Фильтр по периоду
    cutoff_date = datetime.now() - timedelta(days=period_days)
    filtered_df['date'] = pd.to_datetime(filtered_df['date'])
    filtered_df = filtered_df[filtered_df['date'] >= cutoff_date]
    
    # Сортировка
    if sort_by in filtered_df.columns:
        ascending = False if sort_by in ['distance_km', 'duration_minutes', 'tss'] else True
        filtered_df = filtered_df.sort_values(sort_by, ascending=ascending)
    
    return filtered_df

def show_empty_activities_state():
    """Состояние пустой страницы активностей"""
    
    st.markdown("""
    <div class="modern-card text-center py-12">
        <div class="text-6xl mb-4">🏃‍♂️</div>
        <h3 class="text-xl font-semibold mb-2">Нет данных об активностях</h3>
        <p class="text-gray-600 mb-6">Синхронизируйте данные с Garmin Connect для анализа тренировок</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Синхронизировать данные", type="primary", use_container_width=True):
            sync_data(30)
    
    with col2:
        if st.button("🎮 Загрузить демо-данные", use_container_width=True):
            add_test_phase1_data()

def check_ai_provider_configured():
    """Проверка настройки AI провайдера"""
    
    from config.settings import Settings
    
    provider = st.session_state.get('ai_provider', Settings.DEFAULT_AI_PROVIDER)
    
    if provider == 'openai' and Settings.OPENAI_API_KEY:
        return True
    elif provider == 'anthropic' and Settings.ANTHROPIC_API_KEY:
        return True
    elif provider == 'google' and Settings.GOOGLE_API_KEY:
        return True
    elif provider == 'ollama':
        return True  # Локальный, не требует ключа
    
    return False

# =============================================================================
# 14. ПЛАН ВНЕДРЕНИЯ ДЛЯ CLAUDE CODE
# =============================================================================

"""
ПОСЛЕДОВАТЕЛЬНОСТЬ ВНЕДРЕНИЯ:

1. СОЗДАТЬ НОВЫЕ ФАЙЛЫ:
   - utils/modern_ui.py (класс ModernUI)
   - static/modern_styles.css (если нужен отдельный CSS)

2. ОБНОВИТЬ СУЩЕСТВУЮЩИЕ ФАЙЛЫ:
   
   app.py:
   - Заменить show_dashboard() на улучшенную версию
   - Добавить calculate_current_status()
   - Обновить main() для горизонтальной навигации
   - Добавить show_ai_recommendations_panel()
   - Добавить show_quick_actions()
   
   utils/visualizations.py:
   - Обновить create_banister_chart() на create_modern_banister_chart()
   - Добавить create_status_indicator_chart()
   - Добавить create_modern_dashboard_chart()

3. ТЕСТИРОВАНИЕ:
   - Проверить работу на данных
   - Убедиться в корректности CSS
   - Протестировать на разных разрешениях

4. ОПТИМИЗАЦИЯ:
   - Производительность графиков
   - Время загрузки
   - Отзывчивость интерфейса

ИТОГОВЫЙ РЕЗУЛЬТАТ:
✅ Современный, интуитивный интерфейс
✅ Улучшенная навигация
✅ Контекстные рекомендации
✅ Приоритизация важной информации
✅ Мобильная адаптивность
"""