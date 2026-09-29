"""Real-time Chrome measurements; conservative budgets fixed before final run."""
import math

# Synthetic loopback fixture, cold context per route. Not WAN/SLA promises.
BUDGETS = {'cls': 0.10, 'api_requests': 15, 'resource_requests': 40, 'resource_p95_ms': 1500}
VIEWPORTS = [(320, 844, 1), (390, 844, 1), (720, 900, 1), (1440, 900, 1), (720, 450, 2)]
ZOOM_NOTE = '200% desktop browser-zoom approximation: 1440x900 physical viewport represented as 720x450 CSS pixels with DPR 2; not native Chrome UI zoom or pinch zoom.'
OBSERVER = """(() => {
 window.__layoutShifts = [];
 new PerformanceObserver(list => {
   for (const e of list.getEntries()) if (!e.hadRecentInput)
     window.__layoutShifts.push({value:e.value, time:e.startTime,
       sources:e.sources.map(s=>({node:s.node?.tagName, text:s.node?.textContent?.slice(0,100), before:s.previousRect.toJSON(), after:s.currentRect.toJSON()}))});
 }).observe({type:'layout-shift', buffered:true});
})()"""


def install_observer(context):
    context.add_init_script(OBSERVER)


def capture_metrics(page):
    raw = page.evaluate("""() => ({observerInstalled:Array.isArray(window.__layoutShifts) && PerformanceObserver.supportedEntryTypes.includes('layout-shift'), shifts:window.__layoutShifts??[], resources:performance.getEntriesByType('resource').map(e=>({url:e.name,duration:e.duration,bytes:e.transferSize})), chart:(()=>{const e=document.querySelector('[aria-label="Snapshot performance chart"]');if(!e)return null;const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height}})(), viewport:{width:innerWidth,height:innerHeight}})""")
    if not raw.get("observerInstalled"):
        raise RuntimeError("Chrome layout-shift observer was not installed/supported")
    # CLS uses the maximum 5s session window with gaps no greater than 1s.
    maximum = total = 0
    start = previous = None
    for shift in raw['shifts']:
        if start is None or shift['time'] - previous > 1000 or shift['time'] - start > 5000:
            total = 0
            start = shift['time']
        total += shift['value']
        maximum = max(maximum, total)
        previous = shift['time']
    resources = raw['resources']
    durations = sorted(row['duration'] for row in resources)
    return {**raw, 'cls': maximum, 'api_requests': sum('/api/' in row['url'] for row in resources),
            'resource_requests': len(resources), 'resource_p95_ms': durations[max(0, math.ceil(len(durations)*.95)-1)] if durations else 0}


def budget_failures(metrics):
    return [f'{key}-budget: {metrics[key]} > {limit}' for key, limit in BUDGETS.items() if metrics[key] > limit]


def chart_fold_failure(metrics, *, critical_warning=False, zoom=1):
    # Warned/unavailable windows retain their disclosures rather than being
    # compressed to satisfy the ordinary chart-first fixture. Zoom checks
    # readability/overflow, not an impossible halved-height above-fold claim.
    if critical_warning or zoom != 1:
        return None
    chart = metrics.get('chart')
    if not chart or not 0 <= chart['top'] < metrics['viewport']['height']:
        return 'primary-performance-below-initial-viewport'
    return None
