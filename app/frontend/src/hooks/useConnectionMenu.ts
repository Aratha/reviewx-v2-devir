import {useResource} from '@/hooks/useResource';
import {ConnectionService} from '@/services/connections';

/**
 * Whether the SQL and LLM connection pages belong in the menu: only for the rule manager and only
 * when the backend reports the settings editable (`local`); in `nonprod` they are hidden
 * (sql-server-connection Requirement 5, llm-connection Requirement 13).
 */
export function useConnectionMenu(enabled: boolean): {sql: boolean; llm: boolean} {
  const sql = useResource(enabled ? 'sql-connection' : null, (signal) => ConnectionService.sql(signal));
  const llm = useResource(enabled ? 'llm-connection' : null, (signal) => ConnectionService.llm(signal));
  return {sql: sql.data?.editable === true, llm: llm.data?.editable === true};
}
