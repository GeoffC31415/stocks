export function AuroraBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      style={{ background: "var(--bg-base)" }}
    >
      <div
        className="absolute -left-[10%] -top-[20%] h-[60vh] w-[60vh] rounded-full blur-3xl animate-aurora-drift"
        style={{
          background:
            "radial-gradient(circle, rgba(167, 139, 250, 0.45) 0%, rgba(167, 139, 250, 0) 70%)",
        }}
      />
      <div
        className="absolute -right-[15%] top-[5%] h-[55vh] w-[55vh] rounded-full blur-3xl animate-aurora-drift-slow"
        style={{
          background:
            "radial-gradient(circle, rgba(34, 211, 238, 0.40) 0%, rgba(34, 211, 238, 0) 70%)",
        }}
      />
      <div
        className="absolute left-[20%] bottom-[-25%] h-[55vh] w-[70vh] rounded-full blur-3xl animate-aurora-drift"
        style={{
          background:
            "radial-gradient(circle, rgba(99, 102, 241, 0.32) 0%, rgba(99, 102, 241, 0) 70%)",
          animationDelay: "-12s",
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.035] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")",
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(180deg, rgba(7, 10, 26, 0) 0%, rgba(7, 10, 26, 0.55) 100%)",
        }}
      />
    </div>
  );
}
