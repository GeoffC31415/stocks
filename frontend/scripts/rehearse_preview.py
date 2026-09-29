"""Own a disposable synthetic preview server for the complete browser gate."""
import argparse
import subprocess
import sys
from pathlib import Path
from threading import Thread
from preview_demo import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    server = make_server(args.dist, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run([sys.executable, str(Path(__file__).with_name('verify_preview.py')),
                        '--url', f'http://127.0.0.1:{server.server_port}', '--out', str(args.out)],
                       check=True, timeout=300)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()


if __name__ == '__main__': main()
