import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Layers, Plus, Save } from "lucide-react";
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
    <div className="space-y-5">
      <div className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2">
          <Plus size={14} className="text-aurora-cyan" />
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-300">
            New group
          </h3>
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            placeholder="Group name (e.g. Tech, ETFs, EM)"
            className="flex-1 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-aurora-cyan/60 focus:outline-none"
          />
          <button
            type="button"
            className="btn-primary flex items-center gap-1.5 px-3 text-xs"
            onClick={() => createGroupMutation.mutate()}
            disabled={
              !newGroupName.trim() || createGroupMutation.isPending
            }
          >
            <Plus size={14} />
            Add group
          </button>
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="glass rounded-2xl p-8 text-center">
          <Layers size={20} className="mx-auto text-slate-600" />
          <p className="mt-2 text-sm text-slate-400">No groups yet</p>
          <p className="mt-1 text-xs text-slate-500">
            Organise instruments into custom buckets above.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
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
        </div>
      )}
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

  const dirty =
    selected.length !== current.length ||
    selected.some((id) => !current.find((i) => i.id === id));

  return (
    <div className="glass rounded-2xl p-5">
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-aurora-accent-soft">
          <Layers size={14} className="text-aurora-cyan" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-white">
            {group.name}
          </h3>
          <p className="tabular text-[11px] text-slate-500">
            {selected.length} members ·{" "}
            {group.total_value_gbp != null
              ? toGbp(group.total_value_gbp)
              : "—"}
          </p>
        </div>
        <button
          type="button"
          className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
            dirty
              ? "bg-aurora-accent text-white shadow-glow-accent"
              : "border border-white/[0.06] bg-white/[0.02] text-slate-500"
          }`}
          onClick={() => onSave(selected)}
          disabled={!dirty}
        >
          <Save size={12} />
          Save
        </button>
      </div>

      <div className="max-h-44 overflow-auto rounded-xl border border-white/[0.04] bg-white/[0.02] p-2">
        {instruments
          .filter((i) => !i.is_cash)
          .map((i) => {
            const isOn = selected.includes(i.id);
            return (
              <label
                key={i.id}
                className={`flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ${
                  isOn ? "bg-white/[0.04]" : "hover:bg-white/[0.03]"
                }`}
              >
                <input
                  type="checkbox"
                  checked={isOn}
                  onChange={(e) =>
                    setSelected((prev) =>
                      e.target.checked
                        ? [...prev, i.id]
                        : prev.filter((id) => id !== i.id),
                    )
                  }
                  className="accent-aurora-cyan"
                />
                <span className="truncate text-slate-300">{i.identifier}</span>
                <span className="ml-auto truncate text-[11px] text-slate-600">
                  {i.security_name}
                </span>
              </label>
            );
          })}
      </div>
    </div>
  );
}
