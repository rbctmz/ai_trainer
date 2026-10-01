import json, os, sys, subprocess, time, socket, signal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from playwright.sync_api import sync_playwright
from tests.e2e.conftest import _free_port, _wait_until, _stop_process_group
root=Path('/private/tmp/ai-trainer-daily-fix-20261001')
evidence=root/'evidence'
source=Path('/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer')
cases=['ordinary','completed','two','partial-brick','ambiguous','stale','conflicting']
manifest={case:json.loads((evidence/f'scenario-{case}.json').read_text())['database_path'] for case in cases}
(evidence/'browser-db-manifest.json').write_text(json.dumps(manifest,indent=2))
api_port,web_port=_free_port(),_free_port()
api_base=f'http://127.0.0.1:{api_port}'
web_base=f'http://127.0.0.1:{web_port}'
env={**os.environ,'PYTHONPATH':str(root)+':'+os.environ['PYTHONPATH'],'API_BASE_URL':api_base}
processes=[];results=[];errors=[];responses=[];writes=[]
shots=evidence/'real-browser';shots.mkdir(exist_ok=True)
try:
    for cmd,cwd,log in [([sys.executable,'-m','uvicorn','audit_app:app','--host','127.0.0.1','--port',str(api_port)],source,evidence/'real-api.log'),(['npm','run','dev','--','-p',str(web_port)],source/'web',evidence/'real-next.log')]:
        with log.open('wb') as f:processes.append(subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True))
    _wait_until(api_base+'/api/health',lambda r:r.status==200,90,processes[0],evidence/'real-api.log')
    _wait_until(web_base+'/',lambda r:r.status<500,180,processes[1],evidence/'real-next.log')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        for case in cases:
            for theme in ['light','dark']:
                context=browser.new_context(viewport={'width':1280,'height':1100})
                context.add_init_script("localStorage.setItem('demo','0');localStorage.setItem('theme',"+json.dumps(theme)+");")
                page=context.new_page()
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('response',lambda r:responses.append({'url':r.url,'status':r.status}) if '/api/' in r.url and r.status>=400 else None)
                def route_request(route):
                    u=urlsplit(route.request.url)
                    if u.hostname not in ['127.0.0.1','localhost']:
                        route.abort();return
                    if u.path.startswith('/api/'):
                        if route.request.method not in ['GET','HEAD','OPTIONS']:
                            writes.append({'method':route.request.method,'url':route.request.url});route.abort();return
                        query=dict(parse_qsl(u.query));query['audit_case']=case
                        route.continue_(url=urlunsplit((u.scheme,u.netloc,u.path,urlencode(query),u.fragment)))
                    else:route.continue_()
                page.route('**/*',route_request)
                for width in [390,978,1280]:
                    page.set_viewport_size({'width':width,'height':1100})
                    page.goto(web_base+'/today',wait_until='networkidle')
                    region=page.get_by_role('region',name='Сводка на сегодня');region.wait_for()
                    text=page.locator('main').inner_text()
                    item={'case':case,'theme':theme,'width':width,'surface':'today','text':text,'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')}
                    results.append(item)
                    page.screenshot(path=str(shots/f'{case}-{theme}-{width}.png'),full_page=True)
                    if width==978:
                        page.get_by_text('Объяснение решения',exact=True).click()
                        results.append({'case':case,'theme':theme,'width':width,'surface':'today-explanation','text':page.locator('main').inner_text(),'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')})
                        page.screenshot(path=str(shots/f'{case}-{theme}-explanation.png'),full_page=True)
                    print(json.dumps({k:v for k,v in item.items() if k!='text'}),flush=True)
                if theme=='light':
                    page.set_viewport_size({'width':978,'height':1100})
                    page.goto(web_base+'/planning',wait_until='networkidle')
                    page.get_by_role('button',name='Недели',exact=True).click()
                    page.wait_for_timeout(500)
                    results.append({'case':case,'theme':theme,'width':978,'surface':'planning','text':page.locator('main').inner_text(),'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')})
                    page.screenshot(path=str(shots/f'{case}-planning.png'),full_page=True)
                    if case in ['completed','two','partial-brick','ambiguous']:
                        page.goto(web_base+'/activities',wait_until='networkidle')
                        # Open the actual synthetic activity details without modifying data.
                        activity=page.locator('tbody tr').first
                        if activity.count():activity.click();page.wait_for_timeout(500)
                        results.append({'case':case,'theme':theme,'width':978,'surface':'activities','text':page.locator('body').inner_text(),'overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')})
                        page.screenshot(path=str(shots/f'{case}-activity.png'),full_page=True)
                context.close()
        browser.close()
finally:
    for p in reversed(processes):_stop_process_group(p)
    (evidence/'real-browser-results.json').write_text(json.dumps({'results':results,'page_errors':errors,'api_errors':responses,'blocked_writes':writes,'processes_stopped':all(p.poll() is not None for p in processes)},ensure_ascii=False,indent=2))
