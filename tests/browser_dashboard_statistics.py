# Project: VirtualGlove
# File: tests/browser_dashboard_statistics.py
# Purpose: Exercise the optional Dashboard statistics interface in a browser.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-10 - Covered the selected-profile play card shown in place of statistics.
#   2026-09-07 - Added statistics visibility, safety, and persistence coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Exercise optional diagnostics using mocked devices in Playwright WebKit.

Run with PYTHONPATH=src python tests/browser_dashboard_statistics.py.
"""
import asyncio
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

from virtualglove.control_server import SETUP
from virtualglove.dashboard_web import DASHBOARD


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.webkit.launch()
        context = await browser.new_context()

        async def route(request):
            parsed = urlsplit(request.request.url)
            path = parsed.path
            if path in ('/dashboard', '/setup'):
                return await request.fulfill(
                    body=DASHBOARD if path == '/dashboard' else SETUP,
                    content_type='text/html',
                )
            if path == '/status':
                return await request.fulfill(json=dict(
                    vision_state='active', active_profile='super_glove_ball',
                    connection_configured=True, calibrated=True,
                    dpad={'left': True}, buttons={'a': True}, axes={'x': 123},
                    fingers={'index': 0.5}, performance={'inference_ms': {'p50': 12}},
                    events=['glove_zap', '<b>literal event</b>'],
                ))
            return await request.fulfill(json={})

        await context.route('**/*', route)
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        # Count reads of diagnostic fields, not just changes to hidden markup.
        await page.add_init_script("""const originalFetch=window.fetch;
window.diagnosticReads=0;window.statusReads=0;
window.fetch=async(...args)=>{const response=await originalFetch(...args);
if(String(args[0]).startsWith('/status')){const json=response.json.bind(response);response.json=async()=>{
window.statusReads++;return new Proxy(await json(),{get(target,key){
if(['dpad','buttons','axes','fingers','performance','events'].includes(key))window.diagnosticReads++;
return target[key];}});};}return response;};""")
        await page.goto('http://statistics.test/dashboard')
        await page.wait_for_timeout(650)
        assert not await page.locator('#show-statistics').is_checked()
        assert not await page.locator('#dashboard-statistics').is_visible()
        assert await page.locator('#dashboard-program').is_visible()
        assert await page.locator('#program-title').inner_text() == 'Super Glove Ball'
        assert 'Close hand' in await page.locator('#program-mappings').inner_text()
        await page.evaluate("displayProgram('program_a')")
        assert await page.locator('#program-title').inner_text() == 'Program A — Pinball'
        assert 'Toggle combined flippers' in await page.locator('#program-mappings').inner_text()
        await page.evaluate("displayProgram('<img src=x onerror=alert(1)>')")
        assert await page.locator('#program-title').inner_text() == '<img src=x onerror=alert(1)>'
        assert await page.locator('#dashboard-program img').count() == 0
        await page.evaluate("displayProgram('super_glove_ball')")
        assert await page.evaluate('diagnosticReads') == 0
        assert await page.evaluate('statusReads') > 1
        assert await page.locator('#controller-toggle').is_enabled()

        await page.locator('#show-statistics').check()
        await page.wait_for_timeout(350)
        assert await page.locator('#dashboard-statistics').is_visible()
        assert not await page.locator('#dashboard-program').is_visible()
        assert '12' in await page.locator('#performance').inner_text()
        assert 'glove_zap' in await page.locator('#events').inner_text()
        assert await page.locator('#events b').count() == 0
        assert await page.evaluate('diagnosticReads') > 0

        setup = await context.new_page()
        await setup.goto('http://statistics.test/setup')
        assert await setup.locator('#show-statistics').is_checked()
        assert (await setup.locator('main h2').all_text_contents())[-2:] == ['Games', 'Show statistics']
        await setup.locator('#show-statistics').uncheck()
        await page.wait_for_function('!window.dashboardStatisticsEnabled()')
        reads = await page.evaluate('diagnosticReads')
        await page.wait_for_timeout(650)
        assert await page.evaluate('diagnosticReads') == reads
        assert await page.locator('#events').inner_text() == ''
        assert await page.locator('#performance').inner_text() == ''
        assert not await page.locator('#dashboard-statistics').is_visible()
        assert await page.locator('#dashboard-program').is_visible()

        await page.reload()
        assert not await page.locator('#show-statistics').is_checked()
        await page.locator('#show-statistics').check()
        await setup.wait_for_function('window.dashboardStatisticsEnabled()')
        await page.reload()
        assert await page.locator('#show-statistics').is_checked()
        assert not errors, errors
        await browser.close()
        print('Dashboard statistics: default off, no reads while off, live rendering, safe events, cross-tab sync and persistence passed.')


if __name__ == '__main__':
    asyncio.run(main())
