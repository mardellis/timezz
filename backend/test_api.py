#!/usr/bin/env python3
"""
Quick test script for the Time Tracker API
Run: python test_api.py
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000/api/v1"
# Change to your deployed URL: "https://your-app.railway.app/api/v1"

def test_api():
    print("🧪 Testing Time Tracker API...")
    
    # 1. Test health check
    print("\n1️⃣ Health Check")
    try:
        response = requests.get("http://localhost:8000/")
        print(f"✅ Health: {response.json()}")
    except Exception as e:
        print(f"❌ Health failed: {e}")
        return
    
    # 2. Test login
    print("\n2️⃣ Login Test")
    login_data = {
        "trello_user_id": "test_user_123",
        "trello_token": "dummy_token",
        "name": "Test User",
        "email": "test@example.com"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            token_data = response.json()
            token = token_data["access_token"]
            print(f"✅ Login: {token_data['user']}")
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"Error details: {response.text}")
            return
    except Exception as e:
        print(f"❌ Login error: {e}")
        return
    
    # Headers for authenticated requests
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Test start timer
    print("\n3️⃣ Start Timer")
    timer_data = {
        "card_id": "test_card_123",
        "card_name": "Test Card",
        "board_id": "test_board_123",
        "description": "Testing timer functionality"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/time/start", json=timer_data, headers=headers)
        if response.status_code == 200:
            timer_result = response.json()
            print(f"✅ Timer Started: ID {timer_result['id']}")
        else:
            print(f"❌ Start timer failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Start timer error: {e}")
    
    # 4. Check active timer
    print("\n4️⃣ Check Active Timer")
    try:
        response = requests.get(f"{BASE_URL}/time/active", headers=headers)
        if response.status_code == 200:
            active = response.json()
            print(f"✅ Active Timer: {active}")
        else:
            print(f"❌ Check active failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Check active error: {e}")
    
    # Wait a bit to accumulate time
    print("\n⏳ Waiting 3 seconds to accumulate time...")
    time.sleep(3)
    
    # 5. Stop timer
    print("\n5️⃣ Stop Timer")
    try:
        response = requests.post(f"{BASE_URL}/time/stop", headers=headers)
        if response.status_code == 200:
            stop_result = response.json()
            print(f"✅ Timer Stopped: {stop_result['duration_minutes']:.2f} minutes")
        else:
            print(f"❌ Stop timer failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Stop timer error: {e}")
    
    # 6. Get entries
    print("\n6️⃣ Get Entries")
    try:
        response = requests.get(f"{BASE_URL}/time/entries", headers=headers)
        if response.status_code == 200:
            entries = response.json()
            print(f"✅ Entries: {len(entries)} found")
            if entries:
                print(f"   Latest: {entries[0]['card_name']} - {entries[0]['duration_minutes']:.2f}min")
        else:
            print(f"❌ Get entries failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Get entries error: {e}")
    
    # 7. Get reports
    print("\n7️⃣ Get Reports")
    try:
        response = requests.get(f"{BASE_URL}/reports/detailed?days=1", headers=headers)
        if response.status_code == 200:
            report = response.json()
            print(f"✅ Report: {report['total_hours']}h, {report['total_entries']} entries")
        else:
            print(f"❌ Get report failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Get report error: {e}")
    
    print("\n🎉 Test completed!")

if __name__ == "__main__":
    test_api()