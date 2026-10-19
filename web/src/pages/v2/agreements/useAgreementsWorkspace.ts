// S24-AG1 F1/F8/F9 · one request per view (B3). The workspace answers the
// cards, the cutover line, the standard panels and the client rows; the
// Documents and Activity lists are asked for only while their tab is open. A
// newer view cancels the request still in flight, typing in search waits
// 300 ms before asking, and the last answer stays on screen while the next one
// loads (the Pipeline's useWorkspace pattern).
import { useCallback, useEffect, useRef, useState } from "react";

import {
  agreementsParams,
  getAgreementActivity,
  getAgreementDocuments,
  getAgreementsWorkspace,
  type ActivityRow,
  type AgreementsWorkspace,
  type DocumentRow,
  type WorkspaceQuery,
} from "../../../api/agreements";
import { getMe } from "../../../api/client";
import type { ListQuery } from "./agreementsState";

export const SEARCH_DEBOUNCE_MS = 300;

export interface QueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  /** Ask again for the same view (after a write, an export or a download). */
  refetch: () => void;
}

export interface ListPage<T> {
  total: number;
  items: T[];
}

function useAbortableQuery<T>(
  key: string,
  searchlessKey: string,
  enabled: boolean,
  run: (signal: AbortSignal) => Promise<T>,
  failure: string,
): QueryResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const lastKey = useRef<string | null>(null);
  const lastSearchless = useRef<string | null>(null);
  const runRef = useRef(run);
  runRef.current = run;

  useEffect(() => {
    if (!enabled) return;
    // Only a search edit waits; any other change asks at once.
    const searchOnly = lastSearchless.current === searchlessKey && lastKey.current !== key;
    lastKey.current = key;
    lastSearchless.current = searchlessKey;
    const timer = window.setTimeout(
      () => {
        controller.current?.abort();
        const ctl = new AbortController();
        controller.current = ctl;
        setLoading(true);
        runRef
          .current(ctl.signal)
          .then((result) => {
            if (ctl.signal.aborted) return;
            setData(result);
            setError(null);
          })
          .catch((err: unknown) => {
            if (ctl.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
            setError(err instanceof Error && err.message ? err.message : failure);
          })
          .finally(() => {
            if (!ctl.signal.aborted) setLoading(false);
          });
      },
      searchOnly ? SEARCH_DEBOUNCE_MS : 0,
    );
    return () => window.clearTimeout(timer);
    // `key` and `searchlessKey` capture every field of the query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, searchlessKey, enabled, nonce]);

  useEffect(() => () => controller.current?.abort(), []);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, refetch };
}

/** GET /agreements/workspace for the view. */
export function useAgreementsWorkspace(query: WorkspaceQuery): QueryResult<AgreementsWorkspace> {
  const key = agreementsParams(query).toString();
  const searchless = agreementsParams({ ...query, q: "" }).toString();
  return useAbortableQuery(
    key,
    searchless,
    true,
    (signal) => getAgreementsWorkspace(query, signal),
    "The NDA and MSA records could not load.",
  );
}

function listKey(query: ListQuery, withSearch = true): string {
  return JSON.stringify([withSearch ? query.q.trim() : "", query.page, query.page_size]);
}

/** GET /agreements/documents, only while the Documents tab is open. */
export function useAgreementDocuments(query: ListQuery, enabled: boolean): QueryResult<ListPage<DocumentRow>> {
  return useAbortableQuery(
    listKey(query),
    listKey(query, false),
    enabled,
    (signal) => getAgreementDocuments({ q: query.q.trim(), page: query.page, page_size: query.page_size }, signal),
    "The documents could not load.",
  );
}

/** GET /agreements/activity, only while the Activity tab is open. */
export function useAgreementActivity(query: ListQuery, enabled: boolean): QueryResult<ListPage<ActivityRow>> {
  return useAbortableQuery(
    listKey(query),
    listKey(query, false),
    enabled,
    (signal) => getAgreementActivity({ q: query.q.trim(), page: query.page, page_size: query.page_size }, signal),
    "The activity could not load.",
  );
}

// --- the caller's rights ------------------------------------------------------------------------

export interface AgreementRoles {
  /** Legal or SystemAdmin: upload, replace, detach, mark, relationship. */
  canWrite: boolean;
  /** SystemAdmin: batches and the HubSpot mapping. */
  isAdmin: boolean;
}

export function rolesFromGroups(groups: readonly string[]): AgreementRoles {
  return {
    canWrite: groups.includes("Legal") || groups.includes("SystemAdmin"),
    isAdmin: groups.includes("SystemAdmin"),
  };
}

/**
 * The caller's rights, from the workspace answer (can_write / is_admin). Only
 * when an answer arrives without them is /me asked. Null until known: write
 * controls wait instead of guessing. The server answers 403 regardless.
 */
export function useAgreementRoles(data: AgreementsWorkspace | null): AgreementRoles | null {
  const [fallback, setFallback] = useState<AgreementRoles | null>(null);
  const known = data !== null && typeof data.can_write === "boolean";
  const canWrite = data?.can_write === true;
  const isAdmin = data?.is_admin === true;
  const needFallback = data !== null && !known;
  useEffect(() => {
    if (!needFallback || fallback) return;
    let live = true;
    getMe()
      .then((me) => {
        if (live) setFallback(rolesFromGroups(me.groups ?? []));
      })
      .catch(() => {
        if (live) setFallback({ canWrite: false, isAdmin: false });
      });
    return () => {
      live = false;
    };
  }, [needFallback, fallback]);
  const fromWorkspace = useRoleObject(known, canWrite, isAdmin);
  return fromWorkspace ?? fallback;
}

function useRoleObject(known: boolean, canWrite: boolean, isAdmin: boolean): AgreementRoles | null {
  const ref = useRef<AgreementRoles | null>(null);
  if (!known) return null;
  if (!ref.current || ref.current.canWrite !== canWrite || ref.current.isAdmin !== isAdmin) {
    ref.current = { canWrite, isAdmin };
  }
  return ref.current;
}
