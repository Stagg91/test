import google.generativeai as genai
import os
import requests
import random

class AISentimentAgent:
    def __init__(self, gemini_api_key=None):
        self.api_key = gemini_api_key
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Use 1.5 Flash as requested/newer standard, fallback to pro if needed
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def analyze_text(self, text):
        """
        Analyzes text using Gemini to determine sentiment (Bullish/Bearish/Neutral).
        """
        if not self.model:
            return "NEUTRAL" # Default if no key

        try:
            prompt = f"Analyze the sentiment of the following crypto news text. Return only one word: BULLISH, BEARISH, or NEUTRAL.\n\nText: {text}"
            response = self.model.generate_content(prompt)
            return response.text.strip().upper()
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return "NEUTRAL"

    def fetch_crypto_news(self):
        """
        Fetches latest crypto news.
        Tries to fetch from a public RSS feed or API.
        """
        try:
            # CoinDesk RSS Feed
            url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                # Simple parsing of XML/RSS without extra deps like feedparser if possible,
                # otherwise just regex or simple find.
                # Since we don't have feedparser in requirements, let's just grab titles coarsely
                import re
                content = response.text
                titles = re.findall(r'<title>(.*?)</title>', content)
                # Filter out short/generic titles
                return [t for t in titles if len(t) > 20][:5]
        except Exception as e:
            print(f"Error fetching news: {e}")

        # Fallback if fetch fails
        headlines = [
            "Bitcoin market shows resilience amidst volatility.",
            "New regulations could impact crypto trading volumes.",
            "Ethereum upgrades expected to improve scalability."
        ]
        return headlines

    def get_market_sentiment(self):
        """
        Aggregates sentiment from fetched news.
        """
        news = self.fetch_crypto_news()
        sentiments = []

        print(f"Analyzing {len(news)} news items for sentiment...")

        for headline in news:
            # If we don't have an API key, we might just randomize or use a heuristic
            # But the requirement is to use Gemini IF available.
            if self.model:
                sentiment = self.analyze_text(headline)
            else:
                # Basic Heuristic fallback if no AI Key
                lower = headline.lower()
                if any(x in lower for x in ['surge', 'high', 'growth', 'bull', 'adoption']):
                    sentiment = "BULLISH"
                elif any(x in lower for x in ['crash', 'drop', 'ban', 'bear', 'regulation']):
                    sentiment = "BEARISH"
                else:
                    sentiment = "NEUTRAL"

            sentiments.append(sentiment)

        # Simple majority vote
        bullish = sentiments.count("BULLISH")
        bearish = sentiments.count("BEARISH")

        print(f"Sentiment Result: {bullish} Bullish, {bearish} Bearish")

        if bullish > bearish:
            return "BULLISH"
        elif bearish > bullish:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def interpret_strategy_prompt(self, prompt: str):
        """
        Uses Gemini to translate a natural language strategy goal into backtest parameters.
        Returns a dict of configs.
        """
        if not self.model:
            # Fallback mock logic if no API key
            return {
                "rsi_enabled": True,
                "rsi_lower": 30,
                "rsi_upper": 70,
                "macd_enabled": "scalp" in prompt.lower()
            }

        try:
            query = f"""
            You are a crypto trading expert. Translate the following user goal into a JSON configuration for a trading bot backtester.
            Goal: "{prompt}"

            Output strictly valid JSON with these keys (use reasonable values based on the goal):
            - rsi_enabled (bool)
            - rsi_lower_start (int)
            - rsi_lower_stop (int)
            - rsi_lower_step (int)
            - macd_enabled (bool)
            - symbol (e.g. BTCUSDT, ETHUSDT - infer from prompt or default BTCUSDT)

            JSON:
            """
            response = self.model.generate_content(query)
            # Cleanup JSON block markers if present
            text = response.text.replace("```json", "").replace("```", "").strip()
            import json
            config = json.loads(text)
            return config
        except Exception as e:
            print(f"AI Config Error: {e}")
            return {
                "rsi_enabled": True,
                "rsi_lower_start": 20,
                "rsi_lower_stop": 40,
                "rsi_lower_step": 5,
                "macd_enabled": False,
                "symbol": "BTCUSDT"
            }

    def generate_strategy_code(self, prompt: str) -> str:
        """
        Generates Python code for a trading strategy based on a prompt.
        """
        if not self.model:
            return ""

        query = f"""
        You are an expert algorithmic trading developer. Write a Python class named `AIStrategy` that inherits from `BaseStrategy`.

        The user wants: "{prompt}"

        Requirements:
        1. Import `BaseStrategy` from `src.strategies.base` (assume it's available).
        2. Implement `on_candle(self, df: pd.DataFrame) -> dict` method.
        3. The input `df` has columns: `open`, `high`, `low`, `close`, `volume` (all numeric).
        4. You MUST implement logic using pandas or numpy to calculate indicators inside the method (do not assume TA-Lib is installed, use pandas directly or calculate manually).
        5. Return a dictionary with:
           - "signal": "buy", "sell", or "hold"
           - "confidence": float 0.0-1.0
           - "metadata": dict with calculated indicator values.
        6. Do not include markdown formatting like ```python. Just the code.
        7. Ensure the code is syntactically correct and robust (handle empty dataframes check).
        8. IMPORTANT: Include the following imports at the top of the code to ensure it runs in the restricted environment:
           import sys
           import os
           if os.getcwd() not in sys.path: sys.path.append(os.getcwd())

        Code:
        """
        try:
            response = self.model.generate_content(query)
            code = response.text.replace("```python", "").replace("```", "").strip()
            return code
        except Exception as e:
            print(f"Strategy Gen Error: {e}")
            return ""

    def mutate_strategy_code(self, code: str, feedback: str) -> str:
        """
        Modifies an existing strategy code based on feedback (performance results).
        """
        if not self.model:
            return code

        query = f"""
        You are an expert algorithmic trading developer optimization engine.

        Here is an existing Python strategy class:

        {code}

        Performance/Feedback: "{feedback}"

        Task:
        1. Analyze the code and the feedback.
        2. Make subtle or significant changes to the logic to improve performance (e.g. change thresholds, add a filter, change indicator period).
        3. Keep the class name `AIStrategy` and structure.
        4. Return ONLY the full updated Python code. No markdown.
        """
        try:
            response = self.model.generate_content(query)
            new_code = response.text.replace("```python", "").replace("```", "").strip()
            return new_code
        except Exception as e:
            print(f"Strategy Mutation Error: {e}")
            return code
