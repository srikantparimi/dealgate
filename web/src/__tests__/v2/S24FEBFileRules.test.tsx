// S24-AG1 F2/B5/T3 · the browser's file rules mirror api/app/services/agreement_files.py exactly: the
// same checks in the same order with the same messages, and the same stored name. The stored-name table
// below is the server's own output (api/tests/test_s24_ag1_feb_stored_name.py runs it against
// agreement_files.stored_name), so the two cannot drift silently. Also covers the reworked FileDropzone.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";

import {
  MAX_BYTES,
  MSG_EMPTY,
  MSG_NOT_DOCX,
  MSG_NOT_PDF,
  MSG_TOO_LARGE,
  MSG_TYPE,
  checkFile,
  displayName,
  extensionOf,
  sizeText,
  storedName,
} from "../../pages/v2/agreements/fileRules";
import { FileDropzone } from "../../ui/FileDropzone";

/** [original name, extension the server derives, stored name the server writes]. */
export const STORED_NAME_VECTORS: [string, string, string][] = [
  ["Contract.pdf", "pdf", "Contract.pdf"],
  ["x.pdf.pdf", "pdf", "x.pdf"],
  ["x.docx.pdf", "pdf", "x.pdf"],
  ["X.PDF", "pdf", "X.pdf"],
  ["x.PDF.Pdf", "pdf", "x.pdf"],
  ["..\\a/b.pdf", "pdf", "b.pdf"],
  ["C:\\Users\\me\\NDA final.docx", "docx", "NDA final.docx"],
  ["<img src=x onerror=alert(1)>.pdf", "pdf", "_img src_x onerror_alert_1_.pdf"],
  [`${"a".repeat(90)}.pdf`, "pdf", `${"a".repeat(80)}.pdf`],
  [`${"a".repeat(79)} ${"b".repeat(10)}.pdf`, "pdf", `${"a".repeat(79)}.pdf`],
  ["...hidden.pdf", "pdf", "hidden.pdf"],
  ["  spaced   name  .pdf", "pdf", "spaced name.pdf"],
  ["Acme\u2019s NDA (v2).pdf", "pdf", "Acme_s NDA _v2_.pdf"],
  ["r\u00e9sum\u00e9.docx", "docx", "r_sum_.docx"],
  [".pdf", "pdf", "file.pdf"],
  ["report.pdf\n", "pdf", "report.pdf"],
  ["\u{1F600} emoji.pdf", "pdf", "_ emoji.pdf"],
  ["a.b.c.pdf", "pdf", "a.b.c.pdf"],
  ["trailing dots....docx", "docx", "trailing dots.docx"],
  ["tab\tname.pdf", "pdf", "tab_name.pdf"],
  ["x.pdf.docx", "docx", "x.docx"],
  // Review finding: a gap between repeated extensions, and invisible characters (C0, C1, U+061C, zero-width,
  // BOM, line separator) in the stored name.
  ["x.pdf .pdf", "pdf", "x.pdf"],
  ["x.docx .pdf", "pdf", "x.pdf"],
  ["x.pdf..pdf", "pdf", "x.pdf"],
  ["Acme_MSA.docx .pdf", "pdf", "Acme_MSA.pdf"],
  ["x.pdf\t.pdf", "pdf", "x.pdf"],
  ["x .PDF. .pdf", "pdf", "x.pdf"],
  ["a\u0085b.pdf", "pdf", "a_b.pdf"],
  ["a\u0080b.pdf", "pdf", "ab.pdf"],
  ["a\u061cb.pdf", "pdf", "ab.pdf"],
  ["a\u2028b.pdf", "pdf", "a b.pdf"],
  ["x\u200b.pdf", "pdf", "x.pdf"],
  ["a\u00a0\u00a0b.pdf", "pdf", "a_b.pdf"],
  ["a\u001fb.pdf", "pdf", "a_b.pdf"],
  ["\ufeffbom.pdf", "pdf", "bom.pdf"],
];

function pdf(name: string, body = "%PDF-1.7\n1 0 obj\n"): File {
  return new File([body], name, { type: "application/pdf" });
}

