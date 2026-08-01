/**
 * Minimal CSV handling for the bulk-issuing flows.
 *
 * Not a general-purpose parser — no embedded commas/quoted-newline support —
 * because the only input here is a template we generate ourselves. A real
 * dependency (papaparse) is the right call once bulk issuing accepts
 * arbitrary registrar exports; that is a backend-integration concern, not a
 * frontend-scaffolding one.
 */

export function parseCsv(text: string): Record<string, string>[] {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length < 2) return [];

  const headers = lines[0]!.split(",").map((h) => h.trim().toLowerCase());
  return lines.slice(1).map((line) => {
    const cells = line.split(",").map((c) => c.trim().replace(/^"|"$/g, ""));
    const row: Record<string, string> = {};
    headers.forEach((header, i) => {
      row[header] = cells[i] ?? "";
    });
    return row;
  });
}

export function downloadTextFile(filename: string, content: string, mime = "text/csv") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const isValidEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

export function validateRow(
  row: Record<string, string>,
  requiredFields: readonly string[],
): string[] {
  const errors: string[] = [];
  for (const field of requiredFields) {
    if (!row[field]) errors.push(`Missing ${field}`);
  }
  if (row.email && !isValidEmail(row.email)) errors.push("Invalid email");
  return errors;
}
