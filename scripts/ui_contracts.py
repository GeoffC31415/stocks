"""Read-only route contracts and browser measurements for isolated rehearsal."""
from __future__ import annotations

from urllib.parse import urlsplit

# Exact application route templates, never broad /api/* access. Mutations and
# provider refresh endpoints are deliberately absent, including GET refreshes.
COMMON_GETS = {"/api/health", "/api/portfolio/summary", "/api/instruments"}
ROUTES = {
    "overview": {
        "url": "/", "heading": "Performance", "required": "/api/portfolio/performance",
        "gets": {"/api/portfolio/returns", "/api/portfolio/timeseries",
                 "/api/portfolio/attribution", "/api/portfolio/performance", "/api/portfolio/data-confidence",
                 "/api/portfolio/benchmarks", "/api/orders/analytics",
                 "/api/orders/cashflow-timeseries", "/api/orders/estimated-timeseries"},
    },
    "performance": {
        "url": "/portfolio?tab=performance", "heading": "Performance workspace", "required": "/api/portfolio/performance",
        "gets": {"/api/portfolio/performance", "/api/portfolio/returns", "/api/portfolio/timeseries",
                 "/api/orders/analytics", "/api/orders/cashflow-timeseries", "/api/orders/estimated-timeseries"},
    },
    "holdings": {
        "url": "/portfolio?tab=holdings", "heading": "Holdings", "required": "/api/instruments",
        "gets": {"/api/orders/analytics", "/api/orders/positions", "/api/groups",
                 "/api/matching/summary", "/api/instruments/{instrument_id}/history",
                 "/api/instruments/{instrument_id}/orders"},
    },
    "income": {
        "url": "/portfolio?tab=income", "heading": "DRIP purchase proxy", "required": "/api/orders",
        "gets": {"/api/orders", "/api/orders/positions"},
    },
    "orders": {
        "url": "/activity?tab=orders", "heading": "Order history", "required": "/api/orders",
        "gets": {"/api/orders", "/api/orders/analytics", "/api/matching/summary"},
    },
    "allocation": {
        "url": "/portfolio?tab=allocation", "heading": "Allocation & concentration",
        "required": "/api/portfolio/allocation", "gets": {"/api/portfolio/allocation"},
    },
    "returns": {
        "url": "/portfolio?tab=returns", "heading": "Position analysis", "required": "/api/orders/positions",
        "gets": {"/api/orders/positions", "/api/orders/analytics", "/api/groups/performance",
                 "/api/matching/summary"},
    },
    "confidence": {
        "url": "/data?tab=confidence", "heading": "Data confidence", "required": "/api/portfolio/data-confidence",
        "gets": {"/api/portfolio/data-confidence"},
    },
    "classifications": {
        "url": "/data?tab=classifications", "heading": "Classification queue",
        "required": "/api/instruments", "gets": set(),
    },
}


def allowed_gets(view: str | None = None) -> set[str]:
    views = [ROUTES[view]] if view else ROUTES.values()
    return COMMON_GETS.union(*(item["gets"] for item in views))


def request_allowed(method: str, url: str, base: str, view: str) -> bool:
    parsed = urlsplit(url)
    if method != "GET" or parsed.netloc != urlsplit(base).netloc or parsed.scheme != "http":
        return False
    if not parsed.path.startswith("/api/"):
        return True
    from starlette.routing import compile_path

    return any(compile_path(path)[0].fullmatch(parsed.path) for path in allowed_gets(view))


