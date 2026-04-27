import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Wallet,
  History,
  Target,
  Upload,
  Layers,
  BarChart3,
} from "lucide-react";
import { motion } from "framer-motion";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
};

const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/holdings", label: "Holdings", icon: Wallet },
  { to: "/orders", label: "Orders", icon: History },
  { to: "/positions", label: "Positions", icon: Target },
  { to: "/import", label: "Import", icon: Upload },
  { to: "/groups", label: "Groups", icon: Layers },
];

export function Sidebar() {
  return (
    <aside className="hidden lg:flex sticky top-0 h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-aurora-base/60 backdrop-blur-xl">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-aurora-accent shadow-glow-accent">
          <BarChart3 size={18} className="text-white" />
        </div>
        <div>
          <p className="text-sm font-semibold text-white">Portfolio</p>
          <p className="text-[11px] text-slate-500">Aurora dashboard</p>
        </div>
      </div>

      <nav className="flex-1 px-3 py-2">
        <ul className="space-y-1">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "text-white"
                      : "text-slate-400 hover:text-slate-100 hover:bg-white/[0.04]"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        layoutId="sidebar-active"
                        className="absolute inset-0 -z-10 rounded-lg bg-gradient-to-r from-violet-500/20 to-cyan-500/20 ring-1 ring-white/10"
                        transition={{
                          type: "spring",
                          stiffness: 350,
                          damping: 32,
                        }}
                      />
                    )}
                    {isActive && (
                      <span className="absolute -left-3 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r bg-aurora-accent" />
                    )}
                    <item.icon
                      size={16}
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
        Barclays XLS · DRIP-aware
      </div>
    </aside>
  );
}
