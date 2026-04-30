"""Bad: async function — assert still stripped under -O."""

async def fetch(url):
    assert url.startswith("https://"), "https only"
    return await _do_fetch(url)


async def _do_fetch(url):
    return url
