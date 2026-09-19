/**
 * Settings & controls — spec §18.
 *
 * The main region hosts a secondary vertical navigation on the left and the
 * matching subsection on the right. Each subsection is a real route
 * (`/settings/:section`); the URL alone can deep-link every panel.
 *
 * Sections are hidden from the nav when the user's role list has no
 * overlap with the section's `requireAny` list. Hiding a link is a UX
 * hint — the server still enforces every endpoint (CLAUDE.md rule 5).
 * If the user pastes a URL for a section they cannot access, the shell
 * renders a scoped "You don't have access…" empty state per spec §4.
 *
 * Wave 3 does NOT touch `App.tsx`; the route was registered upstream.
 * The 8 subsection components live under `settings/` and are the only
 * files this shell knows about.
 */

import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthProvider";
import { cn } from "../../lib/cn";
import { EmptyState } from "../../ui-v2/EmptyState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { AuditSection } from "./settings/AuditSection";
import { GeneralSection } from "./settings/GeneralSection";
import { ImportsSection } from "./settings/ImportsSection";
import { IntegrationsSection } from "./settings/IntegrationsSection";
import {
  DEFAULT_SECTION,
  findSection,
  isAllowed,
  SECTIONS,
  type SectionDef,
  type SectionId,
} from "./settings/nav";
import { PeopleSection } from "./settings/PeopleSection";
import { PolicySection } from "./settings/PolicySection";
import { RateCardsSection } from "./settings/RateCardsSection";
import { SystemHealthSection } from "./settings/SystemHealthSection";

function renderSection(id: SectionId) {
  switch (id) {
    case "general":
      return <GeneralSection />;
    case "rates":
      return <RateCardsSection />;
    case "policy":
      return <PolicySection />;
    case "people":
      return <PeopleSection />;
    case "integrations":
      return <IntegrationsSection />;
    case "imports":
      return <ImportsSection />;
    case "audit":
      return <AuditSection />;
    case "system-health":
      return <SystemHealthSection />;
  }
}

export function SettingsShellPage() {
  const { section: rawSection } = useParams<{ section: string }>();
  const { user } = useAuth();
  const groups = user?.groups ?? [];

  const requestedId = (rawSection ?? DEFAULT_SECTION) as SectionId;
  const requested = findSection(requestedId);
  const visible = SECTIONS.filter((s) => isAllowed(s, groups));

  const isUnknown = requested === null;
  const isForbidden = requested !== null && !isAllowed(requested, groups);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings & controls"
        subtitle="Workspace, governance and integrations. Policy changes and historical data edits are never casual switches."
      />
      <div className="flex flex-col gap-6 lg:flex-row">
        <SectionNav visible={visible} activeId={requestedId} />
        <main
          className="min-w-0 flex-1"
          aria-label={
            requested ? `${requested.label} section` : "Settings section"
          }
        >
          {isUnknown ? (
            <EmptyState
              title="Section not found"
              description={`The section "${rawSection}" does not exist. Pick one from the nav.`}
            />
          ) : isForbidden ? (
            <EmptyState
              title="You don't have access to this section."
              description="Ask a SystemAdmin if you need to view this section. The server enforces this even if the URL is bypassed."
            />
          ) : (
            renderSection(requested.id)
          )}
        </main>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------

function SectionNav({
  visible,
  activeId,
}: {
  visible: SectionDef[];
  activeId: SectionId;
}) {
  const location = useLocation();
  return (
    <nav
      aria-label="Settings sections"
      className="w-full shrink-0 lg:w-56"
    >
      <ul className="flex flex-row gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
        {visible.map((s) => (
          <li key={s.id}>
            <Link
              to={{ pathname: `/settings/${s.id}`, search: location.search }}
              aria-current={activeId === s.id ? "page" : undefined}
              className={cn(
                "flex items-start gap-2 rounded-control px-3 py-2 text-body",
                "text-text-secondary transition-motion",
                "hover:bg-primary-subtle hover:text-text",
                "focus-visible:outline-focus",
                activeId === s.id &&
                  "bg-primary-subtle text-primary font-medium",
              )}
            >
              <s.icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span className="flex flex-col gap-0.5">
                <span className="truncate">{s.label}</span>
                <span className="text-secondary text-text-secondary hidden lg:block">
                  {s.description}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
