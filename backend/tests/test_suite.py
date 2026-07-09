import requests
import time

BASE_URL = "http://127.0.0.1:8001"


def check_endpoint(name, method, url, payload=None):
    print(f"Testing {name}...", end=" ")
    try:
        start = time.time()
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=payload, timeout=10)

        duration = time.time() - start

        if response.status_code == 200:
            print(f"✅ OK ({duration:.2f}s)")
            return response.json()
        else:
            print(f"❌ FAILED ({response.status_code})")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return None


def run_tests():
    print("🚀 Starting Comprehensive API Tests\n")

    # 1. Health
    check_endpoint("Health Check", "GET", f"{BASE_URL}/health")

    # 2. Trending
    check_endpoint("Trending Movies", "GET", f"{BASE_URL}/trending?limit=5")

    # 3. Semantic Search (Vector)
    res = check_endpoint(
        "Semantic Search ('space adventure')",
        "GET",
        f"{BASE_URL}/movies/semantic-search?q=space%20adventure&limit=3",
    )
    if res:
        movies = res.get("items") or res.get("results") or []
        if movies:
            print(f"   -> Found: {[m['title'] for m in movies]}")

    # 4. Keyword Search (Metadata)
    res = check_endpoint(
        "Keyword Search ('inception')",
        "GET",
        f"{BASE_URL}/movies/search?q=inception&limit=1",
    )
    if res:
        movies = res.get("items") or res.get("results") or []
        if movies:
            print(f"   -> Found: {[m['title'] for m in movies]}")
            movie_id = movies[0]["id"]

            # 5. Get Movie Details
            check_endpoint(
                f"Movie Details (ID: {movie_id})",
                "GET",
                f"{BASE_URL}/movies/{movie_id}",
            )

            # 6. Recommendations
            res = check_endpoint(
                f"Recommendations (ID: {movie_id})",
                "GET",
                f"{BASE_URL}/recommendations/{movie_id}",
            )
            recs = (
                res.get("recommendations") or res.get("items") or res.get("movies")
                if res
                else []
            )
            if recs:
                print(f"   -> Recs: {[m['title'] for m in recs[:3]]}")

    # 7. Agent Chat
    print("\n🤖 Testing AI Agent...")
    chat_payload = {
        "input": "I want a movie that is sad and about war.",
        "chat_history": [],
    }
    res = check_endpoint("Agent Chat", "POST", f"{BASE_URL}/agent/chat", chat_payload)
    if res:
        print(f"   -> Response: {res['response']}")


if __name__ == "__main__":
    run_tests()
