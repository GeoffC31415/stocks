import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { GroupsSection } from "../components/GroupsSection";

export function Groups() {
  const instrumentsQ = useQuery({
    queryKey: ["instruments"],
    queryFn: api.getInstruments,
  });
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: api.getGroups });

  const instruments = useMemo(() => instrumentsQ.data ?? [], [instrumentsQ.data]);
  const groups = useMemo(() => groupsQ.data ?? [], [groupsQ.data]);

  const byGroup = useMemo(() => {
    const grouped: Record<number, typeof instruments> = {};
    for (const group of groups) {
      grouped[group.id] = instruments.filter((i) =>
        i.group_ids.includes(group.id),
      );
    }
    return grouped;
  }, [groups, instruments]);

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h1
            className="text-2xl font-semibold text-white"
            style={{ letterSpacing: "-0.02em" }}
          >
            Groups
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Organise instruments into custom buckets.
          </p>
        </div>
        <span className="chip chip-muted tabular">
          {groups.length} groups
        </span>
      </div>

      <GroupsSection
        groups={groups}
        instruments={instruments}
        byGroup={byGroup}
      />
    </div>
  );
}
