import type {CatalogObject, ObjectSelection} from '@/types/sqlReview';

/**
 * A run has no object limit (sql-review object-review Requirement 3, Decision 3). This is only the
 * technical bound of one request body, mirrored from the backend contract; it is not a product
 * limit and is far above a selection anyone reviews in one run.
 */
export const SELECTION_TECHNICAL_LIMIT = 10_000;

export const OBJECT_TYPES: Array<{code: string; label: string}> = [
  {code: 'P', label: 'Saklı yordam (P)'},
  {code: 'V', label: 'Görünüm (V)'},
  {code: 'FN', label: 'Skaler fonksiyon (FN)'},
  {code: 'IF', label: 'Satır içi tablo fonksiyonu (IF)'},
  {code: 'TF', label: 'Tablo fonksiyonu (TF)'},
  {code: 'SF', label: 'Fonksiyon (SF)'},
];

export type SelectionMap = Record<string, ObjectSelection>;

export function selectionKey(database: string, object: Pick<CatalogObject, 'schema' | 'name' | 'type_code'>): string {
  return [database, object.schema, object.name, object.type_code].join('\u001f');
}

export function toSelection(database: string, object: CatalogObject): ObjectSelection {
  return {database, schema: object.schema, name: object.name, type_code: object.type_code};
}

/** Add or remove one object. */
export function toggleSelection(
  selection: SelectionMap,
  database: string,
  object: CatalogObject,
  selected: boolean,
): SelectionMap {
  const key = selectionKey(database, object);
  if (!selected) {
    const next = {...selection};
    delete next[key];
    return next;
  }
  if (key in selection) return selection;
  return {...selection, [key]: toSelection(database, object)};
}

/** Add every given object in one copy; thousands of objects stay cheap. */
export function addSelections(selection: SelectionMap, database: string, objects: CatalogObject[]): SelectionMap {
  const next = {...selection};
  for (const object of objects) next[selectionKey(database, object)] = toSelection(database, object);
  return next;
}

/** Select or clear every listed object. */
export function toggleAll(
  selection: SelectionMap,
  database: string,
  objects: CatalogObject[],
  selected: boolean,
): SelectionMap {
  if (selected) return addSelections(selection, database, objects);
  const next = {...selection};
  for (const object of objects) delete next[selectionKey(database, object)];
  return next;
}

export function databaseCount(selection: SelectionMap): number {
  return new Set(Object.values(selection).map((item) => item.database)).size;
}
