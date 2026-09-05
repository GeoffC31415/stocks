import { Navigate, useLocation } from "react-router-dom";

export function legacyRedirectUrl(target: string, tab: string | null, search: string): string {
  const params = new URLSearchParams(search);
  if (tab) params.set("tab", tab);
  const query = params.toString();
  return query ? `${target}?${query}` : target;
}

// Workspace tabs are local to their route; all investigation filters survive.
// Explicit target parameters override the current location, including legacy inst links.
export function scopedNavigationUrl(target: string, search: string): string {
  const [path, query = ""] = target.split("?");
  const params = new URLSearchParams(search);
  params.delete("tab");
  new URLSearchParams(query).forEach((value, key) => params.set(key, value));
  const encoded = params.toString();
  return encoded ? `${path}?${encoded}` : path;
}

export function LegacyRedirect({ target, tab }: { target: string; tab?: string }) {
  const location = useLocation();
  return (
    <Navigate
      replace
      to={legacyRedirectUrl(target, tab ?? null, location.search)}
    />
  );
}
