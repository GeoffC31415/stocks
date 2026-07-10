import type { ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  CircleHelp,
  Database,
  Filter,
  Info,
  RefreshCw,
  Scale,
  ShieldCheck,
  Tags,
  Wallet,
} from "lucide-react";
import { Link } from "react-router-dom";

const linkClass =
  "inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 text-xs font-medium text-slate-300 transition-colors hover:bg-white/[0.06] hover:text-white";

export function Help() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-8">
      <header className="glass relative overflow-hidden rounded-2xl p-6 sm:p-8">
        <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-violet-500/10 blur-3xl" />
        <div className="relative flex items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-aurora-accent shadow-glow-accent">
            <CircleHelp size={21} className="text-white" />
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-aurora-cyan">
              Reference
            </p>
            <h1 className="mt-1 text-2xl font-semibold text-white sm:text-3xl">Help & site guide</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              What each page does, how the figures are calculated, and a practical routine for keeping
              the portfolio current. The site combines imported snapshots with order history, so not
              every figure uses the same source or period.
            </p>
          </div>
        </div>
        <nav aria-label="Help sections" className="relative mt-6 flex flex-wrap gap-2 border-t border-white/[0.06] pt-4">
          {[
            ["Routine", "routine-heading"],
            ["Controls", "controls-heading"],
            ["Pages", "pages-heading"],
            ["Concepts", "concepts-heading"],
            ["Common questions", "questions-heading"],
          ].map(([label, target]) => (
            <a
              key={target}
              href={`#${target}`}
              className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/[0.07] hover:text-white"
            >
              {label}
            </a>
          ))}
        </nav>
      </header>

      <section aria-labelledby="routine-heading">
        <SectionHeading
          icon={<RefreshCw size={17} />}
          title="A good routine"
          id="routine-heading"
          description="Use this sequence whenever you have new portfolio or order files."
        />
        <ol className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <RoutineStep
            number="1"
            title="Import new files"
            text="Open Data → Import & refresh. Preview the file first, then import it when the date and account look right."
            to="/data?tab=import"
          />
          <RoutineStep
            number="2"
            title="Check matching"
            text="Open Data → Matching. If the health panel is green, no action is needed. Review only the exceptions."
            to="/data?tab=matching"
          />
          <RoutineStep
            number="3"
            title="Complete metadata"
            text="Use Data → Classifications for any new holding. This powers the allocation views."
            to="/data?tab=classifications"
          />
          <RoutineStep
            number="4"
            title="Review the result"
            text="Return to Dashboard for changes and attribution, then use Portfolio for deeper analysis."
            to="/"
          />
        </ol>
      </section>

      <section aria-labelledby="controls-heading" className="glass rounded-2xl p-5 sm:p-6">
        <SectionHeading
          icon={<Filter size={17} />}
          title="Controls used across the site"
          id="controls-heading"
        />
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <GuidePoint
            title="Account selector"
            text="The All, HL, and ISA buttons in the top bar change the scope of most analytics. If two pages look different, first check that the same account is selected."
          />
          <GuidePoint
            title="Last snapshot"
            text="This is the valuation date of the most recent imported holdings file—not necessarily today's market date."
          />
          <GuidePoint
            title="DRIP threshold"
            text="Small buys below this amount are treated as dividend reinvestments. Changing it recalculates DRIP-based views across the recorded history."
          />
          <GuidePoint
            title="Refresh data"
            text="Reloads application data and quote-backed calculations. It does not import a new broker file by itself."
          />
        </div>
      </section>

      <section aria-labelledby="pages-heading">
        <SectionHeading
          icon={<BookOpen size={17} />}
          title="Page-by-page guide"
          id="pages-heading"
          description="Each main destination has one job; tabs provide the detailed views."
        />
        <div className="mt-4 space-y-4">
          <PageGuide
            icon={<BarChart3 size={18} />}
            title="Dashboard"
            summary="The quickest answer to “where am I now and what changed?”"
            to="/"
            linkLabel="Open Dashboard"
            items={[
              ["Portfolio value", "The latest imported snapshot value for the selected account scope."],
              ["What changed", "Opening to closing snapshot value, observed flows, DRIP proxy, and residual estimated market movement."],
              ["Estimated money-weighted return", "A cumulative Modified Dietz estimate over the displayed dates; it is not annualised unless explicitly labelled."],
              ["P&L and book cost", "Unrealised gain and recorded cost for invested holdings. Cash is excluded from the P&L card."],
              ["Snapshot history", "Actual values from imported snapshots. The optional historical estimate is order-derived and is a different series."],
              ["Performance leaders", "Holding returns against recorded book cost—not short-term price movers."],
            ]}
          />

          <PageGuide
            icon={<Wallet size={18} />}
            title="Portfolio"
            summary="Explore what you own, how it has performed, and where it is concentrated."
            to="/portfolio"
            linkLabel="Open Portfolio"
            items={[
              ["Holdings", "Current positions from the latest snapshot. Select a holding to inspect its details and history."],
              ["Returns", "Order-derived cost, sales, DRIP, current value, P&L, and return estimates by position."],
              ["Allocation", "Largest holdings, concentration, and exposure by asset class, sector/theme, or region."],
              ["Income", "A DRIP purchase proxy by period and holding. It is not a complete dividend ledger."],
              ["Groups", "User-defined collections such as US core index or UK equities, including combined values and performance."],
            ]}
          />

          <PageGuide
            icon={<Activity size={18} />}
            title="Activity"
            summary="Inspect the events and source records behind the portfolio."
            to="/activity"
            linkLabel="Open Activity"
            items={[
              ["Orders", "Search and filter imported buys, sells, and DRIP-classified purchases by name, type, and date."],
              ["Snapshot changes", "Compare two imported snapshots to see new, closed, and changed positions."],
              ["Import history", "Review which files were imported, when they were processed, and their status."],
            ]}
          />

          <PageGuide
            icon={<Scale size={18} />}
            title="Tax"
            summary="Review estimated UK capital gains by tax year."
            to="/tax"
            linkLabel="Open Tax"
            items={[
              ["Tax-year selector", "Choose a UK tax year; the latest available year is selected initially."],
              ["Realised gains", "Calculated from matched disposals and recorded cost basis."],
              ["Annual exemption", "Applied independently for each supported tax year, never guessed for an unknown year."],
              ["Important", "This is an analytical estimate, not tax advice or a substitute for broker and HMRC records."],
            ]}
          />

          <PageGuide
            icon={<Database size={18} />}
            title="Data"
            summary="Maintain the source data and resolve exceptions."
            to="/data"
            linkLabel="Open Data"
            items={[
              ["Import & refresh", "Preview and import holdings or order files; refresh quotes where configured."],
              ["Classifications", "Set ticker, asset class, sector/theme, and region for open holdings."],
              ["Matching", "Connect imported order names to instruments. The simple health panel hides advanced tools until needed."],
              ["Use care", "Imports and metadata edits change the local database. Preview files and keep backups."],
            ]}
          />
        </div>
      </section>

      <section aria-labelledby="concepts-heading">
        <SectionHeading
          icon={<Info size={17} />}
          title="Important concepts"
          id="concepts-heading"
          description="These distinctions explain most apparently conflicting figures."
        />
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <Concept
            title="Snapshot"
            text="A dated broker valuation. Snapshot totals are the strongest source for what the portfolio was worth on that date."
          />
          <Concept
            title="Book cost"
            text="The cost recorded in the latest holdings snapshot. It can differ from net cash deployed from order history."
          />
          <Concept
            title="Modified Dietz"
            text="An estimated money-weighted return that adjusts for the timing of external flows between snapshot boundaries."
          />
          <Concept
            title="External flows"
            text="Non-DRIP buys are treated as contributions. Imported sales are treated as withdrawals because retained cash cannot be distinguished from money leaving the account."
          />
          <Concept
            title="DRIP proxy"
            text="Buy orders under the selected threshold. It estimates reinvested income but omits declared and cash dividends."
          />
          <Concept
            title="Estimated market movement"
            text="The residual snapshot change after observed external flows and the DRIP proxy. It is attribution, not a direct market-price feed."
          />
          <Concept
            title="Concentration index"
            text="HHI squares position weights. Lower values indicate a more evenly spread portfolio; it does not measure investment quality."
          />
          <Concept
            title="Classifications"
            text="Allocation uses product-level classifications. Broad ETFs are not decomposed into every underlying company, country, or sector."
          />
          <Concept
            title="Separate account holdings"
            text="The same security held in two accounts remains two positions. Some views therefore show the ticker twice rather than aggregating it."
          />
        </div>
      </section>

      <section aria-labelledby="questions-heading">
        <SectionHeading
          icon={<CircleHelp size={17} />}
          title="Common questions"
          id="questions-heading"
        />
        <div className="mt-4 space-y-2">
          <Question title="Why do two totals not match exactly?">
            Check the account selector, date, and source. Snapshot value, order-derived cash deployed, book cost,
            and P&L are related but not interchangeable. Whole-pound display rounding can also create a £1 visual difference.
          </Question>
          <Question title="Why does the return period start later than my order history?">
            A portfolio return needs compatible opening and closing snapshots. For All accounts, the period starts only
            once every included account has snapshot coverage.
          </Question>
          <Question title="Why is a dividend-paying holding absent from Income?">
            Income uses DRIP-classified purchases rather than a dividend ledger. Cash dividends and declarations are not
            present in the source files.
          </Question>
          <Question title="Why does an ETF say Diversified or show a theme?">
            The classification describes the investment product at a high level. It is not constituent look-through,
            so a broad index fund is multi-sector and a thematic fund may use its theme.
          </Question>
          <Question title="What should I do when Matching reports an exception?">
            Open the advanced tools, review the suggested instrument, then resolve only the unmatched or review item.
            Leave healthy matches alone.
          </Question>
        </div>
      </section>

      <section className="flex items-start gap-3 rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.04] p-5">
        <ShieldCheck size={19} className="mt-0.5 shrink-0 text-emerald-300" />
        <div>
          <h2 className="text-sm font-semibold text-white">Private local data</h2>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            The application is designed for a single private portfolio and stores its working data locally.
            Back up the database before major imports or bulk edits. Git deliberately ignores the live database.
          </p>
        </div>
      </section>
    </div>
  );
}

