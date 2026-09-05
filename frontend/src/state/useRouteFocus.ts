import { useEffect, useRef, type RefObject } from "react";
import { useNavigationType } from "react-router-dom";

/** Announce new workspaces without stealing text-input or back-navigation focus. */
export function useRouteFocus(root: RefObject<HTMLElement | null>, routeKey: string) {
  const navigation = useNavigationType();
  const previous = useRef(routeKey);
  useEffect(() => {
    if (previous.current === routeKey) return;
    previous.current = routeKey;
    if (navigation === "POP") return;
    const editing = () => document.activeElement instanceof HTMLElement && (
      document.activeElement.matches("input, textarea, select") || document.activeElement.isContentEditable
    );
    if (editing()) return;
    const focus = () => {
      if (editing()) return true;
      const heading = root.current?.querySelector<HTMLElement>("h1, h2, [role='alert']");
      if (!heading) return false;
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      return true;
    };
    if (focus() || !root.current) return;
    const observer = new MutationObserver(() => { if (focus()) observer.disconnect(); });
    observer.observe(root.current, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [navigation, root, routeKey]);
}
