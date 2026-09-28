import { Link } from "react-router-dom";

export function AgreementsPanel({
  legalEntityId,
  readOnly,
}: {
  legalEntityId: string;
  readOnly?: boolean;
}) {
  return (
    <Link
      className="text-primary underline"
      to={`/agreements?entity=${legalEntityId}`}
    >
      {readOnly ? "View NDA & MSA" : "Manage NDA & MSA"}
    </Link>
  );
}
