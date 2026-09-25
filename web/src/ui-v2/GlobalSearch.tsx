import { Building2, FileText, Layers, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  getDeals,
  listClients,
  type ClientListRow,
  type DealRow,
} from "../api/client";
import { cn } from "../lib/cn";
import { Button } from "./primitives/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "./primitives/command";
import { NAV_GROUPS } from "./PrimaryNavigation";

/**
 * ⌘K / Ctrl+K command palette (spec §4).
 *
 * - Groups: Opportunities, Clients, Contracts, Projects, Pages.
 * - Wires to `getDeals` and `listClients` — server enforces authorisation
 *   so restricted rows never appear in results.
 * - Arrow keys navigate; Enter opens; Escape closes.
 * - The header button is the accessible trigger; keyboard shortcut is
 *   supplementary, never the only entry point.
 */

interface SearchResults {
  deals: DealRow[];
  clients: ClientListRow[];
  loading: boolean;
  error: string | null;
}

const EMPTY_RESULTS: SearchResults = {
  deals: [],
  clients: [],
  loading: false,
  error: null,
};

const PAGE_ROUTES: Array<{ to: string; label: string }> = NAV_GROUPS.flatMap(
  (g) => g.items.map((i) => ({ to: i.to, label: i.label })),
);

export interface GlobalSearchProps {
  className?: string;
}

export function GlobalSearch({ className }: GlobalSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResults>(EMPTY_RESULTS);
  const navigate = useNavigate();

  const openPalette = useCallback(() => {
    setOpen(true);
  }, []);

  // Keyboard shortcut — supplementary, header button remains the primary
  // trigger. Meta/ctrl+K is the shadcn/ui convention.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Debounced remote lookup. Server owns authorisation so we can trust
  // whatever comes back; empty query resets to page suggestions only.
  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults(EMPTY_RESULTS);
      return;
    }
    let cancelled = false;
    setResults((prev) => ({ ...prev, loading: true, error: null }));
    const handle = window.setTimeout(async () => {
      try {
        const [dealRes, clientRes] = await Promise.all([
          getDeals({ size: 6 }),
          listClients({ search: trimmed, size: 6 }),
        ]);
        if (cancelled) return;
        const q = trimmed.toLowerCase();
        setResults({
          loading: false,
          error: null,
          deals: dealRes.items.filter(
            (row) =>
              (row.client_name ?? "").toLowerCase().includes(q) ||
              row.hubspot_deal_id.toLowerCase().includes(q),
          ),
          clients: clientRes.items,
        });
      } catch (err) {
        if (cancelled) return;
        setResults({
          loading: false,
          deals: [],
          clients: [],
          error:
            err instanceof ApiError ? err.message : "Search failed",
        });
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [open, query]);

  const pageMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return PAGE_ROUTES.slice(0, 6);
    return PAGE_ROUTES.filter((p) => p.label.toLowerCase().includes(q));
  }, [query]);

  const handleSelect = useCallback(
    (path: string) => {
      setOpen(false);
      setQuery("");
      navigate(path);
    },
    [navigate],
  );

  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        className={cn("gap-2 text-text-secondary", className)}
        onClick={openPalette}
        aria-label="Open global search"
        aria-keyshortcuts="Meta+K Control+K"
      >
        <Search className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">Search</span>
        <kbd className="ml-2 hidden rounded-[4px] border border-divider bg-canvas px-1.5 text-secondary text-text-secondary sm:inline">
          ⌘K
        </kbd>
      </Button>

      <CommandDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setQuery("");
        }}
        label="Global search"
      >
        <CommandInput
          value={query}
          onValueChange={setQuery}
          placeholder="Search opportunities, clients, contracts, projects, pages…"
        />
        <CommandList>
          {results.error ? (
            <div role="alert" className="p-4 text-body text-danger">
              {results.error}
            </div>
          ) : null}

          {!results.loading &&
          !results.error &&
          results.deals.length === 0 &&
          results.clients.length === 0 &&
          pageMatches.length === 0 ? (
            <CommandEmpty>
              No matches. Try another client name, record ID or page.
            </CommandEmpty>
          ) : null}

          {results.deals.length > 0 ? (
            <CommandGroup heading="Opportunities">
              {results.deals.map((row) => (
                <CommandItem
                  key={row.id}
                  value={`opp-${row.id}-${row.client_name ?? ""}`}
                  onSelect={() => handleSelect(`/sows/${row.id}`)}
                >
                  <Layers className="h-4 w-4 text-text-secondary" aria-hidden />
                  <span className="flex-1 truncate">
                    {row.client_name ?? "Unnamed deal"}
                  </span>
                  <span className="text-secondary text-text-secondary">
                    {row.hubspot_deal_id}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}

          {results.clients.length > 0 ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="Clients">
                {results.clients.map((row) => (
                  <CommandItem
                    key={row.id}
                    value={`client-${row.id}-${row.name}`}
                    onSelect={() => handleSelect(`/clients/${row.id}`)}
                  >
                    <Building2 className="h-4 w-4 text-text-secondary" aria-hidden />
                    <span className="flex-1 truncate">{row.name}</span>
                    {row.hubspot_company_id ? (
                      <span className="text-secondary text-text-secondary">
                        {row.hubspot_company_id}
                      </span>
                    ) : null}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}

          {pageMatches.length > 0 ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="Pages">
                {pageMatches.map((page) => (
                  <CommandItem
                    key={page.to}
                    value={`page-${page.to}`}
                    onSelect={() => handleSelect(page.to)}
                >
                    <FileText className="h-4 w-4 text-text-secondary" aria-hidden />
                    <span>{page.label}</span>
                    <span className="ml-auto text-secondary text-text-secondary">
                      {page.to}
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
        </CommandList>
      </CommandDialog>
    </>
  );
}
