type TaxYearRow = { tax_year: string };

export function latestTaxYear(rows: TaxYearRow[]): string | null {
  if (rows.length === 0) return null;
  return rows.reduce(
    (latest, row) => (row.tax_year > latest ? row.tax_year : latest),
    rows[0].tax_year,
  );
}

export function selectTaxYear<T extends TaxYearRow>(
  rows: T[],
  selectedTaxYear: string | null,
): T | null {
  const selected = rows.find((row) => row.tax_year === selectedTaxYear);
  if (selected) return selected;
  const latest = latestTaxYear(rows);
  return rows.find((row) => row.tax_year === latest) ?? null;
}
