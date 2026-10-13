/**
 * Small, safe Markdown renderer for server-written reports (S22 P5: the
 * forecast-model dry-run report). Supports exactly what those reports use:
 * `#`/`##`/`###` headings, paragraphs, `- ` bullets, pipe tables (header row
 * + `|---|` separator), **bold** and `code`. Raw HTML is never interpreted —
 * every string lands in the DOM as text through React.
 */

import { Fragment, type ReactNode } from "react";
import { cn } from "../lib/cn";

export type MarkdownBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] };

const SEPARATOR = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function isTableLine(line: string): boolean {
  const t = line.trim();
  return t.startsWith("|") && t.endsWith("|") && t.length > 1;
}

function splitCells(line: string): string[] {
  const t = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return t.split("|").map((cell) => cell.trim());
}

/** Block-level parse; exported so the component stays a thin renderer. */
export function parseMarkdown(source: string): MarkdownBlock[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === "") {
      i += 1;
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(trimmed);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2].trim() });
      i += 1;
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ kind: "list", items });
      continue;
    }
    if (isTableLine(line) && i + 1 < lines.length && SEPARATOR.test(lines[i + 1])) {
      const header = splitCells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableLine(lines[i])) {
        rows.push(splitCells(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length) {
      const t = lines[i].trim();
      if (t === "" || /^(#{1,3})\s+/.test(t) || /^[-*]\s+/.test(t) || (isTableLine(lines[i]) && i + 1 < lines.length && SEPARATOR.test(lines[i + 1]))) break;
      para.push(t);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: para.join(" ") });
  }
  return blocks;
}

/** Inline **bold** and `code`; everything else is literal text. */
export function renderInline(text: string): ReactNode {
  const parts: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(<Fragment key={key++}>{text.slice(last, match.index)}</Fragment>);
    const token = match[0];
    if (token.startsWith("**")) parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    else parts.push(<code key={key++} className="rounded-control bg-surface-sunken px-1 font-mono text-[0.92em]">{token.slice(1, -1)}</code>);
    last = match.index + token.length;
  }
  if (last < text.length) parts.push(<Fragment key={key++}>{text.slice(last)}</Fragment>);
  return parts.length === 1 ? parts[0] : parts;
}

export function Markdown({ source, className }: { source: string; className?: string }) {
  const blocks = parseMarkdown(source);
  return (
    <div className={cn("flex flex-col gap-3 text-body text-text", className)}>
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "heading": {
            const Tag = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
            const size = block.level === 1 ? "text-section font-semibold" : block.level === 2 ? "text-body font-semibold" : "text-body font-medium";
            return (
              <Tag key={index} className={cn(size, "mt-1 text-text")}>
                {renderInline(block.text)}
              </Tag>
            );
          }
          case "list":
            return (
              <ul key={index} className="list-disc pl-5">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInline(item)}</li>
                ))}
              </ul>
            );
          case "table":
            return (
              <div key={index} className="overflow-x-auto rounded-card border border-divider">
                <table className="w-full border-collapse text-table [&_tbody_tr]:border-t [&_tbody_tr]:border-divider">
                  <thead>
                    <tr>
                      {block.header.map((cell, cellIndex) => (
                        <th key={cellIndex} className="bg-surface-sunken px-3 py-2 text-left text-label uppercase tracking-wide text-text-secondary whitespace-nowrap border-b border-divider">
                          {renderInline(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {block.header.map((_, cellIndex) => (
                          <td key={cellIndex} className="px-3 py-2 whitespace-nowrap tnum">
                            {renderInline(row[cellIndex] ?? "")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return <p key={index}>{renderInline(block.text)}</p>;
        }
      })}
    </div>
  );
}
