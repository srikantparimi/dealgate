/**
 * Settings → Data imports (spec §18).
 *
 * The legacy SOW + resource-line wizard already lives at
 * `/legacy/import` and the actuals CSV import at `/actuals/import`.
 * Rather than duplicate that logic here we deep-link into them and
 * describe the flow honestly: upload → map → validate → preview → confirm
 * → reconcile, with reversible staging before commit.
 *
 * Spec is explicit: legacy approvals require provenance + legal/finance
 * verification. We do NOT manufacture historical approvals — records
 * come in labelled "Imported · Evidence unverified" until the paper
 * trail is attached.
 */

import { Link, useLocation, useNavigate } from "react-router-dom";
import { Button } from "../../../ui-v2/primitives/button";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../ui-v2/primitives/tabs";

type TabId = "new" | "in-progress" | "completed" | "attention";

export function ImportsSection() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const activeTab = (params.get("tab") as TabId) || "new";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Data imports"
        subtitle={
          "Upload → map → validate → preview → confirm → reconcile. Staging " +
          "is reversible before commit. Legacy approvals are never " +
          "manufactured; records land as \"Imported · Evidence unverified\" " +
          "until the paper trail is attached."
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
        <TabsList aria-label="Data import tabs">
          <TabsTrigger value="new">New import</TabsTrigger>
          <TabsTrigger value="in-progress">In progress</TabsTrigger>
          <TabsTrigger value="completed">Completed</TabsTrigger>
          <TabsTrigger value="attention">Needs attention</TabsTrigger>
        </TabsList>

        <TabsContent value="new">
          <NewImportPanel />
        </TabsContent>

        <TabsContent value="in-progress">
          <EmptyState
            title="No imports in progress"
            description={
              "Once a batch is uploaded it appears here until Finance confirms " +
              "the reconciliation preview."
            }
          />
        </TabsContent>

        <TabsContent value="completed">
          <EmptyState
            title="No completed imports yet"
            description="Approved batches move here with a link to the reconciliation report."
          />
        </TabsContent>

        <TabsContent value="attention">
          <div className="flex flex-col gap-3 rounded-panel border border-divider bg-surface p-4">
            <div className="flex items-center gap-2">
              <StatusBadge tone="warn" label="What lands here" />
            </div>
            <ul className="ml-5 list-disc text-body text-text">
              <li>Duplicate SOW refs across a legacy batch.</li>
              <li>Unknown legal entities or client names.</li>
              <li>Missing currency codes or unresolved dates.</li>
              <li>Row-level validation errors — downloadable as CSV.</li>
            </ul>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function NewImportPanel() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ImporterCard
        title="Legacy SOWs + resource lines"
        description={
          "Bulk-upload executed SOW PDFs and paste the Excel of per-project " +
          "resources. Records land as legacy — approval not evidenced — " +
          "until Finance + Legal attach the paper trail."
        }
        href="/legacy/import"
      />
      <ImporterCard
        title="Actuals CSV"
        description={
          "Recognised revenue + realised cost by resource line, per month. " +
          "The API validates the whole file; per-row errors are downloadable."
        }
        href="/actuals/import"
      />
    </div>
  );
}

function ImporterCard({
  title,
  description,
  href,
}: {
  title: string;
  description: string;
  href: string;
}) {
  return (
    <div className="flex flex-col justify-between gap-3 rounded-panel border border-divider bg-surface p-4">
      <div>
        <h3 className="text-section text-text">{title}</h3>
        <p className="mt-1 text-body text-text-secondary">{description}</p>
      </div>
      <div>
        <Button asChild variant="secondary" size="sm">
          <Link to={href}>Open importer</Link>
        </Button>
      </div>
    </div>
  );
}
