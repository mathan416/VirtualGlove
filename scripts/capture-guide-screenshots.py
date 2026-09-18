#!/usr/bin/env python3
# Project: VirtualGlove
# File: scripts/capture-guide-screenshots.py
# Purpose: Refresh guide screenshots from current pages using isolated sample data.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-08 - Added discovered-camera settings to isolated Setup fixtures.
#   2026-09-07 - Kept help-asset fixtures compatible with Python 3.7.
#   2026-09-06 - Capture all documented application panels without live device data.
# Full history: docs/CHANGELOG.md and Git history.

"""Run with PYTHONPATH=src python scripts/capture-guide-screenshots.py.
Requires Playwright and Chrome. No real camera, player, or cabinet is contacted.
"""
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright, expect
from virtualglove.control_server import DASHBOARD, LEARN, PLAY, SETUP
from virtualglove.control_server import help_document_page, help_index_page
from virtualglove.model import Calibration
from virtualglove.tuning import TuningManager
from virtualglove.versioning import current_identity

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/images'
CAMERA = '''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480">
<rect width="640" height="480" fill="#172236"/>
<text x="320" y="225" text-anchor="middle" fill="#aabbd0" font-family="sans-serif" font-size="22">Camera preview omitted</text>
<text x="320" y="265" text-anchor="middle" fill="#aabbd0" font-family="sans-serif" font-size="16">Documentation example — no live camera</text></svg>'''


