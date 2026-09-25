import { useEffect, useState } from "react";
import { Save, UserPlus } from "lucide-react";
import { listApprovalGroups, updateApprovalGroup, listUsers, grantCeoDelegate, type ApprovalGroup, type UserRow } from "../../../api/client";
import { Button } from "../../../ui-v2/primitives/button";
import { reviewError } from "../sow-workspace/SubmitApprovalDialog";

export function ApprovalGroups() {
  const [groups, setGroups] = useState<ApprovalGroup[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [canEdit, setCanEdit] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    try {
      const response = await listApprovalGroups();
      setGroups(response.items); setCanEdit(response.can_edit);
      if (response.can_edit) {
        const all: UserRow[] = [];
        let page = 1;
        for (;;) {
          const result = await listUsers({ page, size: 200 });
          all.push(...result.items);
          if (all.length >= result.total || !result.items.length) break;
          page++;
        }
        setUsers(all);
      }
    } catch (e) { setError(reviewError(e)); }
  }
  useEffect(() => { void load(); }, []);
  return <div className="space-y-5">
    {error && <p role="alert" className="text-danger">{error}</p>}
    {!groups.length && !error && <p>Loading groups...</p>}
    {groups.map(group => <GroupEditor key={group.function} group={group} users={users} canEdit={canEdit} reload={load} />)}
  </div>;
}

function GroupEditor({ group, users, canEdit, reload }: { group: ApprovalGroup; users: UserRow[]; canEdit: boolean; reload: () => Promise<void> }) {
  const [members, setMembers] = useState(group.members.map(m => m.id));
  const [backups, setBackups] = useState(group.backup_ids);
  const [defaultId, setDefaultId] = useState(group.default_approver_id ?? "");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [delegate, setDelegate] = useState("");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const executive = group.function === "executive";
  const candidates = users.length ? users : group.members;
  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      await updateApprovalGroup(group.function, { member_ids: members, backup_ids: backups, default_approver_id: defaultId || null });
      setMessage("Saved"); await reload();
    } catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  async function grant() {
    setBusy(true); setError("");
    try { await grantCeoDelegate({ delegate_id: delegate, effective_from: from, expiry: until }); await reload(); setMessage("Delegation recorded"); }
    catch (e) { setError(reviewError(e)); } finally { setBusy(false); }
  }
  return <section aria-label={`${group.label} group`} className="border-b border-divider pb-5">
    <div className="flex flex-wrap items-center justify-between gap-3 mb-3"><h2 className="text-section">{group.label}</h2><span className="text-secondary text-text-secondary">System group</span></div>
    {error && <p role="alert" className="text-danger mb-2">{error}</p>}
    {message && <p role="status" className="text-success mb-2">{message}</p>}
    {(executive ? !group.members.length : !members.length) && <p className="text-warning mb-3" role="status">Empty group. Reviews cannot route. Owner: SystemAdmin.</p>}
    {executive ? <>
      <ul className="space-y-2 text-body">{group.members.map(m => <li key={m.id}>{m.name}{m.id === group.default_approver_id ? " · CEO" : " · Active delegate"}</li>)}</ul>
      {group.delegations.map((d, i) => <p key={i} className="text-secondary text-text-secondary mt-2">{candidates.find(u => u.id === d.delegate_id)?.name ?? "Recorded delegate"} · {d.effective_from} to {d.expiry}</p>)}
      {canEdit && <div className="flex flex-wrap gap-2 mt-3 items-end">
        <label className="text-secondary">Delegate<select aria-label="Executive delegate" className="block border border-divider bg-surface rounded-control p-2" value={delegate} onChange={e => setDelegate(e.target.value)}><option value="">Select a user</option>{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
        <label className="text-secondary">Effective from<input type="date" className="block border border-divider rounded-control p-2" value={from} onChange={e => setFrom(e.target.value)} /></label>
        <label className="text-secondary">Expiry<input type="date" min={from} className="block border border-divider rounded-control p-2" value={until} onChange={e => setUntil(e.target.value)} /></label>
        <Button variant="secondary" disabled={busy || !delegate || !from || !until} onClick={grant}><UserPlus className="h-4 w-4 mr-2" />Record delegation</Button>
      </div>}
    </> : <>
      <input aria-label={`Search ${group.label} members`} type="search" className="border border-divider rounded-control bg-surface p-2 mb-3 w-full max-w-sm" placeholder="Search people" value={search} onChange={e => setSearch(e.target.value)} />
      <div className="max-h-52 overflow-auto border-y border-divider divide-y divide-divider">
        {candidates.filter(u => `${u.name} ${"email" in u ? u.email : ""}`.toLowerCase().includes(search.toLowerCase())).map(u => <div key={u.id} className="flex flex-wrap gap-3 py-2 text-body items-center">
          <label className="flex-1 min-w-40 flex gap-2 items-center"><input type="checkbox" disabled={!canEdit || busy} checked={members.includes(u.id)} onChange={e => {
            setMembers(e.target.checked ? [...members, u.id] : members.filter(id => id !== u.id));
            if (!e.target.checked) { setBackups(backups.filter(id => id !== u.id)); if (defaultId === u.id) setDefaultId(""); }
          }} />{u.name}</label>
          {members.includes(u.id) && <label className="flex items-center gap-2 text-secondary"><input type="checkbox" aria-label={`${group.label} backup ${u.name}`} disabled={!canEdit || busy} checked={backups.includes(u.id)} onChange={e => setBackups(e.target.checked ? [...backups, u.id] : backups.filter(id => id !== u.id))} />Backup</label>}
        </div>)}
      </div>
      <div className="flex flex-wrap gap-3 mt-3 items-end"><label className="text-secondary">Default approver<select aria-label={`${group.label} default approver`} disabled={!canEdit || busy} className="block mt-1 border border-divider rounded-control bg-surface p-2" value={defaultId} onChange={e => setDefaultId(e.target.value)}><option value="">{members.length ? "Select default" : "No members"}</option>{candidates.filter(u => members.includes(u.id)).map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
        {canEdit && <Button variant="secondary" onClick={save} disabled={busy || (!!members.length && !defaultId)}><Save className="h-4 w-4 mr-2" />Save {group.label}</Button>}
      </div>
    </>}
  </section>;
}
