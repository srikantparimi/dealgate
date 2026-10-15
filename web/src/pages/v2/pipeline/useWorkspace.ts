// S23-PL2 F2 · one request per view. A newer view cancels the request still in
// flight, typing in search waits 300 ms before asking, and the last answer
// stays on screen while the next one loads.
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { getWorkspace, workspaceParams, type Workspace, type WorkspaceQuery } from "../../../api/pipelineWorkspace";

export const SEARCH_DEBOUNCE_MS = 300;

export interface WorkspaceResult {
  data: Workspace | null;
  loading: boolean;
  error: string | null;
  /** Ask again for the same view (after a watch, a next action or a group change). */
  refetch: () => void;
}

export function useWorkspace(query: WorkspaceQuery): WorkspaceResult {
  const [data, setData] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const lastKey = useRef<string | null>(null);

  const key = workspaceParams(query).toString();
  const keyWithoutSearch = workspaceParams({ ...query, q: "" }).toString();
  const lastWithoutSearch = useRef<string | null>(null);

  useEffect(() => {
    // Only a search edit waits; any other change asks at once.
    const searchOnly = lastWithoutSearch.current === keyWithoutSearch && lastKey.current !== key;
    lastKey.current = key;
    lastWithoutSearch.current = keyWithoutSearch;
    const timer = window.setTimeout(
      () => {
        controller.current?.abort();
        const ctl = new AbortController();
        controller.current = ctl;
        setLoading(true);
        getWorkspace(query, ctl.signal)
          .then((ws) => {
            if (ctl.signal.aborted) return;
            setData(ws);
            setError(null);
          })
          .catch((err: unknown) => {
            if (ctl.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
            setError(err instanceof ApiError || err instanceof Error ? err.message : "The Pipeline could not load.");
          })
          .finally(() => {
            if (!ctl.signal.aborted) setLoading(false);
          });
      },
      searchOnly ? SEARCH_DEBOUNCE_MS : 0,
    );
    return () => window.clearTimeout(timer);
    // `key` captures every field of `query`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  useEffect(() => () => controller.current?.abort(), []);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, refetch };
}