async def capture():
    """Render current application HTML against temporary, non-secret fixtures."""
    with tempfile.TemporaryDirectory(prefix='virtualglove-guide-') as temporary:
        manager = TuningManager(Path(temporary) / 'gesture-tuning.json')
        manager.begin_center()
        manager.finish_center(Calibration(.5, .5, .2, 0, .01, .01))
        identity = current_identity()
        state = manager.player_snapshot()
        manager.player_command(dict(action='rename', player=state['active'], generation=state['generation'], name='Player One'))
        sequence = 0
        errors = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel='chrome', headless=True)
            page = await browser.new_page(viewport={'width':1280, 'height':1000})
            page.on('pageerror', lambda e: errors.append(str(e)))
            async def route(request):
                """Serve current pages and fixture responses without external requests."""
                nonlocal sequence
                path = urlsplit(request.request.url).path
                pages = {'/dashboard':DASHBOARD, '/play':PLAY, '/learn':LEARN, '/setup':SETUP, '/help':help_index_page()}
                if path in pages:
                    return await request.fulfill(body=pages[path], content_type='text/html')
                if path == '/help/security':
                    return await request.fulfill(body=help_document_page('security'), content_type='text/html')
                if path == '/status':
                    sequence += 1
                    return await request.fulfill(json=dict(sequence=sequence, vision_state='active', practice_mode=True,
                        worker_running=True, camera_available=True, detected=False, calibrated=True,
                        active_profile='super_glove_ball', configured_profile='super_glove_ball', profile_source='Dashboard',
                        native_xy_source='mediapipe',
                        connection_configured=True, controller_enabled=False, version='0.4.0', build=identity,
                        camera_fps=30.0, camera_fps_requested='auto',
                        capture_backend='opencv', capture_backend_requested='opencv',
                        capture_backend_fallback=None, camera_exposure_mode='auto',
                        camera_exposure_applied=False,
                        player=manager.player_snapshot(), tuning=manager.snapshot(),
                        dpad={'up':False,'down':False,'left':False,'right':False}, buttons={'A':False,'B':False,'Start':False,'Select':False},
                        axes={'x':0,'y':0}, fingers={'index':0,'thumb':0,'middle':0,'ring':0,'pinky':0}))
                if path in ('/api/players', '/api/tuning'):
                    try:
                        command = manager.player_command if path.endswith('players') else manager.command
                        return await request.fulfill(json=command(request.request.post_data_json))
                    except ValueError as error:
                        return await request.fulfill(status=400, json={'error':str(error)})
                if path == '/api/config':
                    return await request.fulfill(json=dict(receiver='RETROPIE-NAME.local',port=55355,profile='off',glove_color='none',camera='auto',camera_fps='auto',camera_backend='opencv',camera_exposure='auto',camera_manual_exposure=78,camera_manual_gain=96,camera_options=[dict(value='auto',label='Automatic — choose the connected camera'),dict(value='2',label='Razer Kiyo Pro — camera 2')],matrix_attract='on',connection_configured=True))
                if path == '/api/connection-status':
                    return await request.fulfill(json=dict(app=True,console_configured=True,console_service=True,console_authenticated=True,networking='connected',checked_seconds_ago=1))
                if path == '/api/games':
                    return await request.fulfill(json=dict(document=(ROOT/'config/games.json').read_text(),revision='example',has_backup=False,profiles=[f'program_{n}' for n in range(1,15)]+[f'program_{c}' for c in 'abcdefghi']+['bad_street_brawler','super_glove_ball']))
                if path == '/api/practice':
                    return await request.fulfill(json={'practice_mode':True})
                if path == '/stream':
                    return await request.fulfill(body=CAMERA,content_type='image/svg+xml')
                if path.startswith(('/help-assets/','/assets/')):
                    asset = ROOT / ('docs/images/'+path[len('/help-assets/'):] if path.startswith('/help-assets/') else path.lstrip('/'))
                    try:
                        asset.resolve().relative_to(ROOT.resolve())
                    except ValueError:
                        return await request.fulfill(status=404)
                    if asset.is_file():
                        return await request.fulfill(path=str(asset))
                return await request.fulfill(status=404)
            await page.route('**/*', route)
            async def screenshot(name, selector=None):
                """Save the rendered page or selected panel to its maintained asset path."""
                target = page.locator(selector) if selector else page
                await target.screenshot(path=str(OUTPUT/name), **({} if selector else {'full_page':True}))
                print('Captured', name, flush=True)
            await page.goto('https://guide.test/dashboard')
            await expect(page.locator('#system')).to_have_text('Ready')
            await screenshot('debug-dashboard.png')
            await page.goto('https://guide.test/play')
            await expect(page.locator('#rps-camera')).to_be_visible()
            await screenshot('play-page.png')
            await page.goto('https://guide.test/learn')
            await expect(page.locator('#player-select')).to_be_enabled()
            await expect(page.locator('#learn-camera')).to_be_visible()
            await screenshot('learn-page.png')
            await page.goto('https://guide.test/setup')
            await expect(page.locator('#player-select')).to_be_enabled()
            await page.get_by_text('Players and hand-setup backups',exact=True).click()
            await page.set_viewport_size({'width':768,'height':1024})
            await screenshot('player-settings.png','.player-card')
            snapshot = manager.player_snapshot()
            backup = manager.player_command(dict(action='export', player=snapshot['active'],generation=snapshot['generation']))['backup']
            await page.locator('#player-import').set_input_files(dict(name='hand-setup.json',mimeType='application/json',buffer=json.dumps(backup).encode()))
            await expect(page.locator('#restore-review')).to_be_visible()
            await screenshot('hand-setup-restore.png','#restore-review')
            await page.locator('#restore-cancel').click()
            await page.get_by_text('Players and hand-setup backups',exact=True).click()
            await page.set_viewport_size({'width':1280,'height':1000})
            await page.goto('https://guide.test/learn')
            await expect(page.locator('#player-select')).to_be_enabled()
            await page.locator('#tune-switch').check()
            await expect(page.locator('#tune-panel')).to_be_visible()
            await screenshot('tune-page.png')
            await page.goto('https://guide.test/setup')
            await expect(page.locator('#games-notice')).to_contain_text('loaded')
            await screenshot('games-section.png','#games-section')
            await page.goto('https://guide.test/help')
            technical = await page.get_by_role('heading',name='Technical documentation',exact=True).bounding_box()
            split = int(technical['y']) - 16
            height = await page.evaluate('document.documentElement.scrollHeight')
            await page.screenshot(path=str(OUTPUT/'help-page.png'),full_page=True,clip={'x':0,'y':0,'width':1280,'height':split})
            await page.screenshot(path=str(OUTPUT/'help-technical.png'),full_page=True,clip={'x':0,'y':split,'width':1280,'height':height-split})
            print('Captured help-page.png and help-technical.png',flush=True)
            await page.goto('https://guide.test/help/security')
            for width in (390,768,1280):
                await page.set_viewport_size({'width':width,'height':1000})
                for cell in await page.locator('.network-exposure td:first-child code').all():
                    # Each port must occupy one text line, even when its table scrolls.
                    assert await cell.evaluate('(e)=>{const r=document.createRange();r.selectNodeContents(e);return r.getClientRects().length===1}')
                assert await page.evaluate('document.documentElement.scrollWidth') <= width
                await page.locator('.network-exposure').screenshot(path=f'/tmp/virtualglove-security-table-{width}.png')
            assert not errors, errors
            await browser.close()


if __name__ == '__main__':
    subprocess.run([sys.executable, str(ROOT/'tests/browser_setup_pairing.py'), '--screenshots'], cwd=ROOT, check=True)
    asyncio.run(capture())
