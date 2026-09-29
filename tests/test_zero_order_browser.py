"""Synthetic zero-order acceptance regression, opt-in isolated dist only."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_analysis_ui as rehearsal


def test_zero_order_performance_and_alternative_journeys(tmp_path):
    dist = os.environ.get('STOCKS_TEST_DIST')
    if not dist:
        pytest.skip('Set STOCKS_TEST_DIST to an isolated build')
    from playwright.sync_api import sync_playwright
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    fixture = tmp_path / 'fixture'
    subprocess.run([sys.executable, str(rehearsal.REPO / 'scripts/synthetic_preview.py'), '--dist', dist,
                    '--output', str(fixture), '--prepare-only'], check=True)
    with (tmp_path / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, str(rehearsal.REPO / 'scripts/verify_analysis_ui.py'),
                                   '--database', str(fixture / 'synthetic.db'), '--dist', dist, '--serve', str(port)], stdout=log, stderr=log)
        try:
            base = f'http://127.0.0.1:{port}'
            rehearsal.wait_ready(server, base)
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
                try:
                    # This invocation is also used by --zero-events in the full matrix.
                    result = rehearsal.verify_view(browser, base, 'performance', 390, tmp_path, zero_events=True)
                    assert not result['failures'], result['failures']
                    result = rehearsal.verify_zero_event_navigation(browser, base)
                    assert not result['failures'], result['failures']
                    assert len(result['checks']) >= 5, result['checks']
                    for width in (320, 390, 720, 768):
                        result = rehearsal.verify_view(browser, base, 'classifications', width, tmp_path, 'long-names', zero_events=True)
                        assert not result['failures'], result['failures']
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
