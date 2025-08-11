import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from plotly.subplots import make_subplots

class Visualizations:
    
    @staticmethod
    def create_activity_timeline(activities_df):
        """График активностей по времени"""
        if activities_df.empty:
            return go.Figure()
        
        fig = px.scatter(
            activities_df, 
            x='date', 
            y='duration_minutes',
            color='sport',
            size='distance_km',
            title="Временная шкала активностей"
        )
        
        return fig
    
    @staticmethod
    def create_training_load_chart(tss_data, dates):
        """График тренировочной нагрузки"""
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=dates,
            y=tss_data,
            mode='lines+markers',
            name='TSS',
            line=dict(color='blue')
        ))
        
        fig.update_layout(
            title="Тренировочная нагрузка (TSS)",
            xaxis_title="Дата",
            yaxis_title="TSS"
        )
        
        return fig
    
    @staticmethod
    def create_hrv_trend(hrv_data, dates):
        """График тренда HRV"""
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=dates,
            y=hrv_data,
            mode='lines+markers',
            name='RMSSD',
            line=dict(color='green')
        ))
        
        fig.update_layout(
            title="Тренд HRV (RMSSD)",
            xaxis_title="Дата",
            yaxis_title="RMSSD (мс)"
        )
        
        return fig
    
    @staticmethod
    def create_banister_chart(dates, ctl_values, atl_values, tsb_values):
        """График модели Банистера: CTL, ATL, TSB"""
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("Тренировочная нагрузка (CTL/ATL)", "Форма спортсмена (TSB)"),
            row_heights=[0.6, 0.4]
        )
        
        # График CTL и ATL
        fig.add_trace(
            go.Scatter(
                x=dates, y=ctl_values,
                mode='lines',
                name='CTL (Фитнес)',
                line=dict(color='blue', width=2),
                fill=None
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=dates, y=atl_values,
                mode='lines',
                name='ATL (Усталость)',
                line=dict(color='red', width=2),
                fill=None
            ),
            row=1, col=1
        )
        
        # График TSB с цветовой заливкой
        colors = []
        for tsb in tsb_values:
            if tsb > 5:
                colors.append('rgba(0, 255, 0, 0.3)')  # Зелёный - отличная форма
            elif tsb > -10:
                colors.append('rgba(255, 255, 0, 0.3)')  # Жёлтый - хорошая форма
            elif tsb > -30:
                colors.append('rgba(255, 165, 0, 0.3)')  # Оранжевый - усталость
            else:
                colors.append('rgba(255, 0, 0, 0.3)')  # Красный - переутомление
        
        fig.add_trace(
            go.Scatter(
                x=dates, y=tsb_values,
                mode='lines',
                name='TSB (Форма)',
                line=dict(color='purple', width=3),
                fill='tozeroy'
            ),
            row=2, col=1
        )
        
        # Добавляем горизонтальные линии-ориентиры для TSB
        fig.add_hline(y=5, line_dash="dash", line_color="green", 
                      annotation_text="Отличная форма", row=2, col=1)
        fig.add_hline(y=-10, line_dash="dash", line_color="orange",
                      annotation_text="Усталость", row=2, col=1)
        fig.add_hline(y=-30, line_dash="dash", line_color="red",
                      annotation_text="Переутомление", row=2, col=1)
        
        fig.update_layout(
            height=600,
            title="Модель Банистера: Анализ фитнеса и усталости",
            showlegend=True,
            hovermode='x unified'
        )
        
        fig.update_yaxes(title_text="Тренировочная нагрузка", row=1, col=1)
        fig.update_yaxes(title_text="TSB", row=2, col=1)
        fig.update_xaxes(title_text="Дата", row=2, col=1)
        
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