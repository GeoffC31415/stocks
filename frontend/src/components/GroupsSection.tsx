import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Layers, Pencil, Plus, Save, Trash2, X } from "lucide-react";
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
  const [newGroupTarget, setNewGroupTarget] = useState("");

  const createGroupMutation = useMutation({
    mutationFn: () =>
      api.createGroup(
        newGroupName.trim(),
        null,
        newGroupTarget.trim() ? Number(newGroupTarget) : null,
      ),
    onSuccess: () => {
      setNewGroupName("");
      setNewGroupTarget("");
      queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });

  const updateGroupMembers = useMutation({
    mutationFn: ({ group, members }: { group: Group; members: number[] }) =>
      api.replaceGroupMembers(group.id, members),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const renameGroupMutation = useMutation({
    mutationFn: ({ group, name }: { group: Group; name: string }) =>
      api.updateGroup(group.id, { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["groups"] }),
  });

  const updateGroupTargetMutation = useMutation({
    mutationFn: ({ group, target }: { group: Group; target: number | null }) =>
      api.updateGroup(group.id, { target_allocation_pct: target }),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  const deleteGroupMutation = useMutation({
    mutationFn: ({ group }: { group: Group }) => api.deleteGroup(group.id),
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
          <input
            value={newGroupTarget}
            onChange={(e) => setNewGroupTarget(e.target.value)}
            placeholder="Target %"
            type="number"
            min="0"
            max="100"
            step="0.1"
            className="w-28 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-aurora-cyan/60 focus:outline-none"
          />
          <button
            type="button"
            className="btn-primary flex items-center gap-1.5 px-3 text-xs"
            onClick={() => createGroupMutation.mutate()}
            disabled={
              !newGroupName.trim() ||
              createGroupMutation.isPending ||
              Number(newGroupTarget || 0) < 0 ||
              Number(newGroupTarget || 0) > 100
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
              onRename={(name) =>
                renameGroupMutation.mutateAsync({ group, name })
              }
              onTargetSave={(target) =>
                updateGroupTargetMutation.mutateAsync({ group, target })
              }
              onDelete={() => deleteGroupMutation.mutateAsync({ group })}
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
  onRename,
  onTargetSave,
  onDelete,
}: {
  group: Group;
  instruments: Instrument[];
  current: Instrument[];
  onSave: (members: number[]) => void;
  onRename: (name: string) => Promise<unknown>;
  onTargetSave: (target: number | null) => Promise<unknown>;
  onDelete: () => Promise<unknown>;
}) {
  const [selected, setSelected] = useState<number[]>(
    current.map((i) => i.id),
  );

  const [isEditingName, setIsEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(group.name);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [targetDraft, setTargetDraft] = useState(
    group.target_allocation_pct?.toString() ?? "",
  );
  const [isSavingTarget, setIsSavingTarget] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isEditingName) setNameDraft(group.name);
  }, [group.name, isEditingName]);

  useEffect(() => {
    setTargetDraft(group.target_allocation_pct?.toString() ?? "");
  }, [group.target_allocation_pct]);

  useEffect(() => {
    if (isEditingName) inputRef.current?.select();
  }, [isEditingName]);

  const dirty =
    selected.length !== current.length ||
    selected.some((id) => !current.find((i) => i.id === id));

  const startEdit = () => {
    setNameDraft(group.name);
    setRenameError(null);
    setIsEditingName(true);
  };

  const cancelEdit = () => {
    setIsEditingName(false);
    setRenameError(null);
    setNameDraft(group.name);
  };

  const startDeleteConfirm = () => {
    setDeleteError(null);
    setIsConfirmingDelete(true);
  };

  const cancelDeleteConfirm = () => {
    setIsConfirmingDelete(false);
    setDeleteError(null);
  };

  const confirmDelete = async () => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await onDelete();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed.");
      setIsDeleting(false);
    }
  };

  const submitRename = async () => {
    const trimmed = nameDraft.trim();
    if (!trimmed) {
      setRenameError("Name cannot be empty.");
      return;
    }
    if (trimmed === group.name) {
      cancelEdit();
      return;
    }
    setIsRenaming(true);
    setRenameError(null);
    try {
      await onRename(trimmed);
      setIsEditingName(false);
    } catch (err) {
      setRenameError(err instanceof Error ? err.message : "Rename failed.");
    } finally {
      setIsRenaming(false);
    }
  };

  const submitTarget = async () => {
    const target = targetDraft.trim() ? Number(targetDraft) : null;
    if (target != null && (Number.isNaN(target) || target < 0 || target > 100)) return;
    setIsSavingTarget(true);
    try {
      await onTargetSave(target);
    } finally {
      setIsSavingTarget(false);
    }
  };

  return (
    <div className="glass rounded-2xl p-5">
      {isConfirmingDelete ? (
        <div className="mb-3 rounded-xl border border-rose-500/30 bg-rose-500/[0.08] p-3">
          <p className="text-sm font-semibold text-rose-200">
            Delete &ldquo;{group.name}&rdquo;?
          </p>
          <p className="mt-0.5 text-[11px] text-rose-300/80">
            This removes the group and its {current.length} membership
            {current.length === 1 ? "" : "s"}. Instruments themselves are kept.
          </p>
          {deleteError ? (
            <p className="mt-1 text-[11px] text-rose-400">{deleteError}</p>
          ) : null}
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={cancelDeleteConfirm}
              disabled={isDeleting}
              className="rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 py-1 text-xs text-slate-300 transition-colors hover:text-white disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={confirmDelete}
              disabled={isDeleting}
              className="flex items-center gap-1 rounded-md bg-rose-500/90 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-rose-500 disabled:opacity-50"
            >
              <Trash2 size={12} />
              {isDeleting ? "Deleting…" : "Delete group"}
            </button>
          </div>
        </div>
      ) : null}
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-aurora-accent-soft">
          <Layers size={14} className="text-aurora-cyan" />
        </div>
        <div className="min-w-0 flex-1">
          {isEditingName ? (
            <div className="flex items-center gap-1.5">
              <input
                ref={inputRef}
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitRename();
                  if (e.key === "Escape") cancelEdit();
                }}
                disabled={isRenaming}
                className="min-w-0 flex-1 rounded-md border border-white/[0.08] bg-white/[0.03] px-2 py-1 text-sm font-semibold text-white focus:border-aurora-cyan/60 focus:outline-none"
              />
              <button
                type="button"
                onClick={submitRename}
                disabled={isRenaming || !nameDraft.trim()}
                aria-label="Save name"
                className="flex h-7 w-7 items-center justify-center rounded-md bg-aurora-accent text-white shadow-glow-accent transition-opacity disabled:opacity-50"
              >
                <Check size={12} />
              </button>
              <button
                type="button"
                onClick={cancelEdit}
                disabled={isRenaming}
                aria-label="Cancel rename"
                className="flex h-7 w-7 items-center justify-center rounded-md border border-white/[0.06] bg-white/[0.02] text-slate-400 transition-colors hover:text-slate-200"
              >
                <X size={12} />
              </button>
            </div>
          ) : (
            <div className="group flex items-center gap-1.5">
              <h3 className="truncate text-sm font-semibold text-white">
                {group.name}
              </h3>
              <button
                type="button"
                onClick={startEdit}
                aria-label={`Rename ${group.name}`}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-500 opacity-0 transition-all hover:bg-white/[0.04] hover:text-slate-200 focus:opacity-100 group-hover:opacity-100"
              >
                <Pencil size={11} />
              </button>
              <button
                type="button"
                onClick={startDeleteConfirm}
                aria-label={`Delete ${group.name}`}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-slate-500 opacity-0 transition-all hover:bg-rose-500/[0.12] hover:text-rose-300 focus:opacity-100 group-hover:opacity-100"
              >
                <Trash2 size={11} />
              </button>
            </div>
          )}
          <p className="tabular text-[11px] text-slate-500">
            {selected.length} members ·{" "}
            {group.total_value_gbp != null
              ? toGbp(group.total_value_gbp)
              : "—"}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input
              value={targetDraft}
              onChange={(e) => setTargetDraft(e.target.value)}
              onBlur={submitTarget}
              type="number"
              min="0"
              max="100"
              step="0.1"
              placeholder="Target %"
              disabled={isSavingTarget}
              className="w-24 rounded-md border border-white/[0.06] bg-white/[0.02] px-2 py-1 text-[11px] text-slate-300 placeholder:text-slate-600 focus:border-aurora-cyan/60 focus:outline-none"
            />
            <span className="text-[11px] text-slate-600">target allocation</span>
          </div>
          {renameError ? (
            <p className="mt-1 text-[11px] text-rose-400">{renameError}</p>
          ) : null}
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
          .sort((a, b) =>
            `${a.identifier} ${a.account_name}`.localeCompare(
              `${b.identifier} ${b.account_name}`,
            ),
          )
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
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-slate-300">{i.identifier}</span>
                    <span className="shrink-0 rounded-full border border-white/[0.06] bg-white/[0.03] px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
                      {i.account_name}
                    </span>
                  </span>
                  <span className="block truncate text-[11px] text-slate-600">
                    {i.security_name}
                  </span>
                </span>
              </label>
            );
          })}
      </div>
    </div>
  );
}
