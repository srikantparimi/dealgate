import type { ReactNode } from "react";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  width?: number | string;
}

export function Table<Row extends { id: string | number }>({
  columns,
  rows,
  onRowClick,
  ariaLabel,
}: {
  columns: Column<Row>[];
  rows: Row[];
  onRowClick?: (row: Row) => void;
  ariaLabel?: string;
}) {
  return (
    <table
      aria-label={ariaLabel}
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontSize: 14,
      }}
    >
      <thead>
        <tr style={{ background: "#f9fafb", textAlign: "left" }}>
          {columns.map((c) => (
            <th
              key={c.key}
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid #e5e7eb",
                fontWeight: 600,
                color: "#374151",
                width: c.width,
              }}
            >
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={String(r.id)}
            onClick={onRowClick ? () => onRowClick(r) : undefined}
            style={{
              cursor: onRowClick ? "pointer" : "default",
              borderBottom: "1px solid #f3f4f6",
            }}
          >
            {columns.map((c) => (
              <td key={c.key} style={{ padding: "8px 12px" }}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
