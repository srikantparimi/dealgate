import { PageHeader } from "../../ui-v2/PageHeader";
import { EmptyState } from "../../ui-v2/EmptyState";

export function StubPage({ title, agent }: { title: string; agent: string }) {
  return (
    <div>
      <PageHeader title={title} subtitle={`Coming from ${agent} in Sprint 8 Wave 2`} />
      <EmptyState
        title="Under construction"
        description="This page is being rebuilt on the V2 design system. The legacy screen is still reachable from the sidebar's Legacy shortcuts."
      />
    </div>
  );
}
