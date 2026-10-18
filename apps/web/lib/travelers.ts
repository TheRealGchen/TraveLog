/** Parsing for the bulk-add box. Validation happens in the API; this only splits text. */

export interface ParsedTraveler {
  name: string;
  email?: string;
  passportNumber?: string;
}

/**
 * One traveler per non-empty line: `Name, email, passport`. Tabs also separate fields, so rows
 * pasted from a spreadsheet work. Email and passport are optional.
 */
export function parseTravelerLines(text: string): ParsedTraveler[] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => {
      const [name = "", email = "", passportNumber = ""] = line
        .split(line.includes("\t") ? "\t" : ",")
        .map((part) => part.trim());
      return {
        name,
        ...(email ? { email } : {}),
        ...(passportNumber ? { passportNumber } : {}),
      };
    });
}

/**
 * Group API validation errors for `add_travelers` by row, using their `path`
 * (`body.travelers.<row>.<field>`). Errors not tied to a row go under -1.
 */
export function errorsByRow(
  errors: { path: string; message: string }[],
): Map<number, string[]> {
  const rows = new Map<number, string[]>();
  for (const { path, message } of errors) {
    const match = /^body\.travelers\.(\d+)(?:\.(\w+))?/.exec(path);
    const row = match ? Number(match[1]) : -1;
    const field = match?.[2];
    // Prefix the field unless the message already starts with it ("email x is already used").
    const named = field && message.replaceAll(" ", "").toLowerCase().startsWith(field.toLowerCase());
    const text = field && !named ? `${field}: ${message}` : message;
    rows.set(row, [...(rows.get(row) ?? []), text]);
  }
  return rows;
}
