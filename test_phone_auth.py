#!/usr/bin/env python3
"""
Test script for phone-based authentication endpoints using Twilio Verify Service.
This script tests all new authentication endpoints.

Requirements:
- Backend running on http://localhost:8000
- Valid Twilio Verify Service configured
- Test phone number that can receive SMS (use Twilio test numbers or your own)

Usage:
    python test_phone_auth.py
"""

import requests
import json
import time
from typing import Dict, Optional

# Configuration
BASE_URL = "http://localhost:8000"
API_PREFIX = "/api"
TEST_PHONE = "03001234567"  # Change to your test phone in international format
TEST_EMAIL = "test@shoptalkai.local"
TEST_NAME = "Test User"
TEST_PASSWORD = "TestPassword123!"

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    END = '\033[0m'

def print_header(text: str):
    """Print colored section header"""
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}{text:^60}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ {text}{Colors.END}")

def print_step(step: int, text: str):
    """Print step indicator"""
    print(f"\n{Colors.CYAN}Step {step}: {text}{Colors.END}")

def make_request(method: str, endpoint: str, data: Optional[Dict] = None, 
                 headers: Optional[Dict] = None, expect_success: bool = True) -> Optional[Dict]:
    """
    Make HTTP request and handle response
    """
    url = f"{BASE_URL}{API_PREFIX}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, headers=headers)
        else:
            print_error(f"Unsupported HTTP method: {method}")
            return None
        
        # Print request info
        print_info(f"{method.upper()} {endpoint}")
        if data:
            print_info(f"Request body: {json.dumps(data, indent=2)}")
        
        # Handle response
        if response.status_code >= 400:
            print_error(f"HTTP {response.status_code}")
            try:
                print_error(f"Response: {response.json()}")
            except:
                print_error(f"Response: {response.text}")
            
            if expect_success:
                return None
        else:
            print_success(f"HTTP {response.status_code}")
            try:
                result = response.json()
                print_info(f"Response: {json.dumps(result, indent=2)}")
                return result
            except:
                print_warning(f"Could not parse JSON response")
                return None
        
        return response.json() if response.status_code < 400 else None
        
    except requests.exceptions.ConnectionError:
        print_error(f"Connection failed. Is the backend running on {BASE_URL}?")
        return None
    except Exception as e:
        print_error(f"Request failed: {str(e)}")
        return None

def test_send_signup_otp():
    """Test sending OTP for signup"""
    print_step(1, "Send OTP for Signup")
    
    data = {
        "phone": TEST_PHONE,
        "email": TEST_EMAIL,
        "name": TEST_NAME,
        "password": TEST_PASSWORD
    }
    
    response = make_request("POST", "/auth/send-signup-otp", data)
    
    if response:
        print_warning(f"⏳ Check your phone for the OTP code (expires in 10 minutes)")
        return True
    return False

def test_verify_signup_otp(otp_code: str) -> Optional[Dict]:
    """Test verifying OTP for signup"""
    print_step(2, "Verify OTP and Create Account")
    
    data = {
        "phone": TEST_PHONE,
        "code": otp_code
    }
    
    response = make_request("POST", "/auth/verify-signup-otp", data)
    
    if response and "access_token" in response:
        print_success("Account created successfully!")
        return response
    return None

def test_get_profile(access_token: str):
    """Test getting user profile"""
    print_step(3, "Get User Profile")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    response = make_request("GET", "/auth/profile", headers=headers)
    
    if response:
        print_success("Profile retrieved successfully!")
        return response
    return None

def test_login(phone: str, password: str) -> Optional[Dict]:
    """Test login endpoint"""
    print_step(4, "Login with Phone and Password")
    
    data = {
        "phone": phone,
        "password": password
    }
    
    response = make_request("POST", "/auth/login", data)
    
    if response and "access_token" in response:
        print_success("Login successful!")
        return response
    return None

def test_forgot_password(phone: str):
    """Test forgot password endpoint"""
    print_step(5, "Request Password Reset OTP")
    
    data = {
        "phone": phone
    }
    
    response = make_request("POST", "/auth/forgot-password", data)
    
    if response:
        print_warning(f"⏳ Check your phone for the reset OTP code")
        return True
    return False

