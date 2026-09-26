import type {CatalogObject, ObjectSelection} from '@/types/sqlReview';

/** At most 50 objects per run (sql-review object-review Requirement 3, Decision 3). */
export const MAX_SELECTION = 50;

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

/** Add or remove one object; adding stops at the limit. */
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
  if (key in selection || Object.keys(selection).length >= MAX_SELECTION) return selection;
  return {...selection, [key]: toSelection(database, object)};
}

/** Select or clear every listed object; selecting adds only as many as the limit allows. */
export function toggleAll(
  selection: SelectionMap,
  database: string,
  objects: CatalogObject[],
  selected: boolean,
): SelectionMap {
  let next = selection;
  for (const object of objects) next = toggleSelection(next, database, object, selected);
  return next;
}

export function databaseCount(selection: SelectionMap): number {
  return new Set(Object.values(selection).map((item) => item.database)).size;
}