function SectionHeading({
  icon,
  title,
  id,
  description,
}: {
  icon: ReactNode;
  title: string;
  id: string;
  description?: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 text-aurora-cyan">
        {icon}
        <h2 id={id} className="text-lg font-semibold text-white">
          {title}
        </h2>
      </div>
      {description ? <p className="mt-1 text-sm text-slate-400">{description}</p> : null}
    </div>
  );
}

function RoutineStep({
  number,
  title,
  text,
  to,
}: {
  number: string;
  title: string;
  text: string;
  to: string;
}) {
  return (
    <li className="glass rounded-2xl p-4">
      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-400/10 text-xs font-semibold text-violet-200">
        {number}
      </div>
      <h3 className="mt-3 text-sm font-semibold text-white">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-slate-400">{text}</p>
      <Link to={to} className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-aurora-cyan hover:text-cyan-200">
        Open {title} <ArrowRight size={12} />
      </Link>
    </li>
  );
}

function GuidePoint({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-xl border border-white/[0.05] bg-white/[0.02] p-4">
      <h3 className="text-sm font-medium text-slate-200">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-slate-400">{text}</p>
    </div>
  );
}

function PageGuide({
  icon,
  title,
  summary,
  to,
  linkLabel,
  items,
}: {
  icon: ReactNode;
  title: string;
  summary: string;
  to: string;
  linkLabel: string;
  items: Array<[string, string]>;
}) {
  return (
    <article className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.04] text-aurora-cyan">
            {icon}
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">{title}</h3>
            <p className="mt-1 text-xs text-slate-400">{summary}</p>
          </div>
        </div>
        <Link to={to} className={linkClass} aria-label={linkLabel}>
          Open <ArrowRight size={13} />
        </Link>
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-3 md:grid-cols-2">
        {items.map(([term, description]) => (
          <div key={term} className="border-l border-white/[0.08] pl-3">
            <dt className="text-xs font-medium text-slate-200">{term}</dt>
            <dd className="mt-0.5 text-xs leading-5 text-slate-400">{description}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function Concept({ title, text }: { title: string; text: string }) {
  return (
    <article className="glass rounded-xl p-4">
      <h3 className="text-sm font-medium text-slate-200">{title}</h3>
      <p className="mt-1 text-xs leading-5 text-slate-400">{text}</p>
    </article>
  );
}

function Question({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group glass rounded-xl px-4 py-3 open:bg-white/[0.025]">
      <summary className="cursor-pointer list-none text-sm font-medium text-slate-200 marker:hidden">
        <span className="flex items-center justify-between gap-3">
          {title}
          <span className="text-lg font-light text-slate-600 transition-transform group-open:rotate-45">+</span>
        </span>
      </summary>
      <p className="mt-2 max-w-4xl text-xs leading-5 text-slate-400">{children}</p>
    </details>
  );
}
