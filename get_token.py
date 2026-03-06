import requests
import json
import sys

def main():
    token_url = "https://openapi.ctrader.com/apps/token"
    payload = {
        "grant_type": "authorization_code",
        "code": "745fbf9a9869509b6348071bd71e06612338e6ce5f59a72e3bd38b231daf4d2b7be3e4ed7f925a05c4aded",
        "client_id": "22363_GqqenOj9XA5dY0PtB7Vq2cRHr20PH7SYxVdq7DRpmQYE9H8Ogf",
        "client_secret": "3JQKyYwA233OYBmLj7v7OeQxhIjSdb1h5g9ITCH9A57odqMnwO",
        "redirect_uri": "http://localhost"
    }
    
    try:
        res = requests.post(token_url, data=payload, timeout=10)
        print("STATUS:", res.status_code)
        print("RESPONSE:", res.text)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    main()
