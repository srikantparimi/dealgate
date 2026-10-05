import type { CommercialComponent } from "../../../../api/commercial";

/** A new immutable revision binds every derived assignment/child to its source and policy. */
export function bindCommercialSource(
  component: CommercialComponent,
  source: Pick<
    CommercialComponent,
    "source_id" | "source_version" | "policy_version"
  >,
): CommercialComponent {
  return {
    ...component,
    ...source,
    staffing: component.staffing.map((row) => ({
      ...row,
      ...source,
      component_id: component.component_id,
      profile_version: component.profile_version,
    })),
    pricing:
      component.profile === "hybrid" && component.pricing?.components
        ? {
            ...component.pricing,
            components: component.pricing.components.map((child) =>
              bindCommercialSource(child, source),
            ),
          }
        : component.pricing,
  };
}
