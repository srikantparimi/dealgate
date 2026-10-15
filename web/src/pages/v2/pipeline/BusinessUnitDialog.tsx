// S23-PL2 F7 / D3 · "Filter by business unit". A business unit is never shown
// without its region (US holds two of them). The fourth choice, "Unmapped
// region", appears while the list holds a deal whose HubSpot region has no
// business unit yet (or while it is selected).
import { useState } from "react";

import type { BusinessUnitFilter, WorkspaceOptions } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { PipelineDrawer, type DrawerControlProps } from "./FilterToolbar";
import { CheckboxOptions, PRECISE_FILTERS_TEXT, type CheckboxOption } from "./OwnerFilterDialog";

export interface BusinessUnitDialogProps extends DrawerControlProps {
  businessUnits: WorkspaceOptions["business_units"];
  /** `workspace.unmapped_regions`: deals in the filtered list with an unmapped HubSpot region. */
  unmappedDeals: number;
  selected: BusinessUnitFilter[];
  onApply: (bus: BusinessUnitFilter[]) => void;
}

export function BusinessUnitDialog({
  open,
  onOpenChange,
  onCloseAutoFocus,
  ...body
}: BusinessUnitDialogProps) {
  return (
    <PipelineDrawer
      open={open}
      onOpenChange={onOpenChange}
      onCloseAutoFocus={onCloseAutoFocus}
      kicker="Precise filters"
      title="Filter by business unit"
      description={PRECISE_FILTERS_TEXT}
    >
      <BusinessUnitBody {...body} />
    </PipelineDrawer>
  );
}

function BusinessUnitBody({
  businessUnits,
  unmappedDeals,
  selected,
  onApply,
}: Omit<BusinessUnitDialogProps, keyof DrawerControlProps>) {
  const [draft, setDraft] = useState<string[]>(selected);
  const options: CheckboxOption[] = [
    ...businessUnits.map((bu) => ({ value: bu.business_unit, label: bu.business_unit, note: bu.regions.join(", ") })),
    ...(unmappedDeals > 0 || selected.includes("unmapped") ? [{ value: "unmapped", label: "Unmapped region" }] : []),
  ];
  return (
    <>
      <CheckboxOptions options={options} checked={draft} onChange={setDraft} />
      <p className="text-secondary text-text-secondary">
        US covers two different business units, ST21 and IT Avalon. They are mapped from the HubSpot region value
        (Settings → Business units).
      </p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => onApply(draft as BusinessUnitFilter[])}>Apply filter</Button>
        <Button variant="secondary" onClick={() => onApply([])}>
          Clear this filter
        </Button>
      </div>
    </>
  );
}
