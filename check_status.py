import requests
import json

def check_status():
    try:
        response = requests.get("http://localhost:8080/api/stats?mode=PAPER")
        data = response.json()
        print(f"Total Strategies: {len(data['strategies'])}")
        for s in data['strategies']:
            print(f"- {s['name']}: {s['status']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_status()
