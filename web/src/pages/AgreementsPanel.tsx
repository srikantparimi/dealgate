import { Link } from "react-router-dom";

/**
 * S17: agreements are a flat NDA/MSA doc store keyed to the client. The
 * `legalEntityId` prop is kept for source compatibility with the S16a
 * callers; the link now points at the client-scoped register.
 */
export function AgreementsPanel({
  clientId,
  legalEntityId,
  readOnly,
}: {
  clientId?: string;
  legalEntityId?: string;
  readOnly?: boolean;
}) {
  const href = clientId
    ? `/agreements?client=${clientId}`
    : legalEntityId
      ? `/agreements?entity=${legalEntityId}`
      : "/agreements";
  return (
    <Link className="text-primary underline" to={href}>
      {readOnly ? "View NDA & MSA" : "Manage NDA & MSA"}
    </Link>
  );
}
