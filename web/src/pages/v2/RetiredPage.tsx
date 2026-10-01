import { ArrowRight } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

// S20 W3 L09/L11: `/deals/:id` no longer implicitly forwards into
// `/sows/:id`. A deal without a SOW must remain navigable in its own
// right (review §"Deal workspace"). Until W2 ships the real
// `/deals/:id` page (see `docs/reports/s20/requests.md#W3-2026-09-30-02`)
// the retired page lands the user on Pipeline with a clear message, so
// nobody arrives at an empty SOW workspace pretending a SOW exists.
export function RetiredPage() {
  const { pathname } = useLocation();
  const { id: _id } = useParams();
  const isDeal = pathname.startsWith("/deals");
  const target = pathname.startsWith("/tasks")
    ? "/work"
    : isDeal
      ? "/pipeline"
      : "/sows";
  const label =
    target === "/work"
      ? "My work"
      : target === "/pipeline"
        ? "Pipeline"
        : "SOW workspace";
  return (
    <section className="py-12" aria-label="Page not found">
      <p className="text-secondary text-text-secondary">404</p>
      <h1 className="text-section font-semibold">This page has moved</h1>
      <p className="mt-2 text-body text-text-secondary">
        {isDeal
          ? "The deal detail page is being rebuilt. Return to Pipeline to find and open this deal."
          : "Your records and history are still available."}
      </p>
      <Link
        className="mt-6 inline-flex items-center gap-2 text-primary"
        to={target}
      >
        {label}
        <ArrowRight className="h-4 w-4" aria-hidden />
      </Link>
    </section>
  );
}
