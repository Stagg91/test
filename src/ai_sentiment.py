from google import genai
import os
import requests
import random
import feedparser
import json

class AISentimentAgent:
    def __init__(self, gemini_api_key=None):
        self.api_key = gemini_api_key
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model = "gemini-1.5-flash"
        else:
            self.client = None

    def analyze_text(self, text):
        """
        Analyzes text using Gemini to determine sentiment (Bullish/Bearish/Neutral).
        """
        if not self.client:
            return "NEUTRAL"

        try:
            prompt = f"Analyze the sentiment of the following crypto news text. Return only one word: BULLISH, BEARISH, or NEUTRAL.\n\nText: {text}"
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            return response.text.strip().upper()
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return "NEUTRAL"

    def fetch_crypto_news(self):
        """
        Fetches latest crypto news from multiple RSS feeds.
        """
        feeds = [
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cointelegraph.com/rss",
            "https://cryptoslate.com/feed/"
        ]

        all_headlines = []

        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    for entry in feed.entries[:3]:
                        if hasattr(entry, 'title'):
                             all_headlines.append(entry.title)
            except Exception as e:
                print(f"Error fetching feed {feed_url}: {e}")

        if not all_headlines:
             all_headlines = [
                "Bitcoin market shows resilience amidst volatility.",
                "New regulations could impact crypto trading volumes.",
                "Ethereum upgrades expected to improve scalability."
            ]
        return list(set(all_headlines))[:10]

    def get_market_sentiment(self):
        """
        Aggregates sentiment from fetched news.
        """
        news = self.fetch_crypto_news()
        sentiments = []

        print(f"Analyzing {len(news)} news items for sentiment...")

        for headline in news:
            if self.client:
                sentiment = self.analyze_text(headline)
            else:
                lower = headline.lower()
                if any(x in lower for x in ['surge', 'high', 'growth', 'bull', 'adoption']):
                    sentiment = "BULLISH"
                elif any(x in lower for x in ['crash', 'drop', 'ban', 'bear', 'regulation']):
                    sentiment = "BEARISH"
                else:
                    sentiment = "NEUTRAL"

            sentiments.append(sentiment)

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
        if not self.client:
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
            response = self.client.models.generate_content(
                model=self.model,
                contents=query
            )
            text = response.text.replace("```json", "").replace("```", "").strip()
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

    # Legacy method support (using new SDK but same interface)
    def generate_strategy_code(self, prompt: str) -> dict:
        # Deprecated: The new engine uses JSON recipes, but app.py might still call this for old manual/ai route?
        # Actually app.py handles both. If strategy_mode="ai", it looks for code.
        # Ideally we should deprecate this path, but let's keep it working.
        if not self.client:
             return {"name": "NoAPI_Strategy", "code": ""}

        query = f"""
        You are an expert algorithmic trading developer.
        The user wants: "{prompt}"

        Task:
        1. Create a creative and descriptive name for this strategy.
        2. Write a Python class named `AIStrategy` that inherits from `BaseStrategy`.
        ... (Shortened prompt for legacy support) ...
        Output JSON: {{"name": "...", "code": "..."}}
        """
        try:
            response = self.client.models.generate_content(model=self.model, contents=query)
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except:
            return {"name": "Error", "code": ""}

    def mutate_strategy_code(self, code: str, feedback: str) -> str:
        if not self.client: return code
        query = f"Refactor this code based on feedback: {feedback}\n\nCode:\n{code}"
        try:
            response = self.client.models.generate_content(model=self.model, contents=query)
            return response.text.replace("```python", "").replace("```", "").strip()
        except:
            return code
