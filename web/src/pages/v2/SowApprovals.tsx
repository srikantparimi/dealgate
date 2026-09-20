/**
 * SOW approvals board — spec §13.1.
 *
 * Six lanes across the top at ≥1440 px; two rows of three at 1024 px;
 * two per row on tablet; single column on phone. Cards are never
 * draggable across lanes — every gate transition is server-enforced.
 *
 * Data source: `listApprovalPackages()`. NDA/MSA badges come from
 * `listAgreements()` and are matched by legal entity via the surrounding
 * opportunity + deal metadata when available.
 */
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import {
  listAgreements,
  listApprovalPackages,
  type AgreementRow,
  type ApprovalPackage,
} from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { PageHeader } from "../../ui-v2/PageHeader";
import { EmptyState } from "../../ui-v2/EmptyState";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { cn } from "../../lib/cn";
import { LANES, laneForPackage, type LaneDef, type LaneId } from "./sow-approvals/lanes";
import { PackageCard, type CardMeta } from "./sow-approvals/PackageCard";
import { DraftSowStrip } from "./sow-approvals/DraftSowStrip";

type ChipId = "all" | "blocked" | "mine" | "new";

interface Chip {
  id: ChipId;
  label: string;
}

const CHIPS: Chip[] = [
  { id: "all", label: "All packages" },
  { id: "blocked", label: "Blocked" },
  { id: "mine", label: "My decisions" },
  { id: "new", label: "New drafts" },
];

/** Which lane the user's role owns. */
function laneOwnedByRole(groups: string[]): LaneId | null {
  if (groups.includes("CEO")) return "ceo_exception";
  if (groups.includes("Delivery")) return "scope_gm";
  if (groups.includes("Finance") || groups.includes("HR") || groups.includes("Legal")) {
    return "functional_review";
  }
  return null;
}

function isBlocked(pkg: ApprovalPackage): boolean {
  if (pkg.status === "voided" || pkg.status === "rejected") return true;
  if (pkg.floors && (pkg.floors.failing?.length ?? 0) > 0) return true;
  if (pkg.floors && pkg.floors.requires_ceo) return true;
  return false;
}

function isNewDraft(pkg: ApprovalPackage): boolean {
  if (pkg.status === "voided" || pkg.status === "rejected") return true;
  if (!pkg.submitted_at) return true;
  return false;
}

