// S24-AG1 T14 · docs/bugs #109: a toast raised from inside an open drawer is the newest Radix layer, so Escape
// used to dismiss the toast and leave the drawer open. The kit's sheet and dialog now hand Escape back to
// themselves while a toast opened after them is on screen, through their own guards and close control.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Dialog, DialogContent, DialogTitle } from "../../ui-v2/primitives/dialog";
import { Sheet, SheetContent, SheetTitle } from "../../ui-v2/primitives/sheet";
import { Toaster, useToast } from "../../ui-v2/primitives/toaster";

function DrawerWithToast({
  busy = false,
  kind = "sheet",
  onOpenChange,
}: {
  busy?: boolean;
  kind?: "sheet" | "dialog";
  onOpenChange?: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(true);
  const { toast } = useToast();
  const change = (next: boolean) => {
    onOpenChange?.(next);
    if (!next && busy) return;
    setOpen(next);
  };
  const body = (
    <>
      <button type="button" onClick={() => toast({ title: "A download link was created." })}>
        Download
      </button>
    </>
  );
  const guard = (event: KeyboardEvent) => {
    if (busy) event.preventDefault();
  };
  return kind === "sheet" ? (
    <Sheet open={open} onOpenChange={change}>
      <SheetContent aria-describedby={undefined} onEscapeKeyDown={guard}>
        <SheetTitle>Client panel</SheetTitle>
        {body}
      </SheetContent>
    </Sheet>
  ) : (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent aria-describedby={undefined} onEscapeKeyDown={guard}>
        <DialogTitle>Client panel</DialogTitle>
        {body}
      </DialogContent>
    </Dialog>
  );
}

function renderDrawer(props: Parameters<typeof DrawerWithToast>[0] = {}) {
  return render(
    <Toaster>
      <DrawerWithToast {...props} />
    </Toaster>,
  );
}

async function raiseToast() {
  const download = screen.getByRole("button", { name: "Download" });
  download.focus();
  fireEvent.click(download);
  await screen.findByText("A download link was created.");
  return download;
}

describe("Escape with a toast on screen (kit sheet and dialog)", () => {
  it.each(["sheet", "dialog"] as const)("one Escape closes the %s that has focus; the toast stays", async (kind) => {
    renderDrawer({ kind });
    const download = await raiseToast();
    fireEvent.keyDown(download, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Client panel" })).toBeNull());
    expect(screen.getByText("A download link was created.")).toBeInTheDocument();
  });

  it("without a toast, Escape closes the drawer as before (Radix alone, once)", async () => {
    const onOpenChange = vi.fn();
    renderDrawer({ onOpenChange });
    const download = screen.getByRole("button", { name: "Download" });
    download.focus();
    fireEvent.keyDown(download, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Client panel" })).toBeNull());
    expect(onOpenChange).toHaveBeenCalledTimes(1);
  });

  it("a busy drawer's own guard still decides: it stays open", async () => {
    renderDrawer({ busy: true });
    const download = await raiseToast();
    fireEvent.keyDown(download, { key: "Escape" });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByRole("dialog", { name: "Client panel" })).toBeInTheDocument();
  });

  it("a toast opened before the drawer leaves Escape to Radix: the drawer closes once, not twice", async () => {
    const onOpenChange = vi.fn();
    function Sequence() {
      const { toast } = useToast();
      const [shown, setShown] = useState(false);
      return (
        <>
          <button
            type="button"
            onClick={() => {
              toast({ title: "Saved earlier." });
              setShown(true);
            }}
          >
            Earlier action
          </button>
          {shown ? <DrawerWithToast onOpenChange={onOpenChange} /> : null}
        </>
      );
    }
    render(
      <Toaster>
        <Sequence />
      </Toaster>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Earlier action" }));
    await screen.findByText("Saved earlier.");
    const download = await screen.findByRole("button", { name: "Download" });
    download.focus();
    fireEvent.keyDown(download, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Client panel" })).toBeNull());
    expect(onOpenChange).toHaveBeenCalledTimes(1);
  });
});
