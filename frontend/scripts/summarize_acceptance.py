"""Summarise real saved reports and on-disk bundle measurements, no network."""
import argparse
import gzip
import json
from pathlib import Path
from urllib.parse import urlsplit


def summarize(root, baseline):
    before = json.loads((root / 'baseline-metrics.json').read_text())
    after = json.loads((root / 'final-metrics.json').read_text())
    matrix = json.loads((root / 'preview/geometry.json').read_text())
    zero = json.loads((root / 'zero-matrix/report.json').read_text())
    metrics = {name: {
        'max_cls': max(r['metrics']['cls'] for r in data['rows']),
        'max_api': max(r['metrics']['api_requests'] for r in data['rows']),
        'max_resources': max(r['metrics']['resource_requests'] for r in data['rows']),
        'max_p95_ms': max(r['metrics']['resource_p95_ms'] for r in data['rows']),
    } for name, data in [('baseline', before), ('final', after)]}
    baseline_entry = next((baseline / 'assets').glob('index-*.js'))
    entry = next((root / 'dist/assets').glob('index-*.js'))
    initial = next(r for r in matrix if r.get('route') == '/')
    files = [root / 'dist' / urlsplit(url).path.lstrip('/') for url in set(initial['loadedScripts'])]
    bundle = {
        'baseline_entry': baseline_entry.stat().st_size,
        'baseline_entry_gzip': len(gzip.compress(baseline_entry.read_bytes())),
        'final_entry': entry.stat().st_size,
        'final_entry_gzip': len(gzip.compress(entry.read_bytes())),
        'final_overview_loaded_js': sum(file.stat().st_size for file in files),
        'final_overview_loaded_js_gzip': sum(len(gzip.compress(file.read_bytes())) for file in files),
        'final_overview_js_chunks': len(files),
    }
    return {
        'metrics': metrics, 'budgets': after['budgets'], 'bundle': bundle,
        'overview_chart_tops': [{'width':r['width'], 'height':r['height'], 'zoom':r['zoom'], 'top':r['metrics']['chart']['top']} for r in after['rows'] if r['route'] == '/'],
        'matrix_rows': sum('route' in r for r in matrix),
        'matrix_max_cls': max(r['metrics']['cls'] for r in matrix if 'metrics' in r),
        'interaction_rows': sum('interaction' in r for r in matrix),
        'redirect_rows': sum('redirects' in r for r in matrix),
        'zero_matrix_rows': len(zero['views']),
        'zero_matrix_failed': sum(bool(r['failures']) for r in zero['views']),
        'zero_journeys': sum(len(r['checks']) for r in zero['journeys']),
        'zero_copy_unchanged': zero['copy_unchanged'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    args = parser.parse_args()
    report = summarize(args.root, args.baseline)
    (args.root / 'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
