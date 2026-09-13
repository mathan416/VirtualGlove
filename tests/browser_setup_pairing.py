# Project: VirtualGlove
# File: tests/browser_setup_pairing.py
# Purpose: Exercise the guided Setup pairing flow with isolated browser fixtures.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-09 - Covered armed-idle and genuine receiver-unavailable status.
#   2026-09-08 - Capture and verify the discovered-camera Setup controls.
#   2026-09-07 - Kept help-asset fixtures compatible with Python 3.7.
#   2026-09-06 - Cover guided pairing, expiry, retries, responsive layouts, and screenshots.
# Full history: docs/CHANGELOG.md and Git history.

"""Run with PYTHONPATH=src python tests/browser_setup_pairing.py [--screenshots] [--webkit].
Requires Playwright and Chrome; never connects to real pairing endpoints.
"""
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
from powerglove_vision.control_server import SETUP

ROOT = Path(__file__).resolve().parents[1]

async def main():
    """Test user-visible state transitions against controlled HTTP responses."""
    config = dict(receiver='RETROPIE-NAME.local', port=55355, profile='off',
                  glove_color='none', camera='auto', camera_fps='auto', matrix_attract='on',
                  camera_buffers=2, camera_backend='opencv', camera_exposure='auto',
                  camera_manual_exposure=78, camera_manual_gain=96,
                  camera_options=[
                      dict(value='auto', label='Automatic — choose the connected camera'),
                      dict(value='2', label='Razer Kiyo Pro — camera 2'),
                  ],
                  connection_configured=True, controller_enabled=False)
    calls = []
    worker_status = dict(worker_running=True, vision_state='idle',
                         controller_enabled=False, controller_context_active=False,
                         receiver_available=False, profile='off', vision_profile='off',
                         version='0.4.0', camera_fps=30.0,
                         camera_fps_requested='auto')
    flags = dict(load_error=False, save_error=False, begin_error=False,
                 pair_error=False, abort_pair=False, expiry=120, pair_delay=.15)
    camera_profile = dict(active=False, phase='idle', candidate=0, total=2,
                          instruction='', results=[], recommendation=None, error=None,
                          cue=None, cue_remaining=0, candidate_remaining=0,
                          candidate_progress=0)
    async with async_playwright() as pw:
        browser = await pw.webkit.launch(headless=True) if '--webkit' in sys.argv else await pw.chromium.launch(channel='chrome', headless=True)
        page = await browser.new_page(viewport={'width':1280,'height':1000})
        errors=[]
        page.on('pageerror', lambda e: errors.append(str(e)))
        async def route(r):
            path=urlsplit(r.request.url).path
            if path=='/setup':return await r.fulfill(body=SETUP,content_type='text/html')
            if path=='/api/config':
                post=r.request.method=='POST';flag='save_error' if post else 'load_error'
                if flags[flag]:flags[flag]=False;return await r.fulfill(status=503,json={'error':'Temporary settings failure'})
                if post:config.update(r.request.post_data_json);config['connection_configured']=True
                return await r.fulfill(json=config)
            if path=='/api/camera-profile':
                if r.request.method=='POST':
                    action=r.request.post_data_json['action']
                    if action=='begin':camera_profile.update(active=True,phase='countdown',candidate=1,instruction='Get ready with one open hand in the camera view.',cue='ready',cue_remaining=3,candidate_remaining=20)
                    elif action in ('cancel','stop'):camera_profile.update(active=False,phase='cancelled',instruction='Your original camera settings are restored. You can start a new test.',error=None,results=[])
                    elif action=='apply':
                        config.update(camera_profile['recommendation']['settings'])
                        return await r.fulfill(json=config)
                return await r.fulfill(json=camera_profile)
            if path.startswith('/api/pair/'):
                calls.append((path,r.request.post_data_json))
                if flags['abort_pair'] and not path.endswith('/begin'):
                    flags['abort_pair']=False;return await r.abort('failed')
                await asyncio.sleep(.15 if path.endswith('/begin') else flags['pair_delay'])
                flag='begin_error' if path.endswith('/begin') else 'pair_error'
                if flags[flag]:flags[flag]=False;return await r.fulfill(status=400,json={'error':'Approval PIN rejected' if flag=='pair_error' else 'Matrix unavailable'})
                if path.endswith('/begin'):return await r.fulfill(json={'certificate_id':'1234ABCD','expires_in':flags['expiry']})
                return await r.fulfill(json={'paired':True})
            if path=='/api/players':
                state=dict(active='default',generation=1,players=[dict(id='default',name='Iain')],progress=dict(course=1,completed=[],lesson=0),needs_center=False,has_saved_calibration=True)
                if r.request.post_data_json['action']=='export':state['backup']=dict(format='virtualglove-hand-setup',version=4,name='Iain')
                return await r.fulfill(json=state)
            if path=='/api/attract':config['matrix_attract']=r.request.post_data_json['mode'];return await r.fulfill(json=config)
            if path=='/api/connection-status':return await r.fulfill(json=dict(app=True,console_configured=True,console_service=True,console_authenticated=True,networking='connected',checked_seconds_ago=1))
            if path=='/api/support-report':return await r.fulfill(json=dict(format='virtualglove-system-report',version=1,privacy=dict(contains_frames=False,contains_pairing_key=False)))
            if path=='/status':return await r.fulfill(json=worker_status)
            if path=='/stream':return await r.fulfill(body="<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480'/>",content_type='image/svg+xml')
            if path=='/api/games':return await r.fulfill(json={'document':'{"games": {}}','revision':'test','profiles':['off'],'has_backup':False})
            if path.startswith('/assets/'):
                f=ROOT/path.lstrip('/')
                if f.is_file():return await r.fulfill(path=str(f))
            if path.startswith('/help-assets/'):
                f=ROOT/'docs/images'/path[len('/help-assets/'):]
                if f.is_file():return await r.fulfill(path=str(f))
            return await r.fulfill(status=404)
        await page.route('**/*',route)
        async def open_page():
            await page.goto('https://pairing.test/setup')
            await expect(page.locator('#receiver')).to_have_value(config['receiver'])
        async def begin(method='code'):
            await page.locator(f'input[name=pair-method][value={method}]').check()
            await page.locator('#pair-begin').click()
            await expect(page.locator('#verified')).to_be_enabled()
            assert calls[-1][1]=={'host':config['receiver'],'method':method}
            await expect(page.locator('#receiver')).to_be_disabled()
            await expect(page.locator('input[name=pair-method][value=code]')).to_be_disabled()
        async def confirm():
            await page.locator('#verified').check()
            await page.locator('#device-code').fill('123')
            await expect(page.locator('#pair-confirm-next')).to_be_disabled()
            await page.locator('#device-code').fill('123456')
            await page.locator('#pair-confirm-next').click()
            await expect(page.locator('#pair-step-3')).to_be_visible()
            assert await page.evaluate("document.activeElement.id") in ('pair-code','pair-password')
        async def responsive():
            for width in (320,390,768,1280):
                await page.set_viewport_size({'width':width,'height':1000})
                assert await page.evaluate('document.documentElement.scrollWidth')<=width,width
        await open_page()
        await expect(page.locator('#camera-rate-status')).to_contain_text('30')
        await expect(page.locator('#camera option')).to_have_count(2)
        await expect(page.locator('#camera')).to_have_value('auto')
        page.on('dialog',lambda dialog:asyncio.create_task(dialog.accept()))
        await page.locator('#camera-profile-start').click()
        await expect(page.locator('#camera-profile-cancel')).to_be_visible()
        await expect(page.locator('#camera-profile-instruction')).to_contain_text('Get ready')
        await expect(page.locator('#camera-profile-view')).to_be_visible()
        await expect(page.locator('#camera-profile-frame')).to_have_attribute('src',re.compile(r'^/stream\?t='))
        await expect(page.locator('#camera-profile-cue')).to_contain_text('Get ready')
        await expect(page.locator('#camera-profile-countdown')).to_have_text('3')
        camera_profile.update(phase='measuring',cue='centre',cue_remaining=5,candidate_remaining=20,candidate_progress=.01,instruction='Hold your open hand comfortably near the centre.')
        await expect(page.locator('#camera-profile-cue')).to_contain_text('centre')
        await expect(page.locator('#camera-profile-time')).to_contain_text('5 seconds left')
        camera_profile.update(cue='sweep',cue_remaining=9,candidate_remaining=15,candidate_progress=.25,instruction='Sweep your hand smoothly between opposite corners.')
        await expect(page.locator('#camera-profile-view')).to_have_attribute('data-cue','sweep')
        await expect(page.locator('#camera-profile-cue')).to_contain_text('opposite corners')
        camera_profile.update(cue='edge',cue_remaining=6,candidate_remaining=6,candidate_progress=.7,instruction='Touch an edge, then return to the centre.')
        await expect(page.locator('#camera-profile-view')).to_have_attribute('data-cue','edge')
        await expect(page.locator('#camera-profile-cue')).to_contain_text('return to centre')
        await expect(page.locator('#camera-save')).to_be_disabled()
        recommended=dict(camera_backend='opencv',capture_isolation='thread',camera_fps=30,camera_buffers=1,camera_exposure='low-latency')
        camera_profile.update(active=False,phase='complete',candidate=2,
                              instruction='Pixel Pal found the best measured settings for this camera.',
                              results=[dict(name='OpenCV test',continuity=1,sample_age_p95_ms=68,valid=True)],
                              recommendation=dict(name='OpenCV recommended',settings=recommended))
        await expect(page.locator('#camera-profile-apply')).to_be_visible(timeout=3000)
        await expect(page.locator('#camera-profile-view')).to_be_hidden()
        await expect(page.locator('#camera-profile-frame')).not_to_have_attribute('src',re.compile(r'.+'))
        await page.locator('#camera-profile-apply').click()
        await expect(page.locator('#camera-profile-recommendation')).to_contain_text('saved')
        camera_profile.update(active=False,phase='error',error='The camera disconnected during the test.')
        await page.reload()
        await expect(page.locator('#camera-profile-cancel')).to_be_visible()
        await expect(page.locator('#camera-profile-cancel')).to_have_text('Stop test')
        await expect(page.locator('#camera-profile-start')).to_be_hidden()
        await page.locator('#camera-profile-cancel').click()
        await expect(page.locator('#camera-profile-start')).to_be_visible()
        await expect(page.locator('#camera-profile-cancel')).to_be_hidden()
        self_profile = camera_profile
        assert self_profile['phase']=='cancelled'
        await expect(page.locator('.connection-indicators li')).to_have_count(6)
        await expect(page.locator('#connection-status-note')).to_contain_text('Console checked 1 seconds ago')
        await expect(page.locator('#connection-status-note')).to_contain_text('do not confirm that a game received input')
        await expect(page.locator('#connection-status-note')).not_to_contain_text('Green:')
        await expect(page.locator('#status-active-destination')).to_have_text('Not active')
        async with page.expect_download() as report_download:
            await page.locator('#support-report').click()
        report=await report_download.value
        assert re.match(r'virtualglove-system-report-\d{4}-\d{2}-\d{2}\.json',report.suggested_filename)
        await expect(page.locator('#support-report-note')).to_contain_text('contains no video')
        await expect(page.locator('#status-tracking')).to_have_attribute('data-state','unknown')
        await expect(page.locator('#status-output')).to_have_attribute('data-state','unknown')
        worker_status.update(controller_enabled=True,controller_context_active=False,
                             receiver_available=False)
        await page.reload()
        await expect(page.locator('#status-output')).to_have_attribute('data-state','good')
        await expect(page.locator('#status-output strong')).to_have_text('Armed — waiting for game')
        worker_status.update(profile='super_glove_ball',vision_profile='super_glove_ball',
                             controller_context_active=True,receiver_active_address=None)
        await page.reload()
        await expect(page.locator('#status-output')).to_have_attribute('data-state','bad')
        await expect(page.locator('#status-output strong')).to_have_text('Receiver unavailable')
        await expect(page.locator('#status-active-destination')).to_have_text('Searching for the paired console')
        worker_status.update(receiver_available=True,receiver_active_address='10.0.2.44')
        await page.reload()
        await expect(page.locator('#status-active-destination')).to_have_text('Authenticated at 10.0.2.44')
        worker_status.update(controller_enabled=False,controller_context_active=False,
                             receiver_available=False,receiver_active_address=None,
                             profile='off',vision_profile='off')
        await page.reload()
        await expect(page.locator('#connection-section')).to_be_visible()
        await expect(page.locator('#pairing-card #pairing-section')).to_be_visible()
        assert await page.locator('body > main > #pairing-section').count() == 0
        await expect(page.locator('#camera-section')).to_be_visible()
        await page.get_by_text('Players and hand-setup backups',exact=True).click()
        await expect(page.locator('#player-name')).to_have_value('Iain')
        async with page.expect_download() as download_info:
            await page.locator('#player-export').click()
        download=await download_info.value
        assert download.suggested_filename=='iain-virtualglove-hand-setup.json'
        assert not await page.locator('#controller-toggle, #shutdown-system, #pair-host').count()
        await expect(page.locator('#pair-password')).to_be_disabled()
        await page.locator('#receiver').fill('draft.local')
        await expect(page.locator('#pair-begin')).to_be_disabled()
        flags['save_error']=True
        await page.get_by_role('button',name='Save connection',exact=True).click()
        await expect(page.locator('#notice')).to_contain_text('Temporary settings failure')
        await expect(page.locator('#receiver')).to_have_value('draft.local')
        await page.get_by_role('button',name='Save connection',exact=True).click()
        await expect(page.locator('#pair-begin')).to_be_enabled()
        config['receiver']='RETROPIE-NAME.local';await open_page()
        await responsive()
        if '--screenshots' in sys.argv:
            await page.evaluate('window.scrollTo(0,0)')
            await page.screenshot(path=str(ROOT/'docs/images/setup-page.png'))
            await page.locator('#camera-section').screenshot(path=str(ROOT/'docs/images/setup-camera.png'))
            await page.locator('#pairing-section').screenshot(path=str(ROOT/'docs/images/setup-pairing-method.png'))
            await page.get_by_role('heading',name='Matrix attract mode',exact=True).locator('..').screenshot(path=str(ROOT/'docs/images/matrix/attract-settings.png'))
        flags['begin_error']=True
        await page.locator('#pair-begin').click()
        await expect(page.locator('#pair-notice')).to_contain_text('Matrix unavailable')
        await begin();await responsive()
        if '--screenshots' in sys.argv:await page.locator('#pairing-section').screenshot(path=str(ROOT/'docs/images/setup-pairing-confirm.png'))
        await confirm();await responsive()
        await page.locator('#pair-submit').click()
        await expect(page.locator('#pair-notice')).to_contain_text('Enter the RetroPie one-time code')
        await expect(page.locator('#pair-notice')).to_be_in_viewport()
        await page.locator('#pair-code').fill('ABCDE-FGHIJ-23456-7ABCD')
        if '--screenshots' in sys.argv:await page.locator('#pairing-section').screenshot(path=str(ROOT/'docs/images/setup-pairing-code.png'))
        n=len(calls)
        await page.locator('#pair-submit').focus()
        # Hold the mouse across a 500 ms refresh: replacing button text used to
        # cancel this click in WebKit, leaving the enabled button unchanged.
        flags['pair_delay']=2
        await page.locator('#pair-submit').click(delay=800)
        await expect(page.locator('#pair-pending')).to_be_visible()
        await expect(page.locator('#pair-pending-heading')).to_be_in_viewport()
        if '--screenshots' in sys.argv:await page.locator('#pairing-section').screenshot(path=str(ROOT/'docs/images/setup-pairing-progress.png'))
        await expect(page.locator('#pair-notice')).to_contain_text('Pairing in progress')
        assert await page.locator('#pairing-section').get_attribute('aria-busy') != 'true'
        await expect(page.locator('#pair-submit')).to_be_disabled()
        await page.locator('#pair-submit').dispatch_event('click')
        await expect(page.locator('#pair-success')).to_be_visible()
        assert len(calls)==n+1
        flags['pair_delay']=.15
        await expect(page.locator('#pair-success-heading')).to_be_in_viewport()
        if '--screenshots' in sys.argv:await page.locator('#pairing-section').screenshot(path=str(ROOT/'docs/images/setup-pairing-complete.png'))
        await expect(page.locator('#device-code')).to_have_value('')
        await expect(page.locator('#pair-code')).to_have_value('')
        await open_page();await begin('ssh')
        await expect(page.locator('#pair-password')).to_be_disabled()
        await confirm();await expect(page.locator('#pair-password')).to_be_enabled()
        await page.locator('#pair-password').fill('not-a-real-password')
        await page.locator('#pair-review').click()
        await expect(page.locator('#pair-password')).to_have_value('')
        await page.locator('#verified').uncheck()
        await expect(page.locator('#pair-password')).to_be_disabled()
        await confirm();await page.locator('#pair-password').fill('not-a-real-password')
        flags['pair_error']=True
        await page.locator('#pair-submit').click()
        await expect(page.locator('#pair-restart')).to_be_visible()
        await expect(page.locator('#pair-password')).to_have_value('')
        await expect(page.locator('#pair-notice')).to_be_in_viewport()
        await expect(page.locator('#verified')).not_to_be_checked()
        await page.locator('#pair-restart').click()
        await expect(page.locator('#verified')).to_be_enabled()
        await confirm();await page.locator('#pair-password').fill('not-a-real-password')
        await page.locator('#pair-submit').click()
        await expect(page.locator('#pair-success')).to_be_visible()
        await open_page();await begin();await confirm()
        await page.locator('#pair-code').fill('ABCDE-FGHIJ-23456-7ABCD')
        flags['abort_pair']=True;await page.locator('#pair-submit').click()
        await expect(page.locator('#pair-restart')).to_be_visible()
        await expect(page.locator('#pair-code')).to_have_value('')
        await open_page();flags['expiry']=2;await begin('ssh');await confirm()
        await page.locator('#pair-password').fill('not-a-real-password')
        await expect(page.locator('#pair-notice')).to_contain_text('expired',timeout=5000)
        await expect(page.locator('#device-code')).to_have_value('')
        await expect(page.locator('#pair-password')).to_have_value('')
        await expect(page.locator('#pair-submit')).to_be_disabled()
        await expect(page.locator('#pair-method-back')).to_be_visible()
        await page.locator('#pair-method-back').click()
        await expect(page.locator('#pair-step-1')).to_be_visible()
        flags['expiry']=120
        config['connection_configured']=False;await open_page()
        await expect(page.locator('#pair-begin')).to_be_disabled()
        await expect(page.locator('#pair-prerequisite')).to_contain_text('Save connection')
        config['connection_configured']=True;flags['load_error']=True
        await page.reload();await expect(page.locator('#setup-retry')).to_be_visible()
        await page.locator('#setup-retry').click();await expect(page.locator('#pair-begin')).to_be_enabled()
        save_settings=page.get_by_role('button',name='Save camera settings',exact=True)
        await page.locator('#camera_fps').select_option('60')
        await save_settings.click();await expect(page.locator('#camera-notice')).to_contain_text('Camera settings saved')
        await expect(save_settings).to_be_enabled()
        assert config['camera_fps']=='60'
        await page.locator('#camera-notice').evaluate("node=>node.textContent=''")
        await page.locator('#camera_fps').select_option('auto')
        await save_settings.click();await expect(page.locator('#camera-notice')).to_contain_text('Camera settings saved')
        await expect(save_settings).to_be_enabled()
        assert config['camera_fps']=='auto'
        for mode in ('off','dim','on'):
            await page.locator('#matrix-attract').select_option(mode)
            await page.get_by_role('button',name='Save attract mode',exact=True).click()
            await expect(page.locator('#attract-notice')).to_contain_text('saved')
            assert config['matrix_attract']==mode
        n=len(calls);await page.goto('http://pairing.test/setup')
        await expect(page.locator('#pair-wizard')).to_be_hidden()
        await expect(page.get_by_role('link',name='Open secure Setup')).to_be_visible()
        assert len(calls)==n
        assert not errors,errors
        await browser.close()
        print('Guided pairing browser checks passed: both methods, gating, failures, expiry, retries, HTTP, responsive layouts, settings and attract mode.')

if __name__=='__main__':
    asyncio.run(main())