def measure_page(page) -> dict:
    """Use actual rendered SVG tick boxes, not a Recharts mock or screenshot claim."""
    return page.evaluate(r"""() => {
      const box = e => { const r=e.getBoundingClientRect();
        return {left:r.left, right:r.right, top:r.top, bottom:r.bottom}; };
      const axes = [...document.querySelectorAll('.recharts-xAxis-tick-labels')].map(axis => {
        const ticks = [...axis.querySelectorAll('.recharts-cartesian-axis-tick-value')]
          .map(e => ({text:e.textContent, ...box(e)})).sort((a,b)=>a.left-b.left);
        return {ticks, duplicates:ticks.length-new Set(ticks.map(t=>t.text)).size,
          overlaps:ticks.slice(1).filter((t,i)=>t.left<ticks[i].right).length};
      });
      const drawdownAxes = [...document.querySelectorAll('.recharts-yAxis-tick-labels')].map(axis =>
        [...axis.querySelectorAll('.recharts-cartesian-axis-tick-value')]
          .map(e => ({text:e.textContent, ...box(e)})))
        .filter(ticks=>ticks.some(t=>t.text.startsWith('-') && t.text.includes('%')));
      const invertedDrawdown = drawdownAxes.some(ticks => {
        const zero=ticks.find(t=>parseFloat(t.text)===0);
        return zero && ticks.some(t=>parseFloat(t.text)<0 && t.top<zero.top);
      });
      const clippedControls=[...document.querySelectorAll('main button, main [role="tab"]')]
        .filter(e=>e.getClientRects().length).filter(e=>{
          const r=e.getBoundingClientRect();
          if(r.left<0 || r.right>innerWidth+1) return true;
          for(let p=e.parentElement; p; p=p.parentElement){
            const s=getComputedStyle(p), b=p.getBoundingClientRect();
            if(s.overflowX==='hidden' && (r.left<b.left || r.right>b.right)) return true;
          }
          return false;
        }).map(e=>e.textContent?.trim()).filter(Boolean);
      const performance=[...document.querySelectorAll('h2')].find(e=>e.textContent==='Performance');
      const plot=document.querySelector('[aria-label="Snapshot performance chart"]');
      const performanceDots=plot ? [...plot.querySelectorAll('.recharts-area-dot')].map(box) : [];
      const plotBox=plot ? box(plot) : null;
      const clippedObservations=plotBox && performanceDots.some(dot=>
        dot.top<plotBox.top || dot.bottom>plotBox.bottom || dot.left<plotBox.left || dot.right>plotBox.right);
      const luminance = color => {
        const rgb=color.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{
          v/=255; return v<=0.04045 ? v/12.92 : ((v+0.055)/1.055)**2.4;
        });
        return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;
      };
      const cards=[...document.querySelectorAll('.surface-card')];
      const contrast=cards.flatMap(card=>[...card.querySelectorAll('h3,p')].map(text=>{
        const foreground=luminance(getComputedStyle(text).color);
        const background=luminance(getComputedStyle(card).backgroundColor);
        return (Math.max(foreground,background)+0.05)/(Math.min(foreground,background)+0.05);
      }));
      return {viewport:innerWidth, document:document.documentElement.scrollWidth,
        height:document.documentElement.scrollHeight, axes, invertedDrawdown, drawdownAxes,
        solidCards:cards.length, cardMinContrast:contrast.length ? Math.min(...contrast) : null,
        blurredCards:cards.filter(card=>getComputedStyle(card).backdropFilter!=='none').length,
        performanceDots, clippedObservations,
        primaryTop:plotBox ? plotBox.top+scrollY : (performance ? box(performance).top+scrollY : null),
        clippedControls, performanceTop:performance ? box(performance).top+scrollY : null};
    }""")


def geometry_failures(measurement: dict) -> list[str]:
    failures = []
    if measurement["document"] > measurement["viewport"]:
        failures.append("document-overflow")
    if any(axis["duplicates"] for axis in measurement["axes"]):
        failures.append("duplicate-date-labels")
    if any(axis["overlaps"] for axis in measurement["axes"]):
        failures.append("overlapping-date-labels")
    if measurement["invertedDrawdown"]:
        failures.append("inverted-drawdown")
    if measurement["clippedControls"]:
        failures.append("clipped-controls")
    if measurement.get("clippedObservations"):
        failures.append("clipped-observations")
    if measurement.get("cardMinContrast") is not None and measurement["cardMinContrast"] < 4.5:
        failures.append("metric-card-text-contrast")
    if measurement.get("blurredCards"):
        failures.append("blurred-analytical-cards")
    return failures
