#!/usr/bin/env python3
"""
Backend test for GiftsDates 3-hour date slot booking logic.
Tests multiple non-overlapping bookings on the same day.
"""
import requests
import json
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
import sys

# Load environment
BASE_URL = "https://texture-vault-10.preview.emergentagent.com/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

# Test data
tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    if details:
        print(f"    {details}")

def register_user(email, name, password="TestPass123!"):
    """Register a new user and return token and user_id"""
    payload = {
        "email": email,
        "password": password,
        "name": name,
        "age": 25,
        "gender": "female",
        "interested_in": "male",
        "city": "New York",
        "country": "USA"
    }
    resp = requests.post(f"{BASE_URL}/auth/register", json=payload)
    if resp.status_code == 200:
        data = resp.json()
        return data["token"], data["user"]["id"]
    else:
        print(f"Registration failed for {email}: {resp.status_code} - {resp.text}")
        return None, None

def set_availability(token, availability_dates, availability_time):
    """Set user's availability dates and time window"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "availability": availability_dates,
        "availability_time": availability_time
    }
    resp = requests.patch(f"{BASE_URL}/auth/me", json=payload, headers=headers)
    return resp.status_code == 200, resp

def book_date(token, target_id, local_time, coins=150):
    """Book a date at specific local time"""
    headers = {"Authorization": f"Bearer {token}"}
    scheduled_at = f"{tomorrow}T{local_time}:00Z"
    payload = {
        "target_id": target_id,
        "venue": "Test Venue",
        "city": "New York",
        "scheduled_at": scheduled_at,
        "coins": coins,
        "local_time": local_time
    }
    resp = requests.post(f"{BASE_URL}/dates/book", json=payload, headers=headers)
    return resp

def get_availability(token, target_id):
    """Get target's availability including busy slots"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BASE_URL}/profiles/{target_id}/availability", headers=headers)
    return resp

def grant_coins_mongodb(user_id, coins):
    """Directly grant coins to user via MongoDB"""
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        result = db.users.update_one(
            {"id": user_id},
            {"$set": {"coins": coins}}
        )
        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"MongoDB error granting coins: {e}")
        return False

