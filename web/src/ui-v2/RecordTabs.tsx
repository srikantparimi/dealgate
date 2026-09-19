import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "../lib/cn";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "./primitives/tabs";

export interface RecordTabItem {
  value: string;
  label: ReactNode;
  content: ReactNode;
  /** If set, changing to this tab pushes this path onto the router. */
  href?: string;
}

export interface RecordTabsProps {
  items: RecordTabItem[];
  value: string;
  onValueChange?: (value: string) => void;
  className?: string;
}

/**
 * Wraps Radix Tabs and keeps the router path in sync when tab items opt in
 * via `href`. Kept intentionally thin — callers own the state so that
 * pages can drive the tab from the URL segment.
 */
export function RecordTabs({
  items,
  value,
  onValueChange,
  className,
}: RecordTabsProps) {
  const navigate = useNavigate();

  return (
    <Tabs
      value={value}
      onValueChange={(next) => {
        onValueChange?.(next);
        const target = items.find((i) => i.value === next);
        if (target?.href) navigate(target.href);
      }}
      className={cn("w-full", className)}
    >
      <TabsList className="w-full overflow-x-auto">
        {items.map((item) => (
          <TabsTrigger key={item.value} value={item.value}>
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {items.map((item) => (
        <TabsContent key={item.value} value={item.value}>
          {item.content}
        </TabsContent>
      ))}
    </Tabs>
  );
}
