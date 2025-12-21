from src.ai_sentiment import AISentimentAgent
import feedparser

def verify():
    print("Testing News Fetching...")
    agent = AISentimentAgent()
    headlines = agent.fetch_crypto_news()
    print(f"Found {len(headlines)} headlines:")
    for h in headlines:
        print(f"- {h}")

    if len(headlines) > 0 and headlines[0] != "Bitcoin market shows resilience amidst volatility.":
        print("\nSUCCESS: Fetched live news.")
    else:
        print("\nWARNING: Using fallback news (possibly due to network or parser issue).")

if __name__ == "__main__":
    verify()
