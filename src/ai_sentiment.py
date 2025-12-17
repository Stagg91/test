import google.generativeai as genai
import os
import requests
import random

class AISentimentAgent:
    def __init__(self, gemini_api_key=None):
        self.api_key = gemini_api_key
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
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
