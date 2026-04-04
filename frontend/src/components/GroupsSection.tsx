import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, type Group, type Instrument } from "../lib/api";
import { toGbp } from "../lib/formatters";

export function GroupsSection({
  groups,
  instruments,
  byGroup,
}: {
  groups: Group[];
  instruments: Instrument[];
  byGroup: Record<number, Instrument[]>;
}) {
  const queryClient = useQueryClient();
  const [newGroupName, setNewGroupName] = useState("");

  const createGroupMutation = useMutation({
    mutationFn: () => api.createGroup(newGroupName.trim(), null),
    onSuccess: () => {
      setNewGroupName("");
      queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });

  const updateGroupMembers = useMutation({
    mutationFn: ({ group, members }: { group: Group; members: number[] }) =>
      api.replaceGroupMembers(group.id, members),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  return (
    <div>
      <div className="mb-4 flex gap-2">
        <input
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          placeholder="New group name"
          className="flex-1 rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm focus:border-violet-500 focus:outline-none"
        />
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-slate-600"
          onClick={() => createGroupMutation.mutate()}
          disabled={!newGroupName.trim() || createGroupMutation.isPending}
        >
          <Plus size={14} />
          Add group
        </button>
      </div>

      <div className="space-y-3">
        {groups.map((group) => (
          <GroupEditor
            key={group.id}
            group={group}
            instruments={instruments}
            current={byGroup[group.id] ?? []}
            onSave={(members) =>
              updateGroupMembers.mutate({ group, members })
            }
          />
        ))}
        {groups.length === 0 && (
          <p className="py-4 text-center text-sm text-slate-500">
            No groups yet. Create one above.
          </p>
        )}
      </div>
    </div>
  );
}

function GroupEditor({
  group,
  instruments,
  current,
  onSave,
}: {
  group: Group;
  instruments: Instrument[];
  current: Instrument[];
  onSave: (members: number[]) => void;
}) {
  const [selected, setSelected] = useState<number[]>(
    current.map((i) => i.id),
  );

  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-900/30 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">
          {group.name}{" "}
          <span className="text-xs font-normal text-slate-500">
            · {toGbp(group.total_value_gbp)}
          </span>
        </h3>
        <button
          type="button"
          className="rounded-md bg-cyan-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-cyan-500"
          onClick={() => onSave(selected)}
        >
          Save
        </button>
      </div>
      <div className="max-h-36 overflow-auto rounded-lg bg-slate-900/40 p-2">
        {instruments
          .filter((i) => !i.is_cash)
          .map((i) => (
            <label
              key={i.id}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm transition-colors hover:bg-slate-800/40"
            >
              <input
                type="checkbox"
                checked={selected.includes(i.id)}
                onChange={(e) =>
                  setSelected((prev) =>
                    e.target.checked
                      ? [...prev, i.id]
                      : prev.filter((id) => id !== i.id),
                  )
                }
                className="accent-cyan-500"
              />
              <span className="truncate text-slate-300">{i.identifier}</span>
            </label>
          ))}
      </div>
    </div>
  );
}
