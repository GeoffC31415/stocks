import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { TargetDriftPanel } from "../components/TargetDriftPanel";
import { GroupsSection } from "../components/GroupsSection";

export function Groups() {
  const instrumentsQ = useQuery({
    queryKey: ["instruments"],
    queryFn: () => api.getInstruments(),
  });
  const groupsQ = useQuery({ queryKey: ["groups"], queryFn: api.getGroups });

  const instruments = instrumentsQ.data ?? [];
  const groups = groupsQ.data ?? [];

  const byGroup = useMemo(() => {
    const grouped: Record<number, typeof instruments> = {};
    for (const group of groups) {
      grouped[group.id] = instruments.filter((i) =>
        i.group_ids.includes(group.id),
      );
    }
    return grouped;
  }, [groups, instruments]);

  if (instrumentsQ.isError || groupsQ.isError) return <div role="alert"><p>Unable to load groups. The editor is withheld to avoid editing incomplete memberships.</p><button type="button" onClick={()=>{void instrumentsQ.refetch();void groupsQ.refetch();}}>Retry groups</button></div>;
  if (instrumentsQ.isPending || groupsQ.isPending) return <p role="status" className="min-h-64">Loading groups and memberships…</p>;
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

      <TargetDriftPanel />
      <p className="text-sm text-slate-300">Group editor below includes all accounts; target analysis above follows the selected account. Editing memberships changes descriptive tags only; no portfolio orders are created.</p>
      {groups.length===0 && <p role="status">No groups yet. Create a group below.</p>}
      <GroupsSection
        groups={groups}
        instruments={instruments}
        byGroup={byGroup}
      />
    </div>
  );
}
