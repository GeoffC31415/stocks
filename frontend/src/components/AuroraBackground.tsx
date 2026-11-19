export function AuroraBackground() {
  return (
    <div
      data-testid="ambient-background"
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10"
      style={{ background: "var(--bg-base)" }}
    />
  );
}