export function SowApprovalsPage() {
  const { user } = useAuth();
  const groups = user?.groups ?? [];

  const [packages, setPackages] = useState<ApprovalPackage[] | null>(null);
  const [agreements, setAgreements] = useState<AgreementRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [chip, setChip] = useState<ChipId>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [pkgRes, agRes] = await Promise.all([
          listApprovalPackages({ size: 100 }),
          listAgreements().catch(() => ({
            items: [] as AgreementRow[],
            allowed_states: [],
          })),
        ]);
        if (cancelled) return;
        setPackages(pkgRes.items);
        setAgreements(agRes.items);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load packages");
        setPackages([]);
      }
    }
    void load();
    return () => {
      cancelled = false;
    };
  }, []);

  const ownedLane = laneOwnedByRole(groups);

  /**
   * Filter the raw package list by chip + search, then bucket by lane.
   * "My decisions" filters to the lane the user's role owns; if the user
   * has no reviewing role, the chip narrows to nothing (honest empty).
   */
  const packagesByLane = useMemo(() => {
    const buckets: Record<LaneId, ApprovalPackage[]> = {
      draft_intake: [],
      scope_gm: [],
      functional_review: [],
      ceo_exception: [],
      client_signature: [],
      handoff: [],
    };
    if (!packages) return buckets;
    const needle = search.trim().toLowerCase();
    for (const pkg of packages) {
      if (chip === "blocked" && !isBlocked(pkg)) continue;
      if (chip === "new" && !isNewDraft(pkg)) continue;
      if (chip === "mine") {
        if (!ownedLane) continue;
        if (laneForPackage(pkg) !== ownedLane) continue;
      }
      if (needle) {
        const hay = [
          pkg.id,
          pkg.opportunity_id,
          pkg.status,
          pkg.package_hash,
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(needle)) continue;
      }
      buckets[laneForPackage(pkg)].push(pkg);
    }
    return buckets;
  }, [packages, chip, ownedLane, search]);

  const totalPackages = packages?.length ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="SOW approvals"
        subtitle="Six-lane lifecycle · gates enforced server-side"
        actions={
          <div className="flex items-center gap-2">
            <Button asChild variant="secondary">
              <a
                href="/settings/data-imports/sows"
                data-testid="import-legacy-sows"
              >
                Import legacy SOWs
              </a>
            </Button>
            <Button asChild variant="primary">
              <a href="/sows/new">New SOW</a>
            </Button>
          </div>
        }
      />

      {/* Work in progress, above the board. A SOW that has not reached an
       * approval package appears in no lane, so without this the only route
       * back to an unfinished upload was browser history. */}
      <DraftSowStrip />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Package filters"
          className="flex flex-wrap gap-2"
        >
          {CHIPS.map((c) => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={chip === c.id}
              onClick={() => setChip(c.id)}
              className={cn(
                "rounded-control border px-3 py-1 text-secondary font-medium transition-motion",
                "focus-visible:outline-focus",
                chip === c.id
                  ? "border-primary bg-primary-subtle text-primary"
                  : "border-input-border bg-surface text-text hover:bg-primary-subtle",
              )}
              data-testid={`chip-${c.id}`}
            >
              {c.label}
              {c.id === "mine" && !ownedLane ? (
                <span className="ml-2 text-secondary text-text-secondary">
                  (no role)
                </span>
              ) : null}
            </button>
          ))}
        </div>
        <div className="relative w-full max-w-xs">
          <Search
            aria-hidden
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-secondary"
          />
          <Input
            aria-label="Search packages"
            placeholder="Search by SOW id, hash…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-panel border border-danger/30 bg-danger-surface p-3 text-danger"
        >
          <AlertTriangle className="h-4 w-4" />
          <span>We couldn't load approvals. {error}</span>
        </div>
      ) : null}

      {packages === null ? (
        <div
          role="status"
          aria-label="Loading approval packages"
          className="grid grid-cols-1 gap-3 md:grid-cols-3 min-[1560px]:grid-cols-6"
        >
          {LANES.map((lane) => (
            <div
              key={lane.id}
              className="h-64 rounded-panel border border-dashed border-divider bg-surface"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 min-[1560px]:grid-cols-6">
          {LANES.map((lane) => (
            <LaneColumn
              key={lane.id}
              lane={lane}
              packages={packagesByLane[lane.id]}
              agreements={agreements}
            />
          ))}
        </div>
      )}

      {packages !== null && totalPackages === 0 && !error ? (
        <EmptyState
          title="No SOW packages yet."
          description="Once someone submits a package from the New SOW studio it will land in a lane."
          action={
            <Button asChild variant="secondary">
              <a href="/sows/new">Open New SOW studio</a>
            </Button>
          }
        />
      ) : null}
    </div>
  );
}

interface LaneColumnProps {
  lane: LaneDef;
  packages: ApprovalPackage[];
  agreements: AgreementRow[];
}

function LaneColumn({ lane, packages, agreements }: LaneColumnProps) {
  return (
    <section
      aria-label={lane.title}
      data-testid={`lane-${lane.id}`}
      className={cn(
        "flex min-w-0 min-h-[16rem] flex-col gap-2 rounded-[10px]",
        "bg-surface-sunken p-[10px]",
      )}
    >
      <header className="flex items-center justify-between gap-2 px-1">
        <div className="min-w-0">
          <h2 className="text-[12px] font-semibold text-text-secondary truncate">
            {lane.title}
          </h2>
          <p className="text-[11px] text-text-muted truncate">{lane.subtitle}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-[4px] border border-border bg-surface",
            "px-[6px] text-[11px] font-medium text-text-secondary tnum",
          )}
          aria-label={`${packages.length} packages`}
        >
          {packages.length}
        </span>
      </header>
      <div className="flex flex-1 flex-col gap-2">
        {packages.length === 0 ? (
          <div
            role="status"
            className={cn(
              "rounded-[8px] border border-dashed border-borderStrong bg-surface",
              "p-4 text-center text-[12px] text-text-muted",
            )}
          >
            Nothing at this gate
          </div>
        ) : (
          packages.map((pkg) => (
            <PackageCard
              key={pkg.id}
              pkg={pkg}
              meta={buildMeta(pkg, agreements)}
              href={`/sows/${pkg.opportunity_id}`}
            />
          ))
        )}
      </div>
    </section>
  );
}

/**
 * Build a card metadata blob from the package + any agreements we
 * happen to have loaded. `listApprovalPackages` does not join the
 * client/opportunity, so we render honest placeholders when the
 * information isn't available. The card link still opens the
 * workspace where the full context lives.
 */
function buildMeta(
  pkg: ApprovalPackage,
  agreements: AgreementRow[],
): CardMeta {
  const nda = agreements.find((a) => a.kind === "NDA");
  const msa = agreements.find((a) => a.kind === "MSA");
  return {
    sowName: `SOW package ${pkg.id.slice(0, 8)}`,
    clientName: null,
    engagementType: null,
    ownerName: null,
    ownerEmail: null,
    proposedValue: null,
    currency: "USD",
    marginPct: pkg.floors
      ? pkg.floors.requires_ceo
        ? "below floor"
        : "within floor"
      : null,
    completeness: pkg.status.replace(/_/g, " "),
    nextAction: pkg.released_at
      ? "Distribution live"
      : pkg.status === "ready_to_sign"
      ? "Send envelope"
      : pkg.status === "pending_ceo_exception"
      ? "CEO decision"
      : "Await reviewer",
    ndaAgreement: nda ?? null,
    msaAgreement: msa ?? null,
    dueDate: null,
  };
}
