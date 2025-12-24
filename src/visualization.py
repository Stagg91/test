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
                            vertical_spacing=0.03, subplot_titles=('Price & Indicators', 'Volume'),
                            row_heights=[0.7, 0.3])

        # Candlestick
        fig.add_trace(go.Candlestick(
            x=df['startTime'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='OHLC'
        ), row=1, col=1)

        # Indicators
        colors = ['blue', 'orange', 'purple', 'cyan', 'magenta']
        if indicators:
            for i, ind in enumerate(indicators):
                if ind in df.columns:
                    # Check if it's an overlay (like SMA) or separate (like RSI)
                    # Simple heuristic: If values are close to price, overlay. If 0-100, separate?
                    # For MVP, we overlay everything on Row 1 or 2?
                    # If we don't know, we can assume overlay for Moving Averages/Bands, separate for Oscillators.
                    # But the requirement says "overlay the indicators".
                    # Let's check name.
                    is_oscillator = any(x in ind.lower() for x in ['rsi', 'macd', 'stoch', 'adx'])

                    if is_oscillator:
                        # Add a 3rd row dynamically? Or just put in main for now with secondary axis?
                        # Let's stick to overlaying purely price-based ones (SMA, EMA, BB)
                        if not is_oscillator:
                            fig.add_trace(go.Scatter(
                                x=df['startTime'],
                                y=df[ind],
                                line=dict(color=colors[i % len(colors)], width=1),
                                name=ind
                            ), row=1, col=1)
                    else:
                        # SMA, EMA, BB
                        fig.add_trace(go.Scatter(
                            x=df['startTime'],
                            y=df[ind],
                            line=dict(color=colors[i % len(colors)], width=1),
                            name=ind
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
        fig.add_trace(go.Bar(
            x=df['startTime'],
            y=df['volume'],
            name='Volume',
            marker_color='grey'
        ), row=2, col=1)

        # Layout
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template='plotly_dark',
            height=800,
            margin=dict(l=50, r=50, t=50, b=50)
        )

        # Convert to JSON
        return json.loads(fig.to_json())
