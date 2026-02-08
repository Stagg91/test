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
        :param trades: List of trade dicts
        :param indicators: List of indicator names (columns in df)
        """
        from src.database import SessionLocal, Indicator

        # Categorize Indicators
        overlays = []
        subplots = []

        if indicators:
            db = SessionLocal()
            all_inds = db.query(Indicator).all()
            db.close()

            for col_name in indicators:
                if col_name not in df.columns: continue

                is_ov = False
                matched = False

                # Heuristic Matching
                for ind in all_inds:
                    # BBANDS Special Case (creates BBL, BBM, BBU)
                    if ind.name == 'bbands':
                        if col_name.startswith('BBL') or col_name.startswith('BBM') or col_name.startswith('BBU'):
                            is_ov = ind.is_overlay
                            matched = True
                            break

                    if col_name.startswith(ind.name.upper()):
                        is_ov = ind.is_overlay
                        matched = True
                        break

                if matched:
                    if is_ov: overlays.append(col_name)
                    else: subplots.append(col_name)
                else:
                    # Default heuristic
                    if any(x in col_name for x in ['RSI', 'MACD', 'ADX', 'ATR', 'STOCH']):
                        subplots.append(col_name)
                    else:
                        overlays.append(col_name)

        # Setup Rows
        # Row 1: Price + Overlays
        # Row 2: Volume
        # Row 3+: Subplots

        num_subplots = len(subplots)
        total_rows = 2 + num_subplots

        # Heights: Main=50%, Vol=15%, Rest=35% divided
        base_heights = [0.5, 0.15]
        if num_subplots > 0:
            sub_h = 0.35 / num_subplots
            base_heights.extend([sub_h] * num_subplots)
        else:
            base_heights = [0.7, 0.3] # Fallback if no subplots

        fig = make_subplots(
            rows=total_rows, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.02,
            row_heights=base_heights
        )

        # --- Row 1: Price ---
        fig.add_trace(go.Candlestick(
            x=df['startTime'],
            open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name='OHLC'
        ), row=1, col=1)

        # Overlays
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        for i, col in enumerate(overlays):
            fig.add_trace(go.Scatter(
                x=df['startTime'], y=df[col],
                line=dict(width=1, color=colors[i % len(colors)]),
                name=col
            ), row=1, col=1)

        # Signals
        if 'signal' in df.columns:
            buys = df[df['signal'] == 1]
            sells = df[df['signal'] == -1]
            if not buys.empty:
                fig.add_trace(go.Scatter(
                    x=buys['startTime'], y=buys['low']*0.99,
                    mode='markers', marker=dict(symbol='triangle-up', size=10, color='green'),
                    name='Buy'
                ), row=1, col=1)
            if not sells.empty:
                fig.add_trace(go.Scatter(
                    x=sells['startTime'], y=sells['high']*1.01,
                    mode='markers', marker=dict(symbol='triangle-down', size=10, color='red'),
                    name='Sell'
                ), row=1, col=1)

        # --- Row 2: Volume ---
        fig.add_trace(go.Bar(
            x=df['startTime'], y=df['volume'],
            name='Volume', marker_color='#555'
        ), row=2, col=1)

        # --- Row 3+: Subplots ---
        for i, col in enumerate(subplots):
            r = 3 + i
            fig.add_trace(go.Scatter(
                x=df['startTime'], y=df[col],
                line=dict(width=1, color=colors[i % len(colors)]),
                name=col
            ), row=r, col=1)

            # Guidelines
            if 'RSI' in col:
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=r, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=r, col=1)

        # Layout
        fig.update_layout(
            template='plotly_dark',
            height=600 + (num_subplots * 150),
            margin=dict(l=50, r=50, t=50, b=50),
            xaxis_rangeslider_visible=False
        )

        # Hide X-axes for upper rows
        for i in range(1, total_rows):
            fig.update_xaxes(showticklabels=False, row=i, col=1)
        # Show X-axis for last row
        fig.update_xaxes(showticklabels=True, row=total_rows, col=1)

        return json.loads(fig.to_json())
