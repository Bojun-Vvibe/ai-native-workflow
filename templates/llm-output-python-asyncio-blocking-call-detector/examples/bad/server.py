"""Bad: blocking sync calls inside async functions."""
import time
import requests
import subprocess


async def fetch_user(user_id: int):
    # 1) sync HTTP inside async — blocks the event loop
    r = requests.get(f"https://api.example.com/users/{user_id}")
    return r.json()


async def poll_loop():
    while True:
        # 2) sync sleep — should be `await asyncio.sleep(1)`
        time.sleep(1)
        await do_work()


async def run_command():
    # 3) blocking subprocess — should be asyncio.create_subprocess_exec
    out = subprocess.run(["echo", "hello"], capture_output=True)
    return out.stdout


async def load_config(path: str):
    # 4) blocking file open inside async path
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def do_work():
    return None
