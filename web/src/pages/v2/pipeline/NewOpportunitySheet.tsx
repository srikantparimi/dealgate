/**
 * NewOpportunitySheet — the right Sheet drawer opened by the pipeline
 * page's header action. Spec §7 explicitly warns against a giant
 * undifferentiated form: the sheet is broken into progressive sections
 * (Client → Commercial → Delivery → Follow-up) that reveal in order so a
 * Sales/Marketing user can save a partial draft and move on.
 *
 * No API is called from here (the create-opportunity endpoint is
 * Agent XX's territory). The sheet gathers the fields and, on Save,
 * hands them to `onDraft` — currently a no-op that surfaces a toast in
 * the parent. This keeps the page's promise honest: an unwired form
 * cannot claim to create an opportunity.
 */

import { useState, type FormEvent } from "react";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { Label } from "../../../ui-v2/primitives/label";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../../ui-v2/primitives/sheet";

export interface NewOpportunityDraft {
  clientDisplayName: string;
  legalEntity: string;
  accountOwner: string;
  functionalRequirement: string;
  engagementType: string;
  planningValue: string;
  currency: string;
  targetStart: string;
  expectedClose: string;
  nextAction: string;
  nextActionDate: string;
}

export interface NewOpportunitySheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDraft?: (draft: NewOpportunityDraft) => void;
}

const emptyDraft: NewOpportunityDraft = {
  clientDisplayName: "",
  legalEntity: "",
  accountOwner: "",
  functionalRequirement: "",
  engagementType: "",
  planningValue: "",
  currency: "USD",
  targetStart: "",
  expectedClose: "",
  nextAction: "",
  nextActionDate: "",
};

export function NewOpportunitySheet({
  open,
  onOpenChange,
  onDraft,
}: NewOpportunitySheetProps) {
  const [draft, setDraft] = useState<NewOpportunityDraft>(emptyDraft);

  function update<K extends keyof NewOpportunityDraft>(
    key: K,
    value: NewOpportunityDraft[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onDraft?.(draft);
    setDraft(emptyDraft);
    onOpenChange(false);
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        aria-label="New opportunity"
        className="flex flex-col gap-4 overflow-y-auto"
      >
        <SheetHeader>
          <SheetTitle>New opportunity</SheetTitle>
          <SheetDescription>
            Progressive sections — fill what you know, save the draft and
            add the rest later. New entities start with Missing NDA and MSA
            until Legal verifies evidence.
          </SheetDescription>
        </SheetHeader>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-6"
          data-testid="new-opportunity-form"
        >
          <fieldset className="flex flex-col gap-3">
            <legend className="text-section text-text">Client</legend>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-client">Client display name</Label>
              <Input
                id="opp-client"
                required
                value={draft.clientDisplayName}
                onChange={(e) => update("clientDisplayName", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-entity">Legal entity</Label>
              <Input
                id="opp-entity"
                value={draft.legalEntity}
                onChange={(e) => update("legalEntity", e.target.value)}
                placeholder="Lookup or new entity"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-owner">Account owner</Label>
              <Input
                id="opp-owner"
                value={draft.accountOwner}
                onChange={(e) => update("accountOwner", e.target.value)}
                placeholder="name@smartek21.com"
              />
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-section text-text">Commercial</legend>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-func">Functional requirement</Label>
              <Input
                id="opp-func"
                value={draft.functionalRequirement}
                onChange={(e) =>
                  update("functionalRequirement", e.target.value)
                }
                placeholder="Short description"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-engagement">Engagement type</Label>
              <Input
                id="opp-engagement"
                value={draft.engagementType}
                onChange={(e) => update("engagementType", e.target.value)}
                placeholder="staff_aug, fixed_price, assessment…"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="opp-value">Planning value</Label>
                <Input
                  id="opp-value"
                  inputMode="decimal"
                  value={draft.planningValue}
                  onChange={(e) => update("planningValue", e.target.value)}
                  placeholder="Unknown"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="opp-currency">Currency</Label>
                <Input
                  id="opp-currency"
                  value={draft.currency}
                  onChange={(e) => update("currency", e.target.value)}
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-section text-text">Delivery window</legend>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <Label htmlFor="opp-start">Target start</Label>
                <Input
                  id="opp-start"
                  type="date"
                  value={draft.targetStart}
                  onChange={(e) => update("targetStart", e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="opp-close">Expected close</Label>
                <Input
                  id="opp-close"
                  type="date"
                  value={draft.expectedClose}
                  onChange={(e) => update("expectedClose", e.target.value)}
                />
              </div>
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-section text-text">Next follow-up</legend>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-next">Next action</Label>
              <Input
                id="opp-next"
                value={draft.nextAction}
                onChange={(e) => update("nextAction", e.target.value)}
                placeholder="e.g. Send capabilities deck"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opp-next-date">Next action date</Label>
              <Input
                id="opp-next-date"
                type="date"
                value={draft.nextActionDate}
                onChange={(e) => update("nextActionDate", e.target.value)}
              />
            </div>
          </fieldset>

          <div className="flex items-center justify-end gap-2 pt-2">
            <SheetClose asChild>
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </SheetClose>
            <Button type="submit" variant="primary">
              Save draft
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
