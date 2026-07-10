import { NavLink } from "react-router-dom";
import { PRIMARY_NAV } from "./Sidebar";

export function MobileNav() {
  return (
    <nav
      aria-label="Mobile"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-white/[0.08] bg-aurora-base/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl lg:hidden"
    >
      <ul className="grid grid-cols-6 gap-1">
        {PRIMARY_NAV.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex min-h-12 flex-col items-center justify-center gap-1 rounded-lg px-1 text-[10px] font-medium transition-colors ${
                  isActive
                    ? "bg-white/[0.06] text-white"
                    : "text-slate-500 hover:bg-white/[0.03] hover:text-slate-200"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    aria-hidden="true"
                    size={18}
                    className={isActive ? "text-aurora-cyan" : undefined}
                  />
                  <span>{item.label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
