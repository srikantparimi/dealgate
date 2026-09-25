import { ArrowRight } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

export function RetiredPage() {
  const { pathname } = useLocation();
  const { id } = useParams();
  const target = pathname.startsWith("/tasks")
    ? "/work"
    : pathname.startsWith("/deals")
      ? id
        ? `/sows/${id}`
        : "/pipeline"
      : "/sows";
  const label =
    target === "/work"
      ? "My work"
      : target === "/pipeline"
        ? "Pipeline clients"
        : "SOW workspace";
  return (
    <section className="py-12" aria-label="Page not found">
      <p className="text-secondary text-text-secondary">404</p>
      <h1 className="text-section font-semibold">This page has moved</h1>
      <p className="mt-2 text-body text-text-secondary">
        Your records and history are still available.
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
