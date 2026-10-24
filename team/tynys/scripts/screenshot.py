"""Снимок экрана «Тыныс» (для CI и презентации): python screenshot.py URL out.png"""
import asyncio, sys
from playwright.async_api import async_playwright


async def main(url, out):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1400, "height": 1100})
        await pg.goto(url); await pg.wait_for_timeout(5000)
        await pg.screenshot(path=out, full_page=True); await b.close()

asyncio.run(main(sys.argv[1], sys.argv[2]))
