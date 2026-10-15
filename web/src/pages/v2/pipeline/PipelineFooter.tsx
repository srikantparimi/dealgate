// S23-PL2 F1 · the page footer: the basis every number on the page uses.
import { longCalendarDate } from "./format";

export function PipelineFooter({ today }: { today: string | null }) {
  return (
    <footer className="text-secondary text-text-secondary">
      {today
        ? `USD · calendar dates · today is ${longCalendarDate(today)} (America/Los_Angeles)`
        : "USD · calendar dates (America/Los_Angeles)"}
    </footer>
  );
}
