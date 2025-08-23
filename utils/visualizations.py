import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from plotly.subplots import make_subplots

class Visualizations:
    
    @staticmethod
    def create_modern_dashboard_chart(activities_df, current_metrics):
        """Современный дашборд-график с метриками и трендами"""
        if activities_df.empty:
            return go.Figure()
        
        # Подготовка данных за последние 30 дней
        recent_data = activities_df.head(30)
        dates = recent_data['date'].tolist()
        tss_data = recent_data['tss'].fillna(0).tolist()
        
        # Создаем subplot с несколькими графиками
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                "📈 TSS за 30 дней", "⚡ Текущая форма (TSB)",
                "🔄 Фитнес/Усталость", "📊 Недельная нагрузка", 
                "🎯 Зоны интенсивности", "💓 Частота тренировок"
            ),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": True}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]],
            vertical_spacing=0.08,
            horizontal_spacing=0.05,
            row_heights=[0.35, 0.35, 0.3]
        )
        
        # 1. TSS за 30 дней с градиентом
        fig.add_trace(
            go.Scatter(
                x=dates, y=tss_data,
                mode='lines+markers',
                name='TSS',
                line=dict(color='#3B82F6', width=3),
                marker=dict(size=6, color='#3B82F6'),
                fill='tonexty',
                fillcolor='rgba(59, 130, 246, 0.1)'
            ),
            row=1, col=1
        )
        
        # 2. Текущая форма TSB с цветовым кодированием
        tsb = current_metrics.get('tsb', 0)
        tsb_color = '#10B981' if tsb > 5 else '#F59E0B' if tsb > -10 else '#EF4444' if tsb > -30 else '#DC2626'
        
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=tsb,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "TSB", 'font': {'size': 16}},
                gauge={'axis': {'range': [-50, 30]},
                       'bar': {'color': tsb_color},
                       'steps': [
                           {'range': [-50, -30], 'color': 'rgba(220, 38, 38, 0.2)'},
                           {'range': [-30, -10], 'color': 'rgba(245, 158, 11, 0.2)'},
                           {'range': [-10, 5], 'color': 'rgba(156, 163, 175, 0.2)'},
                           {'range': [5, 30], 'color': 'rgba(16, 185, 129, 0.2)'}
                       ],
                       'threshold': {'line': {'color': "red", 'width': 4},
                                   'thickness': 0.75, 'value': 0}}
            ),
            row=1, col=2
        )
        
        # 3. Фитнес/Усталость тренд
        if len(dates) >= 7:  # Достаточно данных для расчета
            ctl_data = [current_metrics.get('ctl', 0)] * len(dates)
            atl_data = [current_metrics.get('atl', 0)] * len(dates)
            
            fig.add_trace(
                go.Scatter(
                    x=dates, y=ctl_data,
                    mode='lines',
                    name='Фитнес (CTL)',
                    line=dict(color='#3B82F6', width=2),
                    yaxis='y'
                ),
                row=2, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=dates, y=atl_data,
                    mode='lines',
                    name='Усталость (ATL)',
                    line=dict(color='#EF4444', width=2),
                    yaxis='y2'
                ),
                row=2, col=1
            )
        
        # 4. Недельная нагрузка (барчарт)
        weekly_tss = recent_data.groupby(recent_data['date'].dt.isocalendar().week)['tss'].sum()
        week_labels = [f"Нед {w}" for w in weekly_tss.index]
        
        fig.add_trace(
            go.Bar(
                x=week_labels,
                y=weekly_tss.values,
                name='Недельный TSS',
                marker_color='#8B5CF6',
                opacity=0.8
            ),
            row=2, col=2
        )
        
        # 5. Зоны интенсивности (пайчарт)
        intensity_zones = {
            'Легкие': len(recent_data[recent_data['tss'] < 100]),
            'Средние': len(recent_data[(recent_data['tss'] >= 100) & (recent_data['tss'] < 200)]),
            'Тяжелые': len(recent_data[recent_data['tss'] >= 200])
        }
        
        fig.add_trace(
            go.Pie(
                labels=list(intensity_zones.keys()),
                values=list(intensity_zones.values()),
                hole=0.4,
                marker=dict(colors=['#10B981', '#F59E0B', '#EF4444']),
                textinfo='label+percent',
                textposition='inside'
            ),
            row=3, col=1
        )
        
        # 6. Частота тренировок по дням недели
        recent_data['weekday'] = recent_data['date'].dt.day_name()
        weekday_counts = recent_data['weekday'].value_counts().reindex([
            'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
        ], fill_value=0)
        weekday_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        
        fig.add_trace(
            go.Bar(
                x=weekday_names,
                y=weekday_counts.values,
                name='Тренировок',
                marker_color='#06B6D4',
                opacity=0.8
            ),
            row=3, col=2
        )
        
        # Обновляем layout с современным дизайном
        fig.update_layout(
            title={
                'text': "🏃‍♂️ Современный дашборд тренировок",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 24, 'color': '#1F2937'}
            },
            height=900,
            showlegend=False,
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=40, r=40, t=80, b=40)
        )
        
        # Обновляем оси для современного вида
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        
        return fig
    
    @staticmethod
    def create_activity_timeline(activities_df):
        """Современный график активностей по времени с интерактивными элементами"""
        if activities_df.empty:
            return go.Figure()
        
        # Создаем цветовую схему для видов спорта
        sport_colors = {
            'running': '#EF4444',
            'cycling': '#3B82F6',
            'swimming': '#06B6D4',
            'walking': '#10B981',
            'hiking': '#F59E0B',
            'gym': '#8B5CF6'
        }
        
        fig = px.scatter(
            activities_df, 
            x='date', 
            y='duration_minutes',
            color='sport',
            size='distance_km',
            title="📅 Временная шкала активностей",
            color_discrete_map=sport_colors,
            hover_data={
                'tss': ':.0f',
                'distance_km': ':.1f',
                'duration_minutes': ':.0f'
            }
        )
        
        # Обновляем layout для современного вида
        fig.update_layout(
            title={
                'text': "📅 Временная шкала активностей",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#1F2937'}
            },
            xaxis_title="Дата",
            yaxis_title="Длительность (мин)",
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        # Стилизация осей
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        
        return fig
    
    @staticmethod
    def create_training_load_chart(tss_data, dates):
        """Современный график тренировочной нагрузки с зонами интенсивности"""
        fig = go.Figure()
        
        # Добавляем цветовые зоны как фон
        max_tss = max(tss_data) if tss_data else 300
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=0, y1=100,
            fillcolor="rgba(16, 185, 129, 0.1)", line=dict(width=0),
            name="Легкая нагрузка"
        )
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=100, y1=200,
            fillcolor="rgba(245, 158, 11, 0.1)", line=dict(width=0),
            name="Средняя нагрузка"
        )
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=200, y1=max_tss,
            fillcolor="rgba(239, 68, 68, 0.1)", line=dict(width=0),
            name="Высокая нагрузка"
        )
        
        # Основная линия TSS с градиентом
        fig.add_trace(go.Scatter(
            x=dates,
            y=tss_data,
            mode='lines+markers',
            name='TSS',
            line=dict(color='#3B82F6', width=3),
            marker=dict(size=8, color='#3B82F6', line=dict(width=2, color='white')),
            fill='tonexty',
            fillcolor='rgba(59, 130, 246, 0.2)',
            hovertemplate='<b>TSS</b><br>%{y}<br>%{x}<extra></extra>'
        ))
        
        # Добавляем горизонтальные линии-ориентиры
        fig.add_hline(y=100, line_dash="dot", line_color="#10B981", line_width=1,
                      annotation_text="🟢 Легкая нагрузка", annotation_position="right")
        fig.add_hline(y=200, line_dash="dot", line_color="#F59E0B", line_width=1,
                      annotation_text="🟡 Средняя нагрузка", annotation_position="right")
        
        fig.update_layout(
            title={
                'text': "📈 Тренировочная нагрузка (TSS)",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#1F2937'}
            },
            xaxis_title="Дата",
            yaxis_title="TSS",
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            hovermode='x unified'
        )
        
        # Стилизация осей
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        
        return fig
    
    @staticmethod
    def create_hrv_trend(hrv_data, dates):
        """Современный график тренда HRV с зонами восстановления"""
        fig = go.Figure()
        
        # Вычисляем среднее и стандартное отклонение для зон
        if hrv_data:
            hrv_mean = sum(hrv_data) / len(hrv_data)
            hrv_std = (sum((x - hrv_mean) ** 2 for x in hrv_data) / len(hrv_data)) ** 0.5
            
            # Добавляем цветовые зоны восстановления
            fig.add_shape(
                type="rect", x0=dates[0], x1=dates[-1], 
                y0=hrv_mean + hrv_std, y1=max(hrv_data) + 10,
                fillcolor="rgba(16, 185, 129, 0.2)", line=dict(width=0),
                name="Отличное восстановление"
            )
            fig.add_shape(
                type="rect", x0=dates[0], x1=dates[-1], 
                y0=hrv_mean, y1=hrv_mean + hrv_std,
                fillcolor="rgba(245, 158, 11, 0.2)", line=dict(width=0),
                name="Хорошее восстановление"
            )
            fig.add_shape(
                type="rect", x0=dates[0], x1=dates[-1], 
                y0=hrv_mean - hrv_std, y1=hrv_mean,
                fillcolor="rgba(249, 115, 22, 0.2)", line=dict(width=0),
                name="Среднее восстановление"
            )
            fig.add_shape(
                type="rect", x0=dates[0], x1=dates[-1], 
                y0=0, y1=hrv_mean - hrv_std,
                fillcolor="rgba(239, 68, 68, 0.2)", line=dict(width=0),
                name="Плохое восстановление"
            )
            
            # Добавляем линию среднего значения
            fig.add_hline(y=hrv_mean, line_dash="dash", line_color="#6B7280", line_width=2,
                          annotation_text=f"Среднее: {hrv_mean:.1f}мс", annotation_position="right")
        
        # Основная линия HRV с градиентом
        fig.add_trace(go.Scatter(
            x=dates,
            y=hrv_data,
            mode='lines+markers',
            name='RMSSD',
            line=dict(color='#10B981', width=3),
            marker=dict(size=8, color='#10B981', line=dict(width=2, color='white')),
            fill='tonexty',
            fillcolor='rgba(16, 185, 129, 0.2)',
            hovertemplate='<b>HRV (RMSSD)</b><br>%{y:.1f}мс<br>%{x}<extra></extra>'
        ))
        
        fig.update_layout(
            title={
                'text': "💓 Тренд HRV (RMSSD) - Восстановление",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'color': '#1F2937'}
            },
            xaxis_title="Дата",
            yaxis_title="RMSSD (мс)",
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=False,
            hovermode='x unified'
        )
        
        # Стилизация осей
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)')
        
        return fig
    
    @staticmethod
    def create_banister_chart(dates, ctl_values, atl_values, tsb_values):
        """Современный график модели Банистера: CTL, ATL, TSB с цветовыми зонами"""
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.12,
            subplot_titles=(
                "💪 Тренировочная нагрузка (CTL/ATL)", 
                "⚡ Форма спортсмена (TSB)"
            ),
            row_heights=[0.55, 0.45]
        )
        
        # График CTL с градиентной заливкой
        fig.add_trace(
            go.Scatter(
                x=dates, y=ctl_values,
                mode='lines',
                name='CTL (Фитнес)',
                line=dict(color='#3B82F6', width=3),
                fill='tonexty',
                fillcolor='rgba(59, 130, 246, 0.1)',
                hovertemplate='<b>Фитнес</b><br>%{y:.1f}<br>%{x}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # График ATL с градиентной заливкой
        fig.add_trace(
            go.Scatter(
                x=dates, y=atl_values,
                mode='lines',
                name='ATL (Усталость)',
                line=dict(color='#EF4444', width=3),
                fill='tonexty',
                fillcolor='rgba(239, 68, 68, 0.1)',
                hovertemplate='<b>Усталость</b><br>%{y:.1f}<br>%{x}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # TSB с динамической цветовой заливкой
        tsb_colors = []
        for i, tsb in enumerate(tsb_values):
            if tsb > 5:
                tsb_colors.append('rgba(16, 185, 129, 0.7)')  # Зеленый - отличная форма
            elif tsb > -10:
                tsb_colors.append('rgba(245, 158, 11, 0.7)')  # Желтый - хорошая форма  
            elif tsb > -30:
                tsb_colors.append('rgba(249, 115, 22, 0.7)')  # Оранжевый - усталость
            else:
                tsb_colors.append('rgba(239, 68, 68, 0.7)')  # Красный - переутомление
        
        # Добавляем цветовые зоны TSB как фон
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=5, y1=30,
            fillcolor="rgba(16, 185, 129, 0.1)", line=dict(width=0),
            row=2, col=1
        )
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=-10, y1=5,
            fillcolor="rgba(245, 158, 11, 0.1)", line=dict(width=0),
            row=2, col=1
        )
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=-30, y1=-10,
            fillcolor="rgba(249, 115, 22, 0.1)", line=dict(width=0),
            row=2, col=1
        )
        fig.add_shape(
            type="rect", x0=dates[0], x1=dates[-1], y0=-50, y1=-30,
            fillcolor="rgba(239, 68, 68, 0.1)", line=dict(width=0),
            row=2, col=1
        )
        
        # График TSB с толстой линией
        fig.add_trace(
            go.Scatter(
                x=dates, y=tsb_values,
                mode='lines+markers',
                name='TSB (Форма)',
                line=dict(color='#8B5CF6', width=4),
                marker=dict(size=8, color=tsb_colors, line=dict(width=2, color='white')),
                fill='tozeroy',
                fillcolor='rgba(139, 92, 246, 0.2)',
                hovertemplate='<b>TSB</b><br>%{y:.1f}<br>%{x}<br><extra></extra>'
            ),
            row=2, col=1
        )
        
        # Добавляем горизонтальные линии-ориентиры с аннотациями
        fig.add_hline(
            y=5, line_dash="dot", line_color="#10B981", line_width=2,
            annotation_text="🟢 Отличная форма", annotation_position="right",
            row=2, col=1
        )
        fig.add_hline(
            y=-10, line_dash="dot", line_color="#F59E0B", line_width=2,
            annotation_text="🟡 Усталость", annotation_position="right",
            row=2, col=1
        )
        fig.add_hline(
            y=-30, line_dash="dot", line_color="#EF4444", line_width=2,
            annotation_text="🔴 Переутомление", annotation_position="right",
            row=2, col=1
        )
        
        # Современный layout
        fig.update_layout(
            height=700,
            title={
                'text': "📊 Модель Банистера: Анализ фитнеса и усталости",
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'color': '#1F2937'}
            },
            showlegend=True,
            hovermode='x unified',
            font=dict(family="Inter, -apple-system, sans-serif", size=12),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="rgba(156, 163, 175, 0.3)",
                borderwidth=1
            )
        )
        
        # Стилизация осей
        fig.update_yaxes(
            title_text="Тренировочная нагрузка", 
            showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)',
            zeroline=True, zerolinewidth=2, zerolinecolor='rgba(156, 163, 175, 0.4)',
            row=1, col=1
        )
        fig.update_yaxes(
            title_text="TSB", 
            showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)',
            zeroline=True, zerolinewidth=2, zerolinecolor='rgba(156, 163, 175, 0.4)',
            row=2, col=1
        )
        fig.update_xaxes(
            title_text="Дата",
            showgrid=True, gridwidth=1, gridcolor='rgba(156, 163, 175, 0.2)',
            row=2, col=1
        )
        
        return fig
    
    @staticmethod
    def create_performance_prediction_chart(dates, fitness, fatigue, performance):
        """График предсказания производительности"""
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=dates, y=fitness,
            mode='lines',
            name='Фитнес',
            line=dict(color='blue', width=2),
            yaxis='y'
        ))
        
        fig.add_trace(go.Scatter(
            x=dates, y=fatigue,
            mode='lines',
            name='Усталость',
            line=dict(color='red', width=2),
            yaxis='y'
        ))
        
        fig.add_trace(go.Scatter(
            x=dates, y=performance,
            mode='lines',
            name='Производительность',
            line=dict(color='green', width=3),
            yaxis='y2'
        ))
        
        fig.update_layout(
            title="Модель Банистера: Фитнес, Усталость и Производительность",
            xaxis_title="Дата",
            yaxis=dict(title="Фитнес/Усталость", side="left"),
            yaxis2=dict(title="Производительность", side="right", overlaying="y"),
            hovermode='x unified',
            height=500
        )
        
        return fig
    
    @staticmethod
    def create_tss_distribution_chart(activities_df):
        """Распределение TSS по видам спорта"""
        if activities_df.empty or 'tss' not in activities_df.columns:
            return go.Figure()
        
        fig = px.box(
            activities_df,
            x='sport',
            y='tss',
            title="Распределение TSS по видам спорта",
            labels={'sport': 'Вид спорта', 'tss': 'TSS'}
        )
        
        fig.update_layout(height=400)
        return fig
    
    @staticmethod
    def create_weekly_tss_chart(activities_df):
        """Недельная статистика TSS"""
        if activities_df.empty:
            return go.Figure()
        
        # Группируем по неделям
        activities_df_copy = activities_df.copy()
        activities_df_copy['week'] = pd.to_datetime(activities_df_copy['date']).dt.isocalendar().week
        activities_df_copy['year'] = pd.to_datetime(activities_df_copy['date']).dt.year
        activities_df_copy['year_week'] = activities_df_copy['year'].astype(str) + '-W' + activities_df_copy['week'].astype(str).str.zfill(2)
        
        weekly_tss = activities_df_copy.groupby('year_week')['tss'].sum().reset_index()
        
        fig = px.bar(
            weekly_tss,
            x='year_week',
            y='tss',
            title="Недельная тренировочная нагрузка (TSS)",
            labels={'year_week': 'Неделя', 'tss': 'Недельный TSS'}
        )
        
        fig.update_layout(height=400, xaxis_tickangle=-45)
        return fig