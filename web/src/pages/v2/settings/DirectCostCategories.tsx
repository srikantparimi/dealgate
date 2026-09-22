import { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { getDirectCostCategories, saveDirectCostCategories } from "../../../api/client";
import { useAuth } from "../../../auth/AuthProvider";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";

export function DirectCostCategories() {
  const { user } = useAuth();
  const editable = user?.groups.some((group) => ["Finance", "SystemAdmin"].includes(group)) ?? false;
  const [categories, setCategories] = useState<string[] | null>(null);
  const [savedCategories, setSavedCategories] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    getDirectCostCategories().then((data) => {
      if (active) {
        setCategories(data.categories);
        setSavedCategories(data.categories);
        setError(null);
      }
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Could not load categories");
    });
    return () => { active = false; };
  }, [attempt]);

  const valid = categories !== null && categories.length > 0 &&
    categories.every((category) => category.trim().length > 0) &&
    new Set(categories.map((category) => category.trim().toLowerCase())).size === categories.length;
  const changed = JSON.stringify(categories) !== JSON.stringify(savedCategories);

  function edit(next: string[]) {
    setCategories(next);
    setSaved(false);
  }

  async function save() {
    if (!categories || !valid) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const data = await saveDirectCostCategories(categories.map((category) => category.trim()));
      setCategories(data.categories);
      setSavedCategories(data.categories);
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save categories");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="direct-cost-categories-heading" className="flex flex-col gap-3 border-t border-divider pt-6">
      <h2 id="direct-cost-categories-heading" className="text-section text-text">Direct-cost categories</h2>
      {categories ? (
        <form className="flex max-w-lg flex-col gap-3" onSubmit={(event) => { event.preventDefault(); void save(); }}>
          <ul className="flex flex-col gap-2">
            {categories.map((category, index) => (
              <li key={index} className="flex items-center gap-2">
                <Input
                  aria-label={`Category ${index + 1}`}
                  value={category}
                  maxLength={32}
                  required
                  disabled={!editable || saving}
                  onChange={(event) => edit(categories.map((value, i) => i === index ? event.target.value : value))}
                />
                {editable && (
                  <Button type="button" variant="tertiary" size="sm" aria-label={`Remove category ${index + 1}`}
                    title={`Remove ${category || "category"}`} disabled={saving || categories.length === 1}
                    onClick={() => edit(categories.filter((_, i) => i !== index))}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {editable && <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" disabled={saving || categories.length >= 50}
              onClick={() => edit([...categories, ""])}>
              <Plus className="h-4 w-4" aria-hidden /> Add category
            </Button>
            <Button type="submit" size="sm" disabled={saving || !valid || !changed}>
              <Save className="h-4 w-4" aria-hidden /> {saving ? "Saving..." : "Save categories"}
            </Button>
          </div>}
        </form>
      ) : error ? (
        <Button variant="secondary" size="sm" className="self-start" onClick={() => setAttempt(attempt + 1)}>Retry</Button>
      ) : <p className="text-secondary text-text-secondary">Loading categories...</p>}
      {error && <p role="alert" className="text-secondary text-danger">{error}</p>}
      {saved && <p role="status" className="text-secondary text-text-secondary">Categories saved</p>}
    </section>
  );
}
