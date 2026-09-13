# Project: VirtualGlove
# File: tests/browser_joystick_deadzone.py
# Purpose: Exercise Setup dead-zone controls in isolated browser engines.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Added browser coverage for per-player dead-zone controls.
# Full history: docs/CHANGELOG.md and Git history.
"""Exercise Setup slider saves, live states, retries and player changes in isolated browsers."""
import asyncio
import base64
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect
from powerglove_vision.joystick_web import JOYSTICK_CONTENT, JOYSTICK_SCRIPT
from powerglove_vision.web_common import _page

async def main():
    async with async_playwright() as pw:
        for engine in ('chromium', 'webkit'):
            browser = await getattr(pw, engine).launch(**({'channel':'chrome'} if engine=='chromium' else {}))
            page = await browser.new_page(viewport={'width':390,'height':844})
            state=dict(active='default',generation=1,players=[dict(id='default',name='Iain')],
                       joystick=dict(deadzone=.28,effective_deadzone=.30,jitter_protected=False,
                                     hand_size_protected=True,hand_size_minimum=.30))
            calls=[]; errors=[]; flags={'fail':False, 'tracking':True, 'practice':False, 'calibrating':False, 'calibration_polls':0}
            page.on('pageerror',lambda e:errors.append(str(e)))
            async def route(r):
                path=urlsplit(r.request.url).path
                if path=='/setup':return await r.fulfill(body=_page('Joystick test',JOYSTICK_CONTENT,JOYSTICK_SCRIPT),content_type='text/html')
                if path=='/status':
                    calibrating=flags['calibrating']
                    if calibrating:
                        flags['calibration_polls']+=1
                        if flags['calibration_polls']>1:
                            flags['calibrating']=False;calibrating=False;state['generation']+=1
                    return await r.fulfill(json=dict(vision_state='active',practice_mode=flags['practice'],detected=flags['tracking'],calibrated=not calibrating,calibrating=calibrating,player=dict(active=state['active'],generation=state['generation'],needs_center=False),dpad=dict(left=True,right=False,up=False,down=False),palm_position=dict(x=.2,y=.5),joystick_grid=dict(anchor=dict(x=.5,y=.5),center=dict(x=.5,y=.5),half_size=state['joystick']['effective_deadzone']/2,minimum_size=.30)))
                if path=='/api/practice':
                    data=r.request.post_data_json
                    assert set(data)=={'session','enabled'} and data['session']
                    flags['practice']=data['enabled']
                    return await r.fulfill(json=dict(practice_mode=flags['practice'],session_active=flags['practice']))
                if path=='/calibrate':
                    assert flags['practice']
                    calls.append(dict(action='calibrate'))
                    flags['calibrating']=True;flags['calibration_polls']=0
                    return await r.fulfill(status=204)
                if path=='/stream':return await r.fulfill(body=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='),content_type='image/png')
                if path=='/api/players':
                    data=r.request.post_data_json
                    if data['action']=='joystick_deadzone':
                        calls.append(data)
                        if flags['fail']:return await r.fulfill(status=400,json={'error':'Save failed; retry.'})
                        state['generation']+=1
                        state['joystick']=dict(deadzone=data['value'],effective_deadzone=max(data['value'],.30),jitter_protected=False,
                                               hand_size_protected=data['value']<.30,hand_size_minimum=.30)
                    return await r.fulfill(json=state)
                return await r.fulfill(status=404)
            await page.route('**/*',route);await page.goto('http://joystick.test/setup')
            await expect(page.locator('#joystick-size')).to_be_enabled()
            await expect(page.locator('label[for=joystick-size]')).to_have_text('Center box size: Small ↔ Large')
            await expect(page.locator('#joystick-value')).to_contain_text('28% of camera frame width and height')
            await expect(page.locator('[data-direction=left]')).to_have_text('Left: off')
            await expect(page.locator('#joystick-camera')).to_be_hidden()
            await expect(page.locator('#joystick-camera-toggle')).to_have_text('Turn on camera')
            await page.locator('#joystick-camera-toggle').click()
            await expect(page.locator('#joystick-camera-toggle')).to_have_text('Turn off camera')
            await expect(page.locator('#joystick-camera')).to_be_visible()
            await expect(page.locator('#joystick-grid')).to_be_visible()
            await expect(page.locator('#joystick-center')).to_be_enabled()
            await page.locator('#joystick-center').click()
            await expect(page.locator('#joystick-center-status')).to_contain_text('Hand center saved')
            assert sum(call.get('action')=='calibrate' for call in calls)==1
            await expect(page.locator('#joystick-region')).to_have_attribute('data-region','3')
            assert await page.locator('#joystick-default').evaluate('(button)=>button.parentElement===document.getElementById("joystick-camera-toggle").parentElement')
            await expect(page.locator('[data-direction=left]')).to_have_text('Left: pressed')
            await page.locator('#joystick-size').focus();await page.keyboard.press('Home')
            for _ in range(40):await page.keyboard.press('ArrowRight')
            # Read synchronously with the input event: no polling round trip is needed.
            assert await page.locator('#joystick-grid-left').get_attribute('x1') == '0.25'
            await expect(page.locator('#joystick-value')).to_contain_text('Unsaved preview')
            await page.locator('#joystick-camera-toggle').click()
            await page.locator('#joystick-camera-toggle').click()
            await expect(page.locator('#joystick-grid')).to_be_visible()
            assert await page.locator('#joystick-grid-left').get_attribute('x1') == '0.25'
            await page.wait_for_timeout(1200)
            await expect(page.locator('#joystick-size')).to_have_value('0.5')
            await page.locator('#joystick-save').click(delay=300)
            await expect(page.locator('#joystick-notice')).to_contain_text('Dead zone saved')
            assert calls[-1]['value']==.5 and calls[-1]['generation']==2
            await page.locator('#joystick-default').click();flags['fail']=True
            await page.locator('#joystick-save').click();await expect(page.locator('#joystick-notice')).to_contain_text('Save failed')
            await expect(page.locator('#joystick-size')).to_have_value('0.6')
            flags['fail']=False
            await page.locator('#joystick-save').click();await expect(page.locator('#joystick-notice')).to_contain_text('Dead zone saved')
            await page.locator('#joystick-size').focus();await page.keyboard.press('End')
            state['active']='second';state['generation']+=1;state['players'].append(dict(id='second',name='Scott'))
            await expect(page.locator('#joystick-player')).to_have_text('Player: Scott')
            await expect(page.locator('#joystick-size')).to_have_value('0.6')
            flags['tracking']=False
            await expect(page.locator('[data-direction=left]')).to_have_text('Left: off')
            await expect(page.locator('#joystick-region')).to_be_hidden()
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.locator('#joystick-settings').screenshot(path='/tmp/joystick-'+engine+'.png')
            await page.locator('#joystick-camera-toggle').click()
            await expect(page.locator('#joystick-camera')).to_be_hidden()
            assert await page.locator('#joystick-camera').get_attribute('src') is None
            await expect(page.locator('#joystick-grid')).to_be_hidden()
            await expect(page.locator('#joystick-live')).to_have_text('Camera test is off.')
            assert not flags['practice']
            assert not errors,errors
            await browser.close()
            print(engine+' joystick checks passed')
asyncio.run(main())
