import { useId } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";

type Tone = "accent" | "pos" | "neg" | "amber";

const TONE: Record<Tone, { stroke: string; fill: string }> = {
  accent: { stroke: "#38bdf8", fill: "#38bdf8" },
  pos: { stroke: "#34d399", fill: "#34d399" },
  neg: { stroke: "#fb7185", fill: "#fb7185" },
  amber: { stroke: "#fbbf24", fill: "#fbbf24" },
};

export function Sparkline({
  data,
  dataKey = "value",
  tone = "accent",
  height = 44,
}: {
  data: Array<Record<string, number | string | null>>;
  dataKey?: string;
  tone?: Tone;
  height?: number;
}) {
  const gradId = useId();
  const colors = TONE[tone];

  if (!data || data.length === 0) {
    return <div style={{ height }} className="opacity-30" />;
  }

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.fill} stopOpacity={0.14} />
              <stop offset="100%" stopColor={colors.fill} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area
            type="linear"
            dataKey={dataKey}
            stroke={colors.stroke}
            strokeWidth={1.35}
            fill={`url(#${gradId})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
