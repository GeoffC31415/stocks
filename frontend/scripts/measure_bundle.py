"""Measure saved baseline, route entry, and browser-loaded Overview JS bytes."""
import argparse
import gzip
import json
from pathlib import Path
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', required=True, type=Path)
parser.add_argument('--dist', required=True, type=Path)
parser.add_argument('--geometry', required=True, type=Path)
args = parser.parse_args()
rows = json.loads(args.geometry.read_text())
initial = next(row for row in rows if row.get('route') == '/')
files = [args.dist / urlsplit(url).path.lstrip('/') for url in set(initial['loadedScripts'])]
entry = next((args.dist / 'assets').glob('index-*.js'))
print(json.dumps({
    'baseline_bytes': args.baseline.stat().st_size,
    'baseline_gzip': len(gzip.compress(args.baseline.read_bytes())),
    'entry_bytes': entry.stat().st_size,
    'entry_gzip': len(gzip.compress(entry.read_bytes())),
    'overview_loaded_js_bytes': sum(file.stat().st_size for file in files),
    'overview_loaded_js_gzip': sum(len(gzip.compress(file.read_bytes())) for file in files),
    'overview_loaded_js_chunks': len(files),
    'geometry_rows': len([row for row in rows if 'route' in row]),
    'small_targets': sum(len(row.get('smallTargets', [])) for row in rows),
    'wrapped_nav': sum(len(row.get('wrappedNavLabels', [])) for row in rows),
}, indent=2))
