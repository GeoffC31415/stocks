import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { metricGlossary, type MetricTopic } from "../lib/metricGlossary";

/** Non-modal, viewport-bounded definition popover with explicit focus return. */
export function MetricInfo({ label, topic, context, iconOnly = false }: { label: string; topic: MetricTopic; context?: string; iconOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 16, left: 16 });
  const button = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const id = useId();
  const info = metricGlossary[topic];
  const close = () => { setOpen(false); button.current?.focus({ preventScroll: true }); };

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = button.current?.getBoundingClientRect();
      const box = popover.current?.getBoundingClientRect();
      if (!anchor || !box) return;
      setPosition({
        left: Math.max(16, Math.min(anchor.left, window.innerWidth - box.width - 16)),
        top: Math.max(16, Math.min(anchor.bottom + 8, window.innerHeight - box.height - 16)),
      });
    };
    place();
    popover.current?.focus({ preventScroll: true });
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const pointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!button.current?.contains(target) && !popover.current?.contains(target)) close();
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); close(); } };
    document.addEventListener("pointerdown", pointer);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", pointer);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <>
    <button ref={button} type="button" aria-label={`About ${label}`} aria-expanded={open}
      aria-haspopup="dialog" aria-controls={open ? id : undefined}
      onClick={() => open ? close() : setOpen(true)}
      className={`inline-flex min-h-9 ${iconOnly ? "min-w-9 shrink-0 justify-center" : "min-w-0"} max-w-full items-center gap-1 rounded-md px-1 text-xs text-slate-300 [overflow-wrap:anywhere] focus-visible:outline`}>
      <Info size={14} aria-hidden="true" />{!iconOnly && <span>About {label}</span>}
    </button>
    {open && createPortal(<div id={id} ref={popover} role="dialog" aria-label={`${label} definition`}
      tabIndex={-1} style={{ ...position, width: "min(320px, calc(100vw - 32px))", maxHeight: "calc(100dvh - 32px)" }}
      className="surface-overlay fixed z-50 space-y-3 overflow-auto rounded-xl p-4 text-sm text-slate-200 shadow-lg">
      <p className="font-semibold">{label}</p>
      {context && <p className="text-xs text-slate-300">{context}</p>}
      <p>{info.definition}</p><p className="text-slate-300">{info.limitations}</p>
      <button type="button" onClick={close} className="min-h-11 rounded-lg border border-slate-400/40 px-3">Close definition</button>
    </div>, document.body)}
  </>;
}
