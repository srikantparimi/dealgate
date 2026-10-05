import { request } from "./client";

export interface SupplyInterval {
  kind: "gross" | "committed" | "reserved" | "hired";
  allocation: string;
  start_date: string;
  end_date: string;
  assignment_key: string | null;
}
export interface SupplyBatch {
  id: string;
  revision: number;
  person_count: number;
  source_as_of: string;
  status: string;
}
export interface SupplySource extends SupplyBatch {
  source_system: string;
}
export interface SupplyPerson {
  person_id: string;
  person_key?: string;
  version_id: string;
  source_system: string;
  batch_id: string;
  display_name: string;
  role: string;
  skills: string[];
  level: string;
  location: string;
  timezone: string;
  evidence: string[];
  intervals: SupplyInterval[];
}
export interface PeopleAvailability {
  basis: "gross_with_commitments";
  is_reservation: false;
  sources: SupplySource[];
  people: SupplyPerson[];
}
export interface PeopleImports {
  items: (SupplySource & {
    imported_at: string;
    imported_by: string;
    imported_by_name?: string;
    reason: string;
    previous_batch_id: string | null;
  })[];
  total: number;
  page: number;
  size: number;
}
// Uploaded fields remain intact for the server's whole-file strict validation.
export type SupplyImport = Record<string, unknown> & {
  request_key: string;
  expected_previous_batch_id: string | null;
  reason: string;
};
export const getPeopleAvailability = (signal?: AbortSignal) =>
  request<PeopleAvailability>("/people/availability", { signal });
export const getPeopleImports = (page = 1, signal?: AbortSignal) =>
  request<PeopleImports>(`/people/imports?page=${page}&size=50`, { signal });
export const importPeopleSupply = (body: SupplyImport) =>
  request<SupplyBatch>("/people/imports", {
    method: "POST",
    body: JSON.stringify(body),
  });
