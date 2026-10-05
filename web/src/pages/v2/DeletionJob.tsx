import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { getDeletionJob, retryDeletionJob, type DeletionJobResponse } from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { Button } from "../../ui-v2/primitives/button";

export function DeletionJobPage() {
  const { id } = useParams();
  const [job, setJob] = useState<DeletionJobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const sourceName = job?.subject_type === "client" ? "Client" : job?.subject_type === "opportunity" ? "Opportunity" : job?.subject_type === "agreement" ? "Agreement" : "SOW";
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getDeletionJob(id);
        if (cancelled) return;
        setJob(result);
        setError(null);
        if (result.status !== "done") timer = setTimeout(() => void poll(), 3000);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Deletion status unavailable");
      }
    };
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, refresh]);
  const retry = async () => {
    if (!id) return;
    setRetrying(true);
    try {
      setJob(await retryDeletionJob(id));
      setRefresh(value => value + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Retry could not be queued");
    } finally {
      setRetrying(false);
    }
  };
  return <div>
    <PageHeader title={`${sourceName} deletion`} actions={<Link to={sourceName === "SOW" ? "/sows" : "/pipeline"}>{sourceName === "SOW" ? "SOWs" : "Pipeline"}</Link>} />
    {error && <ErrorState title="Deletion status unavailable" description={error} onRetry={() => setRefresh(value => value + 1)} />}
    {!job && !error && <p role="status">Loading deletion status...</p>}
    {job && <section className="space-y-4 border-b border-divider py-6">
      <h2 className="text-lg font-semibold break-words">{job.sow_title}</h2>
      <p>{job.source_deleted ? `${sourceName} removed from active records` : `${sourceName} removal pending`}</p>
      <p role="status">{job.status === "done" ? "File cleanup complete" : job.status === "failed" ? "File cleanup failed" : "File cleanup pending"}</p>
      {job.last_error && <p role="alert">{job.last_error}</p>}
      {job.next_attempt_at && <p>Next attempt: {new Date(job.next_attempt_at).toLocaleString()}</p>}
      {job.status === "failed" && <Button onClick={() => void retry()} disabled={retrying}>
        <RefreshCw size={16} aria-hidden="true" />{retrying ? "Queuing..." : "Retry cleanup"}
      </Button>}
      <ul>{Object.entries(job.counts).map(([name, count]) => <li key={name}>{name.replaceAll("_", " ")}: {count}</li>)}</ul>
      <Link to="/projects">Projects</Link>
    </section>}
  </div>;
}
