"""Good: async-native I/O, no blocking calls on the event loop."""
import asyncio
import aiohttp


async def fetch_user(user_id: int):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.example.com/users/{user_id}"
        ) as r:
            return await r.json()


async def poll_loop():
    while True:
        await asyncio.sleep(1)
        await do_work()


async def run_command():
    proc = await asyncio.create_subprocess_exec(
        "echo",
        "hello",
        stdout=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return out


async def load_config(path: str):
    # Offload blocking file I/O to a worker thread.
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_file, path)


def _read_file(path: str) -> str:
    # Sync helper called via run_in_executor — calls to open() here are fine.
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def do_work():
    return None
