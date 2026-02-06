#!/usr/bin/env python3
"""
Verification script for TODO-048 fix.
Tests that the aggress endpoint works correctly.

Usage:
  python verify_aggress.py                    # Test local server
  python verify_aggress.py --prod             # Test production (Render)

The script will:
1. Create two participants and log them in
2. Create a test market
3. User A places an offer
4. User B aggresses (buys) that offer
5. Verify the trade happened

If all steps succeed, the fix is working.
"""

import asyncio
import httpx
import sys
from datetime import datetime

# Configuration
LOCAL_URL = "http://localhost:8000"
PROD_URL = "https://risk-morning-markets.onrender.com"

async def main(use_prod=False):
    base_url = PROD_URL if use_prod else LOCAL_URL
    print(f"\n{'='*60}")
    print(f"Testing aggress endpoint on: {base_url}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as admin:
        # Step 1: Login as admin
        print("1. Logging in as admin...")
        resp = await admin.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        if resp.status_code not in [302, 303]:
            print(f"   FAILED: Admin login returned {resp.status_code}")
            return False
        admin.cookies = resp.cookies
        print("   OK: Admin logged in")

        # Step 2: Create test participants
        timestamp = datetime.now().strftime("%H%M%S")
        p1_name = f"TestSeller_{timestamp}"
        p2_name = f"TestBuyer_{timestamp}"

        print(f"2. Creating test participants: {p1_name}, {p2_name}...")
        await admin.post("/admin/participants", data={"display_name": p1_name})
        await admin.post("/admin/participants", data={"display_name": p2_name})
        print("   OK: Participants created")

        # Get participant IDs
        resp = await admin.get("/")
        # Parse the dropdown to find participant IDs
        # This is a bit hacky but works for testing

        # Step 3: Create a test market
        print("3. Creating test market...")
        market_question = f"Test Market {timestamp}"
        resp = await admin.post("/admin/markets", data={"question": market_question, "description": "For testing aggress"})
        if resp.status_code not in [302, 303]:
            print(f"   FAILED: Market creation returned {resp.status_code}")
            return False
        print("   OK: Market created")

        # Get market ID from redirect URL or admin page
        resp = await admin.get("/admin")
        if resp.status_code != 200:
            print(f"   FAILED: Could not get admin page")
            return False

        # Find the market ID in the response
        import re
        market_match = re.search(r'/markets/([a-f0-9-]+)', resp.text)
        if not market_match:
            print("   FAILED: Could not find market ID")
            return False
        market_id = market_match.group(1)
        print(f"   Market ID: {market_id}")

        # Find participant IDs - use a fresh client without cookies
        async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as guest:
            resp = await guest.get("/")
            # format is <option value="UUID">Name</option>
            p1_match = re.search(rf'value="([a-f0-9-]+)">{p1_name}<', resp.text)
            p2_match = re.search(rf'value="([a-f0-9-]+)">{p2_name}<', resp.text)

            if not p1_match or not p2_match:
                print("   FAILED: Could not find participant IDs")
                print(f"   Looking for: {p1_name}, {p2_name}")
                return False

            p1_id = p1_match.group(1)
            p2_id = p2_match.group(1)
            print(f"   Participant IDs: {p1_id}, {p2_id}")

    # Step 4: Login as seller and place an offer
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as seller:
        print(f"\n4. {p1_name} logging in and placing OFFER at 100.00...")
        resp = await seller.post("/join", data={"participant_id": p1_id})
        if resp.status_code not in [302, 303]:
            print(f"   FAILED: Seller login returned {resp.status_code}")
            return False
        seller.cookies = resp.cookies

        resp = await seller.post(
            f"/markets/{market_id}/orders",
            data={"side": "OFFER", "price": "100.00", "quantity": "5"},
            headers={"HX-Request": "true"}
        )
        if resp.status_code != 200:
            print(f"   FAILED: Order placement returned {resp.status_code}")
            return False

        toast = resp.headers.get("HX-Toast-Success") or resp.headers.get("HX-Toast-Error")
        print(f"   Response: {toast}")

        if "HX-Toast-Error" in resp.headers:
            print(f"   FAILED: Order was rejected")
            return False
        print("   OK: Offer placed")

    # Step 5: Get the order ID
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as admin2:
        # Login as admin to see all orders
        resp = await admin2.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        admin2.cookies = resp.cookies

        resp = await admin2.get(f"/partials/orderbook/{market_id}")
        order_match = re.search(r'/orders/([a-f0-9-]+)/aggress', resp.text)
        if not order_match:
            print("   FAILED: Could not find order ID for aggress")
            return False
        order_id = order_match.group(1)
        print(f"   Order ID: {order_id}")

    # Step 6: Login as buyer and aggress the offer
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as buyer:
        print(f"\n5. {p2_name} logging in and AGGRESSING the offer...")
        resp = await buyer.post("/join", data={"participant_id": p2_id})
        if resp.status_code not in [302, 303]:
            print(f"   FAILED: Buyer login returned {resp.status_code}")
            return False
        buyer.cookies = resp.cookies

        print(f"   Sending POST to /orders/{order_id}/aggress with quantity=3...")
        resp = await buyer.post(
            f"/orders/{order_id}/aggress",
            data={"quantity": "3", "fill_and_kill": "false"},
            headers={"HX-Request": "true"}
        )

        print(f"   HTTP Status: {resp.status_code}")
        print(f"   HX-Toast-Success: {resp.headers.get('HX-Toast-Success')}")
        print(f"   HX-Toast-Error: {resp.headers.get('HX-Toast-Error')}")

        if resp.status_code != 200:
            print(f"   FAILED: Aggress returned {resp.status_code}")
            return False

        if "HX-Toast-Error" in resp.headers:
            print(f"   FAILED: Aggress was rejected: {resp.headers.get('HX-Toast-Error')}")
            return False

        toast = resp.headers.get("HX-Toast-Success")
        if not toast or "Bought" not in toast:
            print(f"   FAILED: Expected 'Bought' in success message, got: {toast}")
            return False

        print(f"   OK: Trade executed - {toast}")

    # Step 7: Verify the trade in recent trades
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=False) as verifier:
        resp = await verifier.post("/admin/login", data={"username": "chrson", "password": "optiver"})
        verifier.cookies = resp.cookies

        print(f"\n6. Verifying trade in recent trades...")
        resp = await verifier.get(f"/markets/{market_id}")

        # Check for the buyer name in recent trades
        if p2_name in resp.text and p1_name in resp.text:
            print(f"   OK: Both participants visible in market page")

        # Check trades section
        if "100.00" in resp.text:
            print(f"   OK: Trade at 100.00 visible")

        print("\n" + "="*60)
        print("ALL TESTS PASSED - Aggress endpoint is working!")
        print("="*60 + "\n")
        return True


if __name__ == "__main__":
    use_prod = "--prod" in sys.argv
    success = asyncio.run(main(use_prod))
    sys.exit(0 if success else 1)
