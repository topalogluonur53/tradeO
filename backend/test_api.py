import requests

def test_api():
    # Login
    res = requests.post("http://127.0.0.1:8000/api/auth/token", data={
        "username": "admin",
        "password": "password" # Wait, I don't know the password. Let's just query db directly.
    })
    
test_api()
