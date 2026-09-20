# Project: VirtualGlove
# File: tests/browser_academy_players.py
# Purpose: Verify Academy selection automatically loads the chosen player.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Cover immediate player selection and pending request controls.
# Full history: docs/CHANGELOG.md and Git history.

"""Run with PYTHONPATH=src python tests/browser_academy_players.py.
Requires Playwright WebKit; never connects to real devices.
"""
import asyncio
from playwright.async_api import async_playwright,expect
from virtualglove.academy_web import LEARN
from virtualglove.dashboard_web import DASHBOARD
from virtualglove.control_server import SETUP
async def main():
 """Verify selector changes load the chosen player without another click."""
 async with async_playwright() as pw:
  browser=await pw.webkit.launch();page=await browser.new_page();calls=[]
  s=dict(active='one',generation=1,players=[dict(id='one',name='Iain'),dict(id='two',name='Scott')],progress=dict(course=1,completed=[],lesson=0),needs_center=False,has_saved_calibration=True)
  async def route(r):
   """Serve isolated Academy requests with a delayed player selection."""
   path=r.request.url.split('test')[-1]
   if path in ('/learn','/dashboard','/setup'):return await r.fulfill(body={'/learn':LEARN,'/dashboard':DASHBOARD,'/setup':SETUP}[path],content_type='text/html')
   if path=='/api/config':return await r.fulfill(json=dict(receiver='console.local',port=55355,profile='off',glove_color='none',camera='auto',camera_fps='auto',matrix_attract='on'))
   if path=='/api/games':return await r.fulfill(json=dict(document='{"games":{}}',revision='test',profiles=[],has_backup=False))
   if path=='/api/connection-status':return await r.fulfill(json={})
   if path=='/api/players':
    q=r.request.post_data_json
    if q['action']=='select':
     calls.append(q);await asyncio.sleep(.6);s.update(active=q['id'],generation=2,restoring_calibration=True)
    return await r.fulfill(json=s)
   if path=='/status':return await r.fulfill(json=dict(vision_state='active',detected=False,calibrated=True))
   if r.request.method=='POST':return await r.fulfill(json={})
   return await r.fulfill(status=404)
  await page.route('**/*',route);await page.goto('http://academy.test/learn')
  await expect(page.locator('#player-select')).to_be_enabled()
  await page.locator('#player-select').select_option('two')
  await expect(page.locator('#player-select')).to_be_disabled()
  await expect(page.locator('#player-select')).to_be_enabled()
  assert len(calls)==1 and calls[0]['id']=='two'
  assert await page.locator('#player-use,#player-reuse').count()==0
  await expect(page.locator('#player-select')).to_have_value('two')
  assert await page.locator('#player-create,#player-import').count()==0
  for path in ('/dashboard','/setup'):
   await page.goto('http://academy.test'+path)
   await expect(page.locator('#player-select')).to_be_enabled()
   await expect(page.locator('#player-select')).to_have_value('two')
   await page.locator('#player-select').select_option('one')
   await expect(page.locator('#player-select')).to_be_enabled()
   assert calls[-1]['id']=='one'
   if path=='/dashboard':
    assert await page.locator('#player-create,#player-import').count()==0
    assert await page.locator('#game').evaluate('(e)=>e.parentElement.contains(document.getElementById("game-session"))')
   else:
    assert await page.locator('#player-create,#player-import').count()==2
   for width in (390,768,1280):
    await page.set_viewport_size(dict(width=width,height=1000))
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   s.update(active='two',generation=s['generation']+1)
  print('Shared selection across Academy, Dashboard, and Setup passes in WebKit.')
  await browser.close()
asyncio.run(main())
