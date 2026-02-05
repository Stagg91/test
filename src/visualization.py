import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json

class ChartGenerator:
    @staticmethod
    def generate_chart_json(df: pd.DataFrame, trades: list = None, indicators: list = None):
        """
        Generates a Plotly JSON for the strategy backtest.
        :param df: DataFrame with OHLCV and indicator columns
        :param trades: List of trade dicts (from BacktestResult)
        :param indicators: List of indicator names (columns in df) to overlay
        """
        # Create Subplots: Row 1 = Price + Indicators, Row 2 = Volume, Row 3 = Equity (if available)
        # For simplicity, let's do: Row 1 Main (Price), Row 2 Volume.

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.02, subplot_titles=('Price & Indicators', 'Volume'),
                            row_heights=[0.8, 0.2]) # Optimize space

        # Candlestick (Green/Red styling)
        fig.add_trace(go.Candlestick(
            x=df['startTime'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='OHLC',
            increasing_line_color='#26a69a', increasing_fillcolor='#26a69a',
            decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350'
        ), row=1, col=1)

        # Indicators
        # Distinct Colors for visibility
        colors = ['#FFD700', '#00BFFF', '#FF4500', '#32CD32', '#DA70D6']

        if indicators:
            for i, ind in enumerate(indicators):
                if ind in df.columns:
                    is_oscillator = any(x in ind.lower() for x in ['rsi', 'macd', 'stoch', 'adx', 'atr'])

                    # Logic: Overlay Price indicators (EMA, SMA, BB) on Row 1.
                    # Ignore Oscillators for now to avoid cluttering price view (user asked for clear visuals).
                    # OR, we could add a 3rd subplot, but simpler is cleaner.

                    if not is_oscillator:
                        fig.add_trace(go.Scatter(
                            x=df['startTime'],
                            y=df[ind],
                            line=dict(color=colors[i % len(colors)], width=1.5),
                            name=ind,
                            opacity=0.8
                        ), row=1, col=1)

        # Trades (Markers)
        # Trades might be vector-based signals in DF or a list of executed trades.
        # If we have a 'signal' column in DF:
        if 'signal' in df.columns:
            # Buy Signals
            buys = df[df['signal'] == 1]
            if not buys.empty:
                fig.add_trace(go.Scatter(
                    x=buys['startTime'],
                    y=buys['low'] * 0.99,
                    mode='markers',
                    marker=dict(symbol='triangle-up', size=10, color='green'),
                    name='Buy Signal'
                ), row=1, col=1)

            # Sell Signals
            sells = df[df['signal'] == -1]
            if not sells.empty:
                fig.add_trace(go.Scatter(
                    x=sells['startTime'],
                    y=sells['high'] * 1.01,
                    mode='markers',
                    marker=dict(symbol='triangle-down', size=10, color='red'),
                    name='Sell Signal'
                ), row=1, col=1)

        # Volume
        # Color volume bars based on close vs open?
        # Simple implementation:
        fig.add_trace(go.Bar(
            x=df['startTime'],
            y=df['volume'],
            name='Volume',
            marker_color='#787b86',
            opacity=0.5
        ), row=2, col=1)

        # Layout
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template='plotly_dark',
            height=600, # slightly shorter to fit screens
            margin=dict(l=20, r=20, t=40, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # Convert to JSON
        return json.loads(fig.to_json())
