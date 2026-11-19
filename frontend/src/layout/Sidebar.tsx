import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  CircleHelp,
  Database,
  LayoutDashboard,
  Scale,
  Wallet,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { scopedNavigationUrl } from "../routing";

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
  { to: "/help", label: "Help", icon: CircleHelp },
];

export function Sidebar() {
  const location = useLocation();
  return (
    <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-white/[0.06] bg-[#0b0e14]/95 backdrop-blur-xl lg:flex">
      <div className="flex items-center gap-3 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-sky-400/25 bg-sky-500/15">
          <BarChart3 size={16} className="text-sky-300" />
        </div>
        <div>
          <p className="text-sm font-semibold tracking-tight text-white">Portfolio</p>
          <p className="text-[11px] text-slate-500">Personal analytics</p>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 px-2.5 py-2">
        <ul className="space-y-0.5">
          {PRIMARY_NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={scopedNavigationUrl(item.to, location.search)}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                    isActive
                      ? "text-white"
                      : "text-slate-400 hover:bg-white/[0.035] hover:text-slate-100"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive ? (
                      <motion.span
                        layoutId="sidebar-active"
                        className="absolute inset-0 -z-10 rounded-lg bg-white/[0.07] ring-1 ring-white/[0.08]"
                        transition={{ type: "spring", stiffness: 400, damping: 34 }}
                      />
                    ) : null}
                    {isActive ? (
                      <span
                        aria-hidden="true"
                        className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-sky-400"
                      />
                    ) : null}
                    <item.icon
                      size={16}
                      className={
                        isActive
                          ? "text-sky-400"
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

      <div className="border-t border-white/[0.05] px-4 py-3.5 text-[11px] text-slate-600">
        Private · Local data
      </div>
    </aside>
  );
}