function sized(file: File, size: number): File {
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("stored name (agreement_files.stored_name)", () => {
  it.each(STORED_NAME_VECTORS)("%j is stored as the server stores it", (name, ext, expected) => {
    expect(extensionOf(name)).toBe(ext);
    expect(storedName(name, ext)).toBe(expected);
  });

  it("falls back to file.pdf for an empty name", () => {
    expect(extensionOf("")).toBe("");
    expect(storedName("", "pdf")).toBe("file.pdf");
  });

  it("keeps the original name for display without the path or hidden characters", () => {
    expect(displayName("..\\a/b.pdf")).toBe("b.pdf");
    expect(displayName("tab\tname.pdf")).toBe("tab name.pdf"); // whitespace keeps words apart
    expect(displayName("a\u0085b.pdf")).toBe("a b.pdf");
    expect(displayName("a\u0080b.pdf")).toBe("ab.pdf");
    expect(displayName("a\u061cb.pdf")).toBe("ab.pdf");
    expect(displayName("a\u2028b.pdf")).toBe("a b.pdf");
    expect(displayName("\ufeffbom.pdf")).toBe("bom.pdf");
    expect(displayName("x.pdf .pdf")).toBe("x.pdf .pdf");
    expect(displayName("report.pdf\n")).toBe("report.pdf");
    expect(displayName("\u202eevil\u202c.pdf")).toBe("evil.pdf");
    expect(displayName("")).toBe("file");
    const long = displayName(`${"n".repeat(300)}.pdf`);
    expect(long).toHaveLength(255);
    expect(long.endsWith(".pdf")).toBe(true);
  });

  it("writes sizes as the prototype does", () => {
    expect(sizeText(999)).toBe("under 1 KB");
    expect(sizeText(214000)).toBe("214 KB");
    expect(sizeText(null)).toBe("size not recorded");
  });
});

describe("checkFile: the server's checks, in its order, with its messages", () => {
  it("accepts a real PDF and a real DOCX, whatever the browser says the type is", async () => {
    await expect(checkFile(pdf("x.pdf.pdf"))).resolves.toEqual({
      ok: true,
      ext: "pdf",
      storedName: "x.pdf",
      displayName: "x.pdf.pdf",
    });
    const docx = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00])], "Plan.DOCX", { type: "text/plain" });
    await expect(checkFile(docx)).resolves.toMatchObject({ ok: true, ext: "docx", storedName: "Plan.docx" });
  });

  it("refuses a name that is not .pdf or .docx", async () => {
    await expect(checkFile(pdf("notes.txt"))).resolves.toEqual({ ok: false, message: MSG_TYPE });
    await expect(checkFile(pdf("x.pdf.exe"))).resolves.toEqual({ ok: false, message: MSG_TYPE });
    await expect(checkFile(pdf("no-extension"))).resolves.toEqual({ ok: false, message: MSG_TYPE });
  });

  it("refuses an empty file and one over 25 MiB; exactly 25 MiB passes the size check", async () => {
    await expect(checkFile(new File([], "empty.pdf"))).resolves.toEqual({ ok: false, message: MSG_EMPTY });
    await expect(checkFile(sized(pdf("big.pdf"), 26 * 1024 * 1024))).resolves.toEqual({
      ok: false,
      message: MSG_TOO_LARGE,
    });
    // The directive's cap pinned to a literal, not only the module's constant; one byte more is refused.
    expect(MAX_BYTES).toBe(25 * 1024 * 1024);
    await expect(checkFile(sized(pdf("edge.pdf"), 25 * 1024 * 1024))).resolves.toMatchObject({ ok: true });
    await expect(checkFile(sized(pdf("edge-plus-one.pdf"), 25 * 1024 * 1024 + 1))).resolves.toEqual({
      ok: false,
      message: MSG_TOO_LARGE,
    });
  });

  it("checks the first bytes: a text file named .pdf, a fake .docx, and a PDF header without its dash", async () => {
    await expect(checkFile(pdf("fake.pdf", "hello, not a pdf"))).resolves.toEqual({ ok: false, message: MSG_NOT_PDF });
    await expect(checkFile(pdf("fake.docx"))).resolves.toEqual({ ok: false, message: MSG_NOT_DOCX });
    await expect(checkFile(pdf("short.pdf", "%PDF"))).resolves.toEqual({ ok: false, message: MSG_NOT_PDF });
  });
});

describe("FileDropzone (D12: adopted, keyboard operable, tokens only)", () => {
  function mount(validate?: (file: File) => Promise<string | null>) {
    const onFile = vi.fn();
    render(
      <FileDropzone
        accept={[".pdf", ".docx"]}
        label="PDF or Word (.docx), up to 25 MB"
        typeMessage={MSG_TYPE}
        validate={validate}
        describe={(file) => `${file.name} · ${sizeText(file.size)}`}
        onFile={onFile}
      />,
    );
    return { onFile, input: screen.getByLabelText("Choose a file") as HTMLInputElement };
  }

  it("keeps the file input in the tab order with an accessible name and an extension accept list", () => {
    const { input } = mount();
    expect(input.type).toBe("file");
    expect(input.tabIndex).toBe(0);
    expect(input).toHaveAttribute("accept", ".pdf,.docx");
    expect(input.className).toContain("sr-only");
    expect(input.closest("label")).not.toBeNull();
    expect(screen.getByText("PDF or Word (.docx), up to 25 MB")).toBeInTheDocument();
  });

  it("refuses a wrong extension without trusting the MIME type, and says why in an alert", async () => {
    const { onFile, input } = mount();
    fireEvent.change(input, { target: { files: [new File(["%PDF-1.7"], "notes.txt", { type: "application/pdf" })] } });
    expect(await screen.findByRole("alert")).toHaveTextContent(MSG_TYPE);
    expect(onFile).toHaveBeenLastCalledWith(null);
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("runs the async validation, shows the bad state, then the ok state with name and size", async () => {
    const validate = vi.fn(async (file: File) => (file.name.startsWith("bad") ? "This file is empty." : null));
    const { onFile, input } = mount(validate);
    fireEvent.change(input, { target: { files: [pdf("bad.pdf")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("This file is empty.");
    const good = pdf("Signed NDA.pdf");
    fireEvent.change(input, { target: { files: [good] } });
    await waitFor(() => expect(onFile).toHaveBeenLastCalledWith(good));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText(`Signed NDA.pdf · ${sizeText(good.size)}`)).toBeInTheDocument();
  });

  it("accepts a dropped file", async () => {
    const { onFile } = mount(async () => null);
    const zone = screen.getByText("PDF or Word (.docx), up to 25 MB").closest("label")!;
    const file = pdf("dropped.pdf");
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    await waitFor(() => expect(onFile).toHaveBeenLastCalledWith(file));
  });

  it("uses design tokens only (no raw hex), so it follows light and dark", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const source = readFileSync(resolve(here, "../../ui/FileDropzone.tsx"), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");
    expect(source.match(/#[0-9a-fA-F]{3,8}\b/g)).toBeNull();
  });
});
