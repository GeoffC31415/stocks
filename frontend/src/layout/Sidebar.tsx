import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Database,
  LayoutDashboard,
  Scale,
  Wallet,
} from "lucide-react";
import { NavLink } from "react-router-dom";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
};

export const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/portfolio", label: "Portfolio", icon: Wallet },
  { to: "/activity", label: "Activity", icon: Activity },
  { to: "/tax", label: "Tax", icon: Scale },
  { to: "/data", label: "Data", icon: Database },
];

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-aurora-base/60 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-aurora-accent shadow-glow-accent">
          <BarChart3 size={18} className="text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">Portfolio</p>
          <p className="text-[11px] text-slate-500">Personal analytics</p>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 px-3 py-3">
        <ul className="space-y-1">
          {PRIMARY_NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "text-white"
                      : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive ? (
                      <motion.span
                        layoutId="sidebar-active"
                        className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-violet-500/20 to-cyan-500/20 ring-1 ring-white/10"
                        transition={{ type: "spring", stiffness: 350, damping: 32 }}
                      />
                    ) : null}
                    <item.icon
                      size={17}
                      className={
                        isActive
                          ? "text-aurora-cyan"
                          : "text-slate-500 group-hover:text-slate-300"
                      }
                    />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="px-5 py-4 text-[10px] text-slate-600">
        Private · local portfolio data
      </div>
    </aside>
  );
}
