import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";

export function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | null | undefined;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="min-w-0 space-y-1 text-secondary">
      {label}
      <Input
        type={type === "decimal" ? "text" : type}
        inputMode={type === "decimal" ? "decimal" : undefined}
        placeholder="Unconfirmed"
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
export type Option = string | { value: string; label: string };
const optionValue = (option: Option) =>
  typeof option === "string" ? option : option.value;
const optionLabel = (option: Option) =>
  typeof option === "string" ? option : option.label;
export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  options: Option[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="min-w-0 space-y-1 text-secondary">
      {label}
      <select
        aria-label={label}
        className="block h-10 w-full rounded-md border border-divider bg-surface px-2"
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Unconfirmed</option>
        {value && !options.some((option) => optionValue(option) === value) && (
          <option value={value}>{value} (existing)</option>
        )}
        {options.map((option) => (
          <option key={optionValue(option)} value={optionValue(option)}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    </label>
  );
}
export interface Column<T> {
  key: keyof T;
  label: string;
  type?: "date" | "decimal";
  options?: Option[];
  readonly?: boolean;
}
export function Rows<T extends object>({
  title,
  rows,
  columns,
  onChange,
  create,
  addLabel,
}: {
  title: string;
  rows: T[];
  columns: Column<T>[];
  onChange: (rows: T[]) => void;
  create: () => T;
  addLabel: string;
}) {
  return (
    <section aria-label={title} className="min-w-0 space-y-3">
      <h3 className="font-medium">{title}</h3>
      <div className="relative overflow-x-auto">
        <table className="w-full text-left text-secondary">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={String(column.key)} className="px-2 py-2">
                  {column.label}
                </th>
              ))}
              <th className="w-12">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-divider">
                {columns.map((column) => (
                  <td className="min-w-36 px-2 py-2" key={String(column.key)}>
                    {column.readonly ? (
                      <span>{String(row[column.key] ?? "None")}</span>
                    ) : column.options ? (
                      <select
                        aria-label={`${column.label} ${index + 1}`}
                        className="h-10 w-full rounded-md border border-divider bg-surface px-2"
                        value={String(row[column.key] ?? "")}
                        onChange={(e) =>
                          onChange(
                            rows.map((item, i) =>
                              i === index
                                ? { ...item, [column.key]: e.target.value }
                                : item,
                            ),
                          )
                        }
                      >
                        <option value="">Unconfirmed</option>
                        {row[column.key] &&
                        !column.options.some(
                          (option) => optionValue(option) === row[column.key],
                        ) ? (
                          <option value={String(row[column.key])}>
                            {String(row[column.key])} (existing)
                          </option>
                        ) : null}
                        {column.options.map((option) => (
                          <option
                            key={optionValue(option)}
                            value={optionValue(option)}
                          >
                            {optionLabel(option)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <Input
                        aria-label={`${column.label} ${index + 1}`}
                        type={column.type === "date" ? "date" : "text"}
                        inputMode={
                          column.type === "decimal" ? "decimal" : undefined
                        }
                        value={String(row[column.key] ?? "")}
                        onChange={(e) =>
                          onChange(
                            rows.map((item, i) =>
                              i === index
                                ? {
                                    ...item,
                                    [column.key]:
                                      e.target.value ||
                                      (column.type ? null : ""),
                                  }
                                : item,
                            ),
                          )
                        }
                      />
                    )}
                  </td>
                ))}
                <td>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${title.toLowerCase()} row ${index + 1}`}
                    title={`Delete ${title.toLowerCase()} row ${index + 1}`}
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button variant="secondary" onClick={() => onChange([...rows, create()])}>
        <Plus className="h-4 w-4" />
        {addLabel}
      </Button>
    </section>
  );
}
