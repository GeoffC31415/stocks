"""Real TLS/ASGI/WebAuthn rehearsal on exclusively synthetic loopback state.

No public ACME, trust installation, broker network, production DB or service changes.
A CDP virtual authenticator proves browser/server cryptography, NOT Dashlane enrollment.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def rehearsal_environment(inherited, output: Path, dist: Path, origin: str, password_hash: str, mode: str):
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or parsed.hostname != 'localhost' or not parsed.port:
        raise ValueError('Only an explicit HTTPS localhost port is permitted')
    env = {k: v for k, v in inherited.items() if not k.startswith('PORTFOLIO_')}
    env.update({
        'PYTHONPATH': str(ROOT / 'backend'), 'PYTHONDONTWRITEBYTECODE': '1',
        'PORTFOLIO_DEPLOYMENT_MODE': 'public', 'PORTFOLIO_PUBLIC_ORIGIN': origin,
        'PORTFOLIO_AUTH_MODE': mode, 'PORTFOLIO_AUTH_USERNAME': 'rehearsal',
        'PORTFOLIO_AUTH_PASSWORD_HASH': password_hash,
        'PORTFOLIO_AUTH_DATABASE_PATH': str(output / 'auth.sqlite3'),
        'PORTFOLIO_DATABASE_URL': f"sqlite+aiosqlite:///{output / 'portfolio-synthetic.db'}",
        'PORTFOLIO_FRONTEND_DIST': str(dist.resolve()),
        'PORTFOLIO_SYNC_INBOX': str(output / 'empty-inbox'),
        'PORTFOLIO_BROWSER_PROFILE': str(output / 'never-used-browser'),
        'PORTFOLIO_SYNC_SERVICE_TRIGGER_ENABLED': 'false',
        'XDG_DATA_HOME': str(output / 'caddy-data'),
        'XDG_CONFIG_HOME': str(output / 'caddy-config'),
        'STOCKS_REHEARSAL_ROOT': str(output.resolve()),
    })
    return env


def proxy_config(tls_port: int, backend_port: int):
    for port in (tls_port, backend_port):
        if not 1024 < port < 65536:
            raise ValueError('Only high ports allowed')
    return f'''{{
    admin off
    auto_https disable_redirects
    skip_install_trust
}}
https://localhost:{tls_port} {{
    bind 127.0.0.1
    tls internal
    request_body {{
        max_size 10MiB
    }}
    reverse_proxy 127.0.0.1:{backend_port} {{
        header_up -Forwarded
        header_up X-Forwarded-For {{remote_host}}
        header_up X-Forwarded-Proto {{scheme}}
        header_up X-Forwarded-Host {{host}}
    }}
}}
'''


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def serve(port):
    """Child-only guarded app startup. Every SQLite connection stays in its scratch dir."""
    import pydantic_settings
    allowed = Path(os.environ['STOCKS_REHEARSAL_ROOT']).resolve()
    original = pydantic_settings.BaseSettings.__init__

    def no_dotenv(self, *args, **kwargs):
        kwargs['_env_file'] = None
        original(self, *args, **kwargs)

    pydantic_settings.BaseSettings.__init__ = no_dotenv

    def audit(event, args):
        if event == 'sqlite3.connect':
            value = str(args[0])
            if value != ':memory:' and not Path(value).resolve().is_relative_to(allowed):
                raise AssertionError('Rehearsal attempted database outside private scratch directory')
        if event == 'socket.connect' and args[0].family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError('Backend outbound network is forbidden in passkey rehearsal')

    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT / 'backend'))
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, proxy_headers=True,
                forwarded_allow_ips='127.0.0.1', access_log=False, server_header=False)


CEREMONY_JS = """async ({kind, label}) => {
  const prefix = '/api/auth/' + kind;
  const issued = await fetch(prefix + '/options', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(kind === 'register' ? {label} : {})});
  if (!issued.ok) throw new Error('options status ' + issued.status);
  const ticket = await issued.json();
  const options = kind === 'register' ? PublicKeyCredential.parseCreationOptionsFromJSON(ticket.options) : PublicKeyCredential.parseRequestOptionsFromJSON(ticket.options);
  const credential = kind === 'register' ? await navigator.credentials.create({publicKey:options}) : await navigator.credentials.get({publicKey:options});
  const verified = await fetch(prefix + '/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ceremony_id:ticket.ceremony_id,credential:credential.toJSON()})});
  if (!verified.ok) throw new Error('verify status ' + verified.status);
  const session = await verified.json();
  const replay = await fetch(prefix + '/verify', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ceremony_id:ticket.ceremony_id,credential:credential.toJSON()})});
  return {session, replay_status:replay.status};
}"""


def main():
    import httpx
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serve', type=int)
    parser.add_argument('--caddy', type=Path)
    parser.add_argument('--dist', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return
    if not all((args.caddy, args.dist, args.output)):
        parser.error('--caddy, --dist and --output are required')
    if not args.caddy.is_file() or not (args.dist / 'index.html').is_file():
        parser.error('Existing Caddy binary and built frontend are required')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = args.output.resolve()
    sys.path.insert(0, str(ROOT / 'backend'))
    from app.security import hash_password
    password = secrets.token_urlsafe(32)
    tls_port, backend_port = free_port(), free_port()
    while tls_port == backend_port:
        backend_port = free_port()
    origin = f'https://localhost:{tls_port}'
    env = rehearsal_environment(os.environ, output, args.dist, origin, hash_password(password), 'basic')
    config = output / 'Caddyfile'
    config.write_text(proxy_config(tls_port, backend_port))
    report = {'origin': origin, 'data': 'synthetic only', 'authenticator': 'CDP virtual, NOT Dashlane', 'checks': []}
    processes, logs = [], []

    def spawn(name, command):
        log = (output / f'{name}.log').open('a')
        logs.append(log)
        p = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=log)
        processes.append(p)
        return p

    def stop(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def app_start():
        return spawn('app', [sys.executable, '-B', str(Path(__file__).resolve()), '--serve', str(backend_port)])

    def ready():
        deadline = time.monotonic() + 30
        # Certificate bypass is ONLY readiness on this private loopback CA.
        with httpx.Client(verify=False, trust_env=False, timeout=1) as c:
            while time.monotonic() < deadline:
                if app_process.poll() is not None or proxy.poll() is not None:
                    raise RuntimeError('Rehearsal child exited; inspect private logs')
                try:
                    if c.get(origin + '/api/health').status_code == 401:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
        raise TimeoutError('Loopback readiness failed')

    browser = None
    try:
        app_process = app_start()
        proxy = spawn('caddy', [str(args.caddy.resolve()), 'run', '--config', str(config), '--adapter', 'caddyfile'])
        ready()
        roots = list((output / 'caddy-data').rglob('root.crt'))
        assert len(roots) == 1
        tls = ssl.create_default_context(cafile=str(roots[0]))
        with httpx.Client(verify=tls, trust_env=False, timeout=5) as client:
            assert client.get(origin + '/api/health').status_code == 401
            response = client.get(origin + '/api/auth/session', auth=('rehearsal', password))
            assert response.status_code == 200, f'Auth status missing: {response.status_code}'
            assert response.json()['mode'] == 'basic'
        report['checks'].append('TLS verified, anonymous API denied, migration mode explicit')
        with sync_playwright() as pw:
            chrome = shutil.which('google-chrome') or shutil.which('chromium')
            assert chrome, 'Existing Chrome is required'
            browser = pw.chromium.launch(executable_path=chrome, headless=True)
            context = browser.new_context(ignore_https_errors=True,
                                          http_credentials={'username': 'rehearsal', 'password': password},
                                          viewport={'width': 1280, 'height': 900})
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(origin + '/') else route.abort())
            page = context.new_page()
            page.set_default_timeout(10000)
            page_errors = []
            page.on('pageerror', lambda err: page_errors.append(str(err)))
            cdp = context.new_cdp_session(page)
            cdp.send('WebAuthn.enable')
            authenticator = cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {
                'protocol': 'ctap2', 'transport': 'usb', 'hasResidentKey': True,
                'hasUserVerification': True, 'isUserVerified': True,
                'automaticPresenceSimulation': True,
            }})['authenticatorId']
            page.goto(origin + '/', wait_until='networkidle')
            page.get_by_role('button', name='Security / passkeys', exact=True).click()
            page.get_by_label('Passkey name', exact=True).fill('Synthetic primary')
            with page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/register/verify') as registration_response:
                page.get_by_role('button', name='Add passkey', exact=True).click()
            verified_registration = registration_response.value
            assert verified_registration.status == 200
            registered_session = verified_registration.json()
            assert registered_session['passkey_authenticated'] is True
            replay_status = page.evaluate("async(body)=>(await fetch('/api/auth/register/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).status", verified_registration.request.post_data_json)
            assert replay_status >= 400
            page.get_by_text('Synthetic primary', exact=True).wait_for()
            page.screenshot(path=str(output / 'passkey-enrollment-desktop.png'), full_page=True)
            report['checks'].append('Built frontend Basic bootstrap enrollment, resident WebAuthn UV and replay denial verified')
            cookies = context.cookies()
            session_cookies = [c for c in cookies if c['name'] == '__Host-stocks_session']
            assert len(session_cookies) == 1
            assert session_cookies[0]['secure'] and session_cookies[0]['httpOnly']
            assert session_cookies[0]['sameSite'] == 'Strict' and session_cookies[0]['path'] == '/'
            report['checks'].append('Secure HttpOnly Strict host-only session cookie issued')
            # Preserve enrolled credential/session store while changing ONLY synthetic app mode.
            stop(app_process)
            env['PORTFOLIO_AUTH_MODE'] = 'passkey'
            app_process = app_start()
            ready()
            with httpx.Client(verify=tls, trust_env=False, timeout=5) as client:
                assert client.get(origin + '/api/health', auth=('rehearsal', password)).status_code == 401
                assert client.get(origin + '/', headers={'Accept': 'text/html'}).status_code == 200
            persisted = page.evaluate("async()=>({status:(await fetch('/api/health')).status, session:await(await fetch('/api/auth/session')).json()})")
            assert persisted['status'] == 200 and persisted['session']['mode'] == 'passkey'
            report['checks'].append('Session persists restart; passkey-only rejects valid old Basic; anonymous shell available')
            page.goto(origin + '/portfolio?tab=groups', wait_until='networkidle')
            assert 'Groups' in page.locator('body').inner_text()
            page.screenshot(path=str(output / 'passkey-authenticated-desktop.png'), full_page=True)
            # Check CSRF and public broker guards without ever reaching a real provider.
            with httpx.Client(verify=tls, trust_env=False, timeout=5) as client:
                client.cookies.set('__Host-stocks_session', session_cookies[0]['value'])
                assert client.post(origin + '/api/groups', json={'name':'forbidden'}).status_code == 403
                assert client.post(origin + '/api/groups', headers={'Origin':'https://evil.test'}, json={'name':'forbidden'}).status_code == 403
            result = page.evaluate("""async()=>{
                const p=await fetch('/api/groups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Synthetic passkey rehearsal'})});
                const item=await p.json();const all=await(await fetch('/api/groups')).json();
                const del=await fetch('/api/groups/'+item.id,{method:'DELETE'});
                const after=await(await fetch('/api/groups')).json();
                return {created:p.status,exists:all.some(x=>x.id===item.id),removed:del.status,absent:!after.some(x=>x.id===item.id)};
            }""")
            assert result == {'created':201,'exists':True,'removed':204,'absent':True}
            report['checks'].append('Origin checks and real session-authorized synthetic write/read/delete verified')
            # API logout immediately revokes the token; saved old token cannot be replayed.
            assert page.evaluate("async()=>(await fetch('/api/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status") == 200
            with httpx.Client(verify=tls, trust_env=False, timeout=5) as client:
                client.cookies.set('__Host-stocks_session', session_cookies[0]['value'])
                assert client.get(origin + '/api/health').status_code == 401
            page.reload(wait_until='networkidle')
            page.screenshot(path=str(output / 'passkey-login-desktop.png'), full_page=True)
            # Prefer actual built UI sign-in control, not merely an API-only proof.
            button = page.get_by_role('button', name='Sign in with a passkey', exact=True)
            if button.count() == 0:
                raise AssertionError('Expected accessible passkey sign-in UI')
            with page.expect_response(lambda response: urlsplit(response.url).path == '/api/auth/login/verify') as login_response:
                button.click()
            verified_response = login_response.value
            assert verified_response.status == 200
            assert verified_response.json()['passkey_authenticated'] is True
            page.get_by_role('button', name='Log out', exact=True).wait_for()
            post_login_health = page.evaluate("async()=>(await fetch('/api/health')).status")
            report['login_diagnostics'] = {
                'health_status': post_login_health,
                'session': page.evaluate("async()=>await(await fetch('/api/auth/session')).json()"),
                'cookie_metadata': [{k:c[k] for k in ('name','domain','path','secure','httpOnly','sameSite','expires')} for c in context.cookies()],
            }
            assert post_login_health == 200, f'Post-login health status {post_login_health}'
            report['checks'].append('Logout revokes replayed cookie; built frontend performs fresh WebAuthn login')
            # Enrol an independent virtual backup device, then revoke the first.
            first_id = page.evaluate("async()=>(await(await fetch('/api/auth/credentials')).json()).credentials[0].id")
            cdp.send('WebAuthn.removeVirtualAuthenticator', {'authenticatorId': authenticator})
            authenticator = cdp.send('WebAuthn.addVirtualAuthenticator', {'options': {
                'protocol': 'ctap2', 'transport': 'usb', 'hasResidentKey': True,
                'hasUserVerification': True, 'isUserVerified': True,
                'automaticPresenceSimulation': True,
            }})['authenticatorId']
            backup = page.evaluate(CEREMONY_JS, {'kind':'register','label':'Synthetic independent backup'})
            assert backup['session']['passkey_authenticated'] is True
            removed = page.evaluate("async(id)=>(await fetch('/api/auth/credentials/'+encodeURIComponent(id),{method:'DELETE'})).status", first_id)
            assert removed == 200
            remaining = page.evaluate("async()=>(await(await fetch('/api/auth/credentials')).json()).credentials")
            assert len(remaining) == 1 and remaining[0]['label'] == 'Synthetic independent backup'
            assert page.evaluate("async(id)=>(await fetch('/api/auth/credentials/'+encodeURIComponent(id),{method:'DELETE'})).status", remaining[0]['id']) == 409
            current_cookie = next(c for c in context.cookies() if c['name'] == '__Host-stocks_session')
            assert page.evaluate("async()=>(await fetch('/api/auth/logout-all',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status") == 200
            with httpx.Client(verify=tls, trust_env=False, timeout=5) as client:
                client.cookies.set('__Host-stocks_session', current_cookie['value'])
                assert client.get(origin + '/api/health').status_code == 401
            report['checks'].append('Independent backup enrolled; old credential revoked; last-key deletion refused; logout-all revokes saved cookie')
            # Exercise the real local operator CLI on this synthetic store only.
            recovery_file = output / 'synthetic-recovery-token.txt'
            recovery = subprocess.run([sys.executable, '-B', '-m', 'app.auth_cli', '--database',
                str(output / 'auth.sqlite3'), 'recover', '--output', str(recovery_file)],
                env=env, cwd=ROOT, capture_output=True, text=True, timeout=10, check=True)
            recovery_token = recovery_file.read_text().strip()
            assert recovery_token not in recovery.stdout + recovery.stderr
            assert recovery_file.stat().st_mode & 0o777 == 0o600
            recovered = page.evaluate("""async(token)=>{
                const body=JSON.stringify({token,label:'Synthetic recovered key'});
                const opts=await fetch('/api/auth/recovery/options',{method:'POST',headers:{'Content-Type':'application/json'},body});
                if(!opts.ok)throw new Error('recovery options '+opts.status);
                const ticket=await opts.json();
                const reused=await fetch('/api/auth/recovery/options',{method:'POST',headers:{'Content-Type':'application/json'},body});
                const credential=await navigator.credentials.create({publicKey:PublicKeyCredential.parseCreationOptionsFromJSON(ticket.options)});
                const result=await fetch('/api/auth/register/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ceremony_id:ticket.ceremony_id,credential:credential.toJSON()})});
                return {status:result.status,reused:reused.status,session:await result.json()};
            }""", recovery_token)
            assert recovered['status'] == 200 and recovered['reused'] >= 400
            assert recovered['session']['passkey_authenticated'] is True
            recovery_file.unlink()
            del recovery_token
            remaining = page.evaluate("async()=>(await(await fetch('/api/auth/credentials')).json()).credentials")
            assert len(remaining) == 1 and remaining[0]['label'] == 'Synthetic recovered key'
            report['checks'].append('Private local recovery CLI and one-use browser enrollment verified; old credentials replaced')
            page.reload(wait_until='networkidle')
            assert not page_errors, page_errors
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(output / 'passkey-authenticated-mobile.png'), full_page=True)
            cdp.send('WebAuthn.removeVirtualAuthenticator', {'authenticatorId': authenticator})
            browser.close()
            browser = None
        report['result'] = 'passed'
    except Exception as exc:
        report['result'] = 'failed'
        report['error_type'] = type(exc).__name__
        # No response bodies or bearer credentials in the report.
        raise
    finally:
        if browser:
            try:
                browser.close()
            except PlaywrightError:
                report['browser_close_error'] = True
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()
        report['children_stopped'] = all(p.poll() is not None for p in processes)
        (output / 'report.json').write_text(json.dumps(report, indent=2))
        for child in output.iterdir():
            if child.is_file():
                child.chmod(0o600)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
