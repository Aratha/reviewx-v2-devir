import {formatDateTime} from '@/lib/format';
import {selectionKey, type SelectionMap} from '@/lib/objectSelection';
import type {CatalogObject} from '@/types/sqlReview';

/**
 * Objects of one database with a checkbox per row. The checkbox is the keyboard-accessible primary
 * action; clicking anywhere on the row toggles it too. The header checkbox selects the listed page
 * only (sql-review object-review Requirement 3).
 */
export function ObjectTable({
  database,
  objects,
  selection,
  onToggle,
  onToggleAll,
}: {
  database: string;
  objects: CatalogObject[];
  selection: SelectionMap;
  onToggle: (object: CatalogObject, selected: boolean) => void;
  onToggleAll: (objects: CatalogObject[], selected: boolean) => void;
}) {
  const allSelected = objects.length > 0 && objects.every((object) => selectionKey(database, object) in selection);
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{database} veritabanındaki nesneler</caption>
        <thead>
          <tr>
            <th scope="col" className="cell-check">
              <input
                type="checkbox"
                checked={allSelected}
                disabled={objects.length === 0}
                aria-label="Görünen nesnelerin tümünü seç"
                onChange={(event) => onToggleAll(objects, event.target.checked)}
              />
            </th>
            <th scope="col">Şema</th>
            <th scope="col">Ad</th>
            <th scope="col">Tür</th>
            <th scope="col">Oluşturulma</th>
            <th scope="col">Son değişiklik</th>
          </tr>
        </thead>
        <tbody>
          {objects.map((object) => {
            const key = selectionKey(database, object);
            const checked = key in selection;
            return (
              <tr
                key={key}
                className={`is-clickable${checked ? ' is-selected' : ''}`}
                onClick={() => onToggle(object, !checked)}
              >
                <td className="cell-check">
                  <input
                    type="checkbox"
                    checked={checked}
                    aria-label={`${object.schema}.${object.name} seç`}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => onToggle(object, event.target.checked)}
                  />
                </td>
                <td className="mono subtle">{object.schema}</td>
                <td>
                  <strong>{object.name}</strong>
                </td>
                <td>
                  <span className="mono">{object.type_code}</span> <span className="subtle">{object.type}</span>
                </td>
                <td className="nowrap">{formatDateTime(object.created_at)}</td>
                <td className="nowrap">{formatDateTime(object.last_modified)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
