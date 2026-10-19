// S24-AG1 F2/B5 · the browser's copy of api/app/services/agreement_files.py: the same checks in the
// same order (extension, empty, size, first bytes), the same messages, and the same stored name. The
// server re-checks every upload and its answer wins; this only spares a round trip and shows
// "Will be stored as …" before anything is sent. The browser's MIME type is never trusted.

export const MAX_BYTES = 25 * 1024 * 1024; // 25 MiB, as agreement_files.MAX_BYTES
export const MAX_STORED_BASE = 80;
export const MAX_DISPLAY_NAME = 255;
export const ACCEPTED_EXTENSIONS: readonly string[] = [".pdf", ".docx"];

export type AgreementExt = "pdf" | "docx";

// The wording is the server's (and the prototype's).
export const MSG_TYPE = "Only PDF and Word (.docx) files can be uploaded.";
export const MSG_TOO_LARGE = "This file is larger than 25 MB.";
export const MSG_EMPTY = "This file is empty.";
export const MSG_NOT_PDF = "This file is named .pdf but its contents are not a PDF.";
export const MSG_NOT_DOCX = "This file is named .docx but its contents are not a Word document.";
/** Browser only: the file could not be read to check its first bytes (prototype wording). */
export const MSG_UNREADABLE = "This file could not be read.";

const MAGIC: Record<AgreementExt, readonly number[]> = {
  pdf: [0x25, 0x50, 0x44, 0x46, 0x2d], // %PDF-
  docx: [0x50, 0x4b, 0x03, 0x04], // PK 03 04
};

// Python's `$` also matches just before one final newline; the look-ahead keeps that behaviour.
const EXT = /\.([A-Za-z0-9]+)(?=\n?$)/;
const KNOWN_TAIL = /(\.(pdf|docx))+(?=\n?$)/i;
const UNSAFE = /[^A-Za-z0-9._\- ]+/g;
// Python's \s (str.isspace): JavaScript's \s plus the four information separators and NEL. The BOM, which
// only JavaScript counts, is a format character and is gone before this runs.
// eslint-disable-next-line no-control-regex
const SPACES = /[\s\x1c-\x1f\x85]+/g;
// eslint-disable-next-line no-control-regex
const TRAILING_GAP = /[\s\x1c-\x1f\x85.]+$/;
// Invisible characters can disguise a name on screen: every control (C0 and C1), format character (bidi
// marks and overrides including U+061C, zero-width characters, the BOM) and line or paragraph separator.
// Separators become a space; whitespace controls stay whitespace (agreement_files._visible).
const HIDDEN_CHAR = /[\p{Cc}\p{Cf}]/u;
const SEPARATOR_CHAR = /[\p{Zl}\p{Zp}]/u;
// eslint-disable-next-line no-control-regex
const SPACE_CONTROL = /[\t\n\x0b\x0c\r\x1c-\x1f\x85]/;

function visible(text: string): string {
  let out = "";
  for (const ch of text) {
    if (SEPARATOR_CHAR.test(ch)) out += " ";
    else if (SPACE_CONTROL.test(ch) || !HIDDEN_CHAR.test(ch)) out += ch;
  }
  return out;
}

/** The last path segment ("..\\a/b.pdf" → "b.pdf"). */
export function lastSegment(name: string | null | undefined): string {
  const parts = (name ?? "").split(/[\\/]/);
  return parts[parts.length - 1] ?? "";
}

/** Lower-case extension of the last path segment, or "" when there is none. */
export function extensionOf(name: string | null | undefined): string {
  const match = EXT.exec(lastSegment(name));
  return match ? match[1]!.toLowerCase() : "";
}

export function isAcceptedExtension(ext: string): ext is AgreementExt {
  return ext === "pdf" || ext === "docx";
}

function stripSpaceDot(value: string): string {
  return value.replace(/^[ .]+/, "").replace(/[ .]+$/, "");
}

/**
 * The sanitised object name, exactly as agreement_files.stored_name: letters, digits, dot, dash,
 * underscore and space; at most 80 characters before exactly one extension ("x.pdf.pdf" → "x.pdf").
 */
export function storedName(original: string | null | undefined, ext: string): string {
  const name = visible(lastSegment(original));
  const match = EXT.exec(name);
  let base = match ? name.slice(0, name.length - match[0].length) : name;
  // Strip every trailing known extension, also when a space or a dot separates them ("x.pdf .pdf",
  // "x.pdf..pdf", "Acme.docx .pdf"), so exactly one extension remains.
  for (;;) {
    const previous = base;
    base = base.replace(TRAILING_GAP, "").replace(KNOWN_TAIL, "");
    if (base === previous) break;
  }
  base = base.replace(UNSAFE, "_");
  base = stripSpaceDot(base.replace(SPACES, " "));
  base = stripSpaceDot(base.slice(0, MAX_STORED_BASE)) || "file";
  return `${base}.${ext}`;
}

/** The original name as the server keeps it for display: no path, no hidden characters, whitespace runs as one
 * space, at most 255. */
export function displayName(original: string | null | undefined): string {
  const name = visible(lastSegment(original)).replace(SPACES, " ").trim() || "file";
  const points = Array.from(name);
  if (points.length <= MAX_DISPLAY_NAME) return name;
  const match = EXT.exec(name);
  const tail = match && Array.from(match[0]).length <= 10 ? match[0] : "";
  return points.slice(0, MAX_DISPLAY_NAME - Array.from(tail).length).join("") + tail;
}

/** File size as the prototype writes it: "under 1 KB", "214 KB". */
export function sizeText(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return "size not recorded";
  return bytes < 1000 ? "under 1 KB" : `${Math.round(bytes / 1000)} KB`;
}

export type FileCheck =
  | { ok: true; ext: AgreementExt; storedName: string; displayName: string }
  | { ok: false; message: string };

/** Read the first `count` bytes. FileReader, because jsdom's Blob has no arrayBuffer(). */
function readHead(file: Blob, count: number): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error ?? new Error(MSG_UNREADABLE));
    reader.readAsArrayBuffer(file.slice(0, count));
  });
}

/** Every rule the server applies, in its order (agreement_files.check_bytes). */
export async function checkFile(file: File): Promise<FileCheck> {
  const ext = extensionOf(file.name);
  if (!isAcceptedExtension(ext)) return { ok: false, message: MSG_TYPE };
  if (file.size === 0) return { ok: false, message: MSG_EMPTY };
  if (file.size > MAX_BYTES) return { ok: false, message: MSG_TOO_LARGE };
  const magic = MAGIC[ext];
  let head: Uint8Array;
  try {
    head = await readHead(file, magic.length);
  } catch {
    return { ok: false, message: MSG_UNREADABLE };
  }
  if (head.length < magic.length || !magic.every((byte, i) => head[i] === byte)) {
    return { ok: false, message: ext === "pdf" ? MSG_NOT_PDF : MSG_NOT_DOCX };
  }
  return { ok: true, ext, storedName: storedName(file.name, ext), displayName: displayName(file.name) };
}
