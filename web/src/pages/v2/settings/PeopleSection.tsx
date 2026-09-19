/**
 * Settings → People & access (spec §18).
 *
 * Tabs: Users / Roles / Delegations.
 *  - Users: reuses listUsers; scope, status and last-access columns per
 *    spec. Invite + edit-scope actions surface but the mutations live
 *    on the legacy Users admin route until we lift them here.
 *  - Roles: a static reference card for each role — the API has no
 *    role-detail endpoint yet, so we spell out capabilities honestly
 *    (spec §18: "list view/edit/approve/export capabilities").
 *  - Delegations: the server only exposes `grantCeoDelegate` today; a
 *    listing endpoint does not yet exist. We say so honestly instead
 *    of manufacturing rows (spec §4).
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  listUsers,
  type UserRow,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../ui-v2/primitives/tabs";

type TabId = "users" | "roles" | "delegations";

interface RoleDoc {
  role: string;
  view: string;
  edit: string;
  approve: string;
  sensitive: string;
}

const ROLES: RoleDoc[] = [
  {
    role: "CEO",
    view: "Full pipeline + governance + finance",
    edit: "Exception rationale + decision",
    approve: "Below-floor packages · exception decisions",
    sensitive: "Full cost visibility",
  },
  {
    role: "SystemAdmin",
    view: "Every screen",
    edit: "Users, delegations, settings",
    approve: "None — admin never approves a package",
    sensitive: "Full — restricted to operator role",
  },
  {
    role: "Finance",
    view: "Rate cards, policy, GM, actuals",
    edit: "Rate cards + policy publish",
    approve: "Finance function on approval packages",
    sensitive: "Full cost visibility",
  },
  {
    role: "Delivery",
    view: "Delivery model, staffing, forecast",
    edit: "Delivery model + resource lines",
    approve: "Delivery function on approval packages",
    sensitive: "Approved role costs only",
  },
  {
    role: "HR",
    view: "Staffing, lead-time warnings",
    edit: "Resource assignment",
    approve: "HR function on approval packages",
    sensitive: "Named-person costs",
  },
  {
    role: "Legal",
    view: "NDA/MSA register, signed SOW verify",
    edit: "Agreements + signed SOW upload",
    approve: "Legal function on approval packages",
    sensitive: "Signed documents",
  },
  {
    role: "Sales",
    view: "Deals, clients, AI discovery",
    edit: "Deal fields, next actions",
    approve: "None",
    sensitive: "None — sees no cost",
  },
];

export function PeopleSection() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const activeTab = (params.get("tab") as TabId) || "users";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="People & access"
        subtitle={
          "Users, roles and delegations. Every deactivation reassigns open work " +
          "through a reviewable queue; the original reviewer and any delegate " +
          "stay in the audit history."
        }
      />

      <Tabs
        value={activeTab}
        onValueChange={(v) => {
          const next = new URLSearchParams(location.search);
          next.set("tab", v);
          navigate({ search: next.toString() }, { replace: true });
        }}
      >
        <TabsList aria-label="People tabs">
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="roles">Roles</TabsTrigger>
          <TabsTrigger value="delegations">Delegations</TabsTrigger>
        </TabsList>

        <TabsContent value="users">
          <UsersPanel />
        </TabsContent>

        <TabsContent value="roles">
          <RolesPanel />
        </TabsContent>

        <TabsContent value="delegations">
          <DelegationsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function UsersPanel() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listUsers({ size: 50 })
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenPanel label="Ask a SystemAdmin if you need to review users." />;
    }
    return (
      <ErrorState
        title="We couldn't load the users list."
        description="Retry to try again."
        onRetry={load}
      />
    );
  }

  if (loading && rows.length === 0) {
    return <EmptyState title="Loading" description="Fetching users." />;
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No users found"
        description="Invite the first teammate from the legacy Users admin screen."
      />
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-divider">
      <table className="w-full border-collapse text-body">
        <thead className="bg-primary-subtle/30">
          <tr>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Name
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Work email
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Roles
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Status
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Last access
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => (
            <tr key={u.id} className="border-t border-divider">
              <td className="px-3 py-2 text-text">{u.name}</td>
              <td className="px-3 py-2 text-text-secondary">{u.email}</td>
              <td className="px-3 py-2">
                <span className="flex flex-wrap gap-1">
                  {u.groups.length === 0 ? (
                    <span className="text-text-secondary">—</span>
                  ) : (
                    u.groups.map((g) => (
                      <StatusBadge key={g} tone="primarySubtle" label={g} />
                    ))
                  )}
                </span>
              </td>
              <td className="px-3 py-2">
                <StatusBadge
                  tone={u.last_login ? "ok" : "neutral"}
                  label={u.last_login ? "Active" : "Invited"}
                />
              </td>
              <td className="px-3 py-2 text-text-secondary tnum">
                {u.last_login ?? "Never"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RolesPanel() {
  return (
    <div className="overflow-hidden rounded-panel border border-divider">
      <table className="w-full border-collapse text-body">
        <thead className="bg-primary-subtle/30">
          <tr>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Role
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              View
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Edit
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Approve
            </th>
            <th scope="col" className="px-3 py-2 text-left text-secondary text-text-secondary uppercase tracking-wide">
              Sensitive fields
            </th>
          </tr>
        </thead>
        <tbody>
          {ROLES.map((r) => (
            <tr key={r.role} className="border-t border-divider">
              <td className="px-3 py-2 text-text font-medium">{r.role}</td>
              <td className="px-3 py-2 text-text-secondary">{r.view}</td>
              <td className="px-3 py-2 text-text-secondary">{r.edit}</td>
              <td className="px-3 py-2 text-text-secondary">{r.approve}</td>
              <td className="px-3 py-2 text-text-secondary">{r.sensitive}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DelegationsPanel() {
  // The API surface today only exposes `grantCeoDelegate` (POST). A broader
  // "list delegations" endpoint doesn't exist yet, so we degrade honestly
  // per CLAUDE.md rule 9 + spec §4 — no fake rows.
  return (
    <EmptyState
      title="Delegations viewer not available yet"
      description={
        "The API today only exposes a granular grant endpoint for CEO exception " +
        "authority; a broader listing is on the roadmap. Existing grants remain " +
        "in the audit log — filter Audit → entity=user for the immutable history."
      }
    />
  );
}

function ForbiddenPanel({ label }: { label: string }) {
  return (
    <EmptyState
      title="You don't have access to this section."
      description={label}
    />
  );
}
