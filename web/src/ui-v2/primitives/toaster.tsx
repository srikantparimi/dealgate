import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "./toast";

interface ToastItem {
  id: string;
  title?: ReactNode;
  description?: ReactNode;
  variant?: "default" | "success" | "warning" | "destructive";
  durationMs?: number;
}

interface ToastContextValue {
  toast: (t: Omit<ToastItem, "id">) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/**
 * Global toast provider. Wrap the app root in `<Toaster>` and call
 * `useToast()` anywhere below it. Non-financial confirmations only — never
 * use a toast to acknowledge an approval, signature or release (spec §4).
 */
export function Toaster({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
  }, []);

  const toast = useCallback((t: Omit<ToastItem, "id">) => {
    const id = crypto.randomUUID();
    setItems((prev) => [...prev, { ...t, id }]);
    return id;
  }, []);

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      <ToastProvider swipeDirection="right">
        {children}
        {items.map((item) => (
          <Toast
            key={item.id}
            variant={item.variant}
            duration={item.durationMs ?? 5000}
            onOpenChange={(open) => {
              if (!open) dismiss(item.id);
            }}
          >
            <div className="flex-1">
              {item.title ? <ToastTitle>{item.title}</ToastTitle> : null}
              {item.description ? (
                <ToastDescription>{item.description}</ToastDescription>
              ) : null}
            </div>
            <ToastClose />
          </Toast>
        ))}
        <ToastViewport />
      </ToastProvider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <Toaster>");
  return ctx;
}
