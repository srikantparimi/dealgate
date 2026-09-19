import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * Appearance + density preferences persisted to `localStorage`.
 *
 * Spec §2 and §4:
 *  - Appearance: System / Light / Dark. `System` follows
 *    `prefers-color-scheme`. Persist independently of financial settings.
 *  - Density: Comfortable / Compact. Never automatic — always a user
 *    preference.
 *  - Reduced motion is respected globally via CSS.
 */
export type Appearance = "system" | "light" | "dark";
export type Density = "comfortable" | "compact";

const APPEARANCE_KEY = "dealgate:v2:appearance";
const DENSITY_KEY = "dealgate:v2:density";

interface PreferencesContextValue {
  appearance: Appearance;
  effectiveTheme: "light" | "dark";
  density: Density;
  setAppearance: (a: Appearance) => void;
  setDensity: (d: Density) => void;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

function readStorage<T extends string>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return (raw as T) ?? fallback;
  } catch {
    return fallback;
  }
}

function resolveEffectiveTheme(appearance: Appearance): "light" | "dark" {
  if (appearance !== "system") return appearance;
  if (typeof window === "undefined" || !window.matchMedia) return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearanceState] = useState<Appearance>(() =>
    readStorage<Appearance>(APPEARANCE_KEY, "system"),
  );
  const [density, setDensityState] = useState<Density>(() =>
    readStorage<Density>(DENSITY_KEY, "comfortable"),
  );
  const [effectiveTheme, setEffectiveTheme] = useState<"light" | "dark">(() =>
    resolveEffectiveTheme(readStorage<Appearance>(APPEARANCE_KEY, "system")),
  );

  const setAppearance = useCallback((next: Appearance) => {
    setAppearanceState(next);
    try {
      window.localStorage.setItem(APPEARANCE_KEY, next);
    } catch {
      // ignore quota / private-mode failures
    }
  }, []);

  const setDensity = useCallback((next: Density) => {
    setDensityState(next);
    try {
      window.localStorage.setItem(DENSITY_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  // Track `prefers-color-scheme` when the user picked System.
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function update() {
      setEffectiveTheme(resolveEffectiveTheme(appearance));
    }
    update();
    if (appearance !== "system") return undefined;
    if (media.addEventListener) {
      media.addEventListener("change", update);
      return () => media.removeEventListener("change", update);
    }
    // Safari <14 fallback
    media.addListener(update);
    return () => media.removeListener(update);
  }, [appearance]);

  // Reflect preferences on <html> so global CSS variables pick them up.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", effectiveTheme);
  }, [effectiveTheme]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-density", density);
  }, [density]);

  const value = useMemo<PreferencesContextValue>(
    () => ({
      appearance,
      effectiveTheme,
      density,
      setAppearance,
      setDensity,
    }),
    [appearance, effectiveTheme, density, setAppearance, setDensity],
  );

  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
}

export function usePreferences(): PreferencesContextValue {
  const ctx = useContext(PreferencesContext);
  if (!ctx) {
    throw new Error(
      "usePreferences must be used inside <PreferencesProvider>",
    );
  }
  return ctx;
}