def test_verify_reset_otp(phone: str, otp_code: str) -> bool:
    """Test verifying reset OTP"""
    print_step(6, "Verify Password Reset OTP")
    
    data = {
        "phone": phone,
        "code": otp_code
    }
    
    response = make_request("POST", "/auth/verify-reset-otp", data)
    
    if response:
        print_success("Reset OTP verified!")
        return True
    return False

def test_reset_password(phone: str, otp_code: str, new_password: str) -> bool:
    """Test reset password endpoint"""
    print_step(7, "Reset Password")
    
    data = {
        "phone": phone,
        "code": otp_code,
        "new_password": new_password
    }
    
    response = make_request("POST", "/auth/reset-password", data)
    
    if response:
        print_success("Password reset successfully!")
        return True
    return False

def interactive_mode():
    """Run interactive testing"""
    print_header("ShopTalk AI - Phone Authentication Testing")
    
    print_info(f"Testing with phone: {TEST_PHONE}")
    print_info(f"Testing with email: {TEST_EMAIL}")
    
    choice = input(f"\n{Colors.CYAN}What do you want to test?{Colors.END}\n"
                   f"1. Complete signup flow with OTP\n"
                   f"2. Login with existing account\n"
                   f"3. Password reset flow\n"
                   f"4. Get user profile (requires token)\n"
                   f"\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        print_header("SIGNUP WITH OTP FLOW")
        
        if not test_send_signup_otp():
            return
        
        otp = input(f"\n{Colors.CYAN}Enter the OTP code from SMS: {Colors.END}")
        
        result = test_verify_signup_otp(otp)
        if result and "access_token" in result:
            print_success("Signup completed! User account created.")
            
            # Optionally get profile
            should_profile = input(f"\n{Colors.CYAN}Test getting profile? (y/n): {Colors.END}")
            if should_profile.lower() == 'y':
                test_get_profile(result["access_token"])
    
    elif choice == "2":
        print_header("LOGIN FLOW")
        
        phone = input(f"{Colors.CYAN}Enter phone number ({TEST_PHONE}): {Colors.END}") or TEST_PHONE
        password = input(f"{Colors.CYAN}Enter password: {Colors.END}")
        
        result = test_login(phone, password)
        if result and "access_token" in result:
            print_success("Login successful!")
            
            # Optionally get profile
            should_profile = input(f"\n{Colors.CYAN}Test getting profile? (y/n): {Colors.END}")
            if should_profile.lower() == 'y':
                test_get_profile(result["access_token"])
    
    elif choice == "3":
        print_header("PASSWORD RESET FLOW")
        
        phone = input(f"{Colors.CYAN}Enter phone number ({TEST_PHONE}): {Colors.END}") or TEST_PHONE
        
        if not test_forgot_password(phone):
            return
        
        otp = input(f"\n{Colors.CYAN}Enter the OTP code from SMS: {Colors.END}")
        
        if not test_verify_reset_otp(phone, otp):
            return
        
        new_password = input(f"{Colors.CYAN}Enter new password: {Colors.END}")
        
        test_reset_password(phone, otp, new_password)
    
    elif choice == "4":
        print_header("GET PROFILE")
        
        token = input(f"{Colors.CYAN}Enter access token: {Colors.END}")
        test_get_profile(token)
    
    else:
        print_error("Invalid choice")

def quick_test():
    """Run quick automated test"""
    print_header("ShopTalk AI - Quick Endpoint Test")
    
    # Test 1: Check if backend is running
    print_step(1, "Check backend connectivity")
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        if response.status_code == 200:
            print_success(f"Backend is running on {BASE_URL}")
        else:
            print_error(f"Backend responded with {response.status_code}")
            return
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to backend on {BASE_URL}")
        print_info("Make sure the backend is running: python -m uvicorn app.main:app --reload")
        return
    
    # Test 2: Send signup OTP
    if test_send_signup_otp():
        print_info("Check your phone for the OTP code")
        otp = input(f"\n{Colors.CYAN}Enter the OTP code: {Colors.END}")
        
        # Test 3: Verify signup OTP
        result = test_verify_signup_otp(otp)
        if result:
            print_success("All tests passed!")
            print_info(f"Access token: {result.get('access_token', '')[:50]}...")
        else:
            print_error("Signup verification failed")
    else:
        print_error("Could not send OTP")

if __name__ == "__main__":
    import sys
    
    # Check command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_test()
    else:
        interactive_mode()