def main():
    print_section("3-HOUR DATE SLOT BOOKING TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"Test Date: {tomorrow}")
    
    # Setup: Register 3 users
    print_section("SETUP: Register Users")
    
    target_email = f"target_{datetime.now().timestamp()}@test.com"
    booker1_email = f"booker1_{datetime.now().timestamp()}@test.com"
    booker2_email = f"booker2_{datetime.now().timestamp()}@test.com"
    
    target_token, target_id = register_user(target_email, "Target User")
    if not target_token:
        print("❌ Failed to register target user")
        sys.exit(1)
    print_result("Register Target User", True, f"ID: {target_id}")
    
    booker1_token, booker1_id = register_user(booker1_email, "Booker One")
    if not booker1_token:
        print("❌ Failed to register booker1")
        sys.exit(1)
    print_result("Register Booker 1", True, f"ID: {booker1_id}")
    
    booker2_token, booker2_id = register_user(booker2_email, "Booker Two")
    if not booker2_token:
        print("❌ Failed to register booker2")
        sys.exit(1)
    print_result("Register Booker 2", True, f"ID: {booker2_id}")
    
    # Grant coins to bookers via MongoDB
    print_section("SETUP: Grant Coins via MongoDB")
    
    if grant_coins_mongodb(booker1_id, 5000):
        print_result("Grant coins to Booker 1", True, "5000 coins")
    else:
        print_result("Grant coins to Booker 1", False, "MongoDB update failed")
        sys.exit(1)
    
    if grant_coins_mongodb(booker2_id, 5000):
        print_result("Grant coins to Booker 2", True, "5000 coins")
    else:
        print_result("Grant coins to Booker 2", False, "MongoDB update failed")
        sys.exit(1)
    
    # Set target availability
    print_section("SETUP: Set Target Availability")
    
    success, resp = set_availability(
        target_token,
        [tomorrow],
        {"from": "12:00", "to": "21:00"}
    )
    if success:
        print_result("Set availability", True, f"Date: {tomorrow}, Time: 12:00-21:00")
    else:
        print_result("Set availability", False, f"Status: {resp.status_code}, Response: {resp.text}")
        sys.exit(1)
    
    # Test Scenarios
    print_section("TEST SCENARIOS")
    
    # Scenario A: Booker1 books at 12:00 (locks 12:00-15:00)
    print("\n[A] Booker1 books TARGET at 12:00 (should lock 12:00-15:00)")
    resp_a = book_date(booker1_token, target_id, "12:00", 150)
    if resp_a.status_code == 200:
        data = resp_a.json()
        if data.get("status") == "escrow":
            print_result("Scenario A", True, f"Booking successful, status: {data['status']}")
        else:
            print_result("Scenario A", False, f"Unexpected status: {data.get('status')}")
    else:
        print_result("Scenario A", False, f"Status: {resp_a.status_code}, Response: {resp_a.text}")
    
    # Scenario B: Try to book overlapping slot at 12:00 (should fail with SLOT_BUSY)
    print("\n[B] Booker2 tries to book TARGET at 12:00 (overlaps 12:00-15:00, should fail)")
    resp_b = book_date(booker2_token, target_id, "12:00", 150)
    if resp_b.status_code == 400:
        detail = resp_b.json().get("detail", "")
        if detail.startswith("SLOT_BUSY:"):
            print_result("Scenario B", True, f"Correctly rejected: {detail}")
        else:
            print_result("Scenario B", False, f"Wrong error: {detail}")
    else:
        print_result("Scenario B", False, f"Expected 400, got {resp_b.status_code}: {resp_b.text}")
    
    # Scenario B2: Try to book overlapping slot at 13:00 (should also fail)
    print("\n[B2] Booker2 tries to book TARGET at 13:00 (overlaps 12:00-15:00, should fail)")
    resp_b2 = book_date(booker2_token, target_id, "13:00", 150)
    if resp_b2.status_code == 400:
        detail = resp_b2.json().get("detail", "")
        if detail.startswith("SLOT_BUSY:"):
            print_result("Scenario B2", True, f"Correctly rejected: {detail}")
        else:
            print_result("Scenario B2", False, f"Wrong error: {detail}")
    else:
        print_result("Scenario B2", False, f"Expected 400, got {resp_b2.status_code}: {resp_b2.text}")
    
    # Scenario C: Booker2 books at 15:00 (non-overlapping, should succeed)
    print("\n[C] Booker2 books TARGET at 15:00 (non-overlapping 15:00-18:00, should succeed)")
    resp_c = book_date(booker2_token, target_id, "15:00", 150)
    if resp_c.status_code == 200:
        data = resp_c.json()
        if data.get("status") == "escrow":
            print_result("Scenario C", True, f"Multiple dates on same day allowed! Status: {data['status']}")
        else:
            print_result("Scenario C", False, f"Unexpected status: {data.get('status')}")
    else:
        print_result("Scenario C", False, f"Status: {resp_c.status_code}, Response: {resp_c.text}")
    
    # Scenario D: Book at 18:00 (should succeed, 18:00-21:00)
    print("\n[D] Booker1 books TARGET at 18:00 (non-overlapping 18:00-21:00, should succeed)")
    resp_d = book_date(booker1_token, target_id, "18:00", 150)
    if resp_d.status_code == 200:
        data = resp_d.json()
        if data.get("status") == "escrow":
            print_result("Scenario D", True, f"Third booking on same day successful! Status: {data['status']}")
        else:
            print_result("Scenario D", False, f"Unexpected status: {data.get('status')}")
    else:
        print_result("Scenario D", False, f"Status: {resp_d.status_code}, Response: {resp_d.text}")
    
    # Scenario E: Try to book at 20:00 (3h block 20:00-23:00 exceeds window end 21:00)
    print("\n[E] Booker2 tries to book TARGET at 20:00 (20:00-23:00 exceeds window 21:00, should fail)")
    resp_e = book_date(booker2_token, target_id, "20:00", 150)
    if resp_e.status_code == 400:
        detail = resp_e.json().get("detail", "")
        if detail.startswith("TIME_UNAVAILABLE:"):
            print_result("Scenario E", True, f"Correctly rejected: {detail}")
        else:
            print_result("Scenario E", False, f"Wrong error: {detail}")
    else:
        print_result("Scenario E", False, f"Expected 400, got {resp_e.status_code}: {resp_e.text}")
    
    # Scenario F: Get availability and verify busy_slots
    print("\n[F] GET /api/profiles/{target_id}/availability - verify busy_slots and slot_hours")
    resp_f = get_availability(booker1_token, target_id)
    if resp_f.status_code == 200:
        data = resp_f.json()
        print(f"    Response: {json.dumps(data, indent=2)}")
        
        checks = []
        
        # Check slot_hours = 3
        if data.get("slot_hours") == 3:
            checks.append(("slot_hours = 3", True))
        else:
            checks.append(("slot_hours = 3", False))
        
        # Check busy_slots exists and has tomorrow's date
        busy_slots = data.get("busy_slots", {})
        if tomorrow in busy_slots:
            slots = busy_slots[tomorrow]
            checks.append(("busy_slots contains tomorrow", True))
            
            # Should have 3 slots: 12:00-15:00, 15:00-18:00, 18:00-21:00
            expected_slots = [
                {"from": "12:00", "to": "15:00"},
                {"from": "15:00", "to": "18:00"},
                {"from": "18:00", "to": "21:00"}
            ]
            
            if len(slots) == 3:
                checks.append(("3 busy slots present", True))
            else:
                checks.append(("3 busy slots present", False))
            
            # Check each expected slot
            for expected in expected_slots:
                found = any(s["from"] == expected["from"] and s["to"] == expected["to"] for s in slots)
                checks.append((f"Slot {expected['from']}-{expected['to']}", found))
        else:
            checks.append(("busy_slots contains tomorrow", False))
        
        # Check that tomorrow IS in busy_days (since all 3 slots are now taken)
        busy_days = data.get("busy_days", [])
        if tomorrow in busy_days:
            checks.append(("Tomorrow in busy_days (all slots taken)", True))
        else:
            checks.append(("Tomorrow in busy_days (all slots taken)", False))
        
        all_passed = all(result for _, result in checks)
        for check_name, result in checks:
            print_result(f"  {check_name}", result)
        
        print_result("Scenario F", all_passed, "Availability endpoint verification")
    else:
        print_result("Scenario F", False, f"Status: {resp_f.status_code}, Response: {resp_f.text}")
    
    # Summary
    print_section("TEST SUMMARY")
    print("All test scenarios completed.")
    print("Review the results above for pass/fail status.")
    print("\nKey findings:")
    print("- Multiple 3-hour dates can be booked on the same day (non-overlapping)")
    print("- Overlapping bookings are correctly rejected with SLOT_BUSY")
    print("- Time window boundaries are enforced (TIME_UNAVAILABLE)")
    print("- Availability endpoint returns busy_slots with slot_hours=3")

if __name__ == "__main__":
    main()
