# Project: VirtualGlove
# File: tests/browser_dashboard_controls.py
# Purpose: Verify Dashboard clicks remain reliable across live status refreshes.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-06 - Cover WebKit button replacement and centering request regressions.
# Full history: docs/CHANGELOG.md and Git history.

"""Run with PYTHONPATH=src python tests/browser_dashboard_controls.py.
Requires Playwright WebKit; never connects to real devices.
"""
import asyncio
from playwright.async_api import async_playwright
from powerglove_vision.dashboard_web import DASHBOARD
async def main():
 """Exercise delayed physical clicks across the polling interval."""
 async with async_playwright() as p:
  b=await p.webkit.launch();page=await b.new_page();calls=[]
  status=dict(vision_state='active',active_profile='super_glove_ball',camera_available=True,
              connection_configured=True,controller_enabled=False,calibrated=True,
              player={'needs_center':True})
  async def route(r):
   """Keep every browser request isolated from actual devices."""
   path=r.request.url.split('test')[-1]
   if path=='/dashboard':return await r.fulfill(body=DASHBOARD,content_type='text/html')
   if path=='/status':return await r.fulfill(json=status)
   if r.request.method=='POST':calls.append(path);return await r.fulfill(json={})
   return await r.fulfill(status=404)
  await page.route('**/*',route);await page.goto('http://dashboard.test/dashboard');await page.wait_for_timeout(600)
  for button in ['center','controller-toggle']:
   calls.clear();await page.locator('#'+button).click(delay=400);await page.wait_for_timeout(200);assert calls==(['/calibrate'] if button=='center' else ['/api/controller']), (button,calls)
  status.update(vision_state='error',camera_available=False,
                vision_error="camera 'auto' is unavailable; waiting for a USB camera")
  await page.wait_for_timeout(400)
  assert await page.locator('#camera').is_hidden()
  assert not await page.locator('#camera').get_attribute('src')
  assert await page.locator('#camera-idle').inner_text()=='Camera unavailable. Connect a USB camera to use gesture controls.'
  await b.close()
asyncio.run(main())
