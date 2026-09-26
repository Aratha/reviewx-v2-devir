import type {components} from './api';

/** Aliases over the recorded OpenAPI contract; no request or response shape is restated by hand. */
type Schemas = components['schemas'];

export type UserSummary = Schemas['UserSummary'];
export type UserPage = Schemas['UserPage'];
export type ApplicationRole = Schemas['RoleChange']['role'];

export type RuleItem = Schemas['RuleItem'];
export type RuleSetWorkspace = Schemas['RuleSetWorkspace'];
export type RuleSetDraftUpdate = Schemas['RuleSetDraftUpdate'];
export type RuleSetVersionSummary = Schemas['RuleSetVersionSummary'];
export type RuleSetVersionDetail = Schemas['RuleSetVersionDetail'];
export type RuleSetVersionPage = Schemas['RuleSetVersionPage'];

export type SqlConnectionView = Schemas['SqlConnectionView'];
export type SqlConnectionChange = Schemas['SqlConnectionChange'];
export type SqlConnectionTestResult = Schemas['SqlConnectionTestResult'];
export type LlmConnectionView = Schemas['LlmConnectionView'];
export type LlmConnectionUpdate = Schemas['LlmConnectionUpdate'];
export type LlmChatApi = Schemas['LlmConnectionView']['chat_api'];
export type LlmCallSummary = Schemas['LlmCallSummaryItem'];
export type LlmCallSummaryPage = Schemas['LlmCallSummaryPage'];

export type DatabasePage = Schemas['DatabasePage'];
export type CatalogObject = Schemas['CatalogObjectItem'];
export type CatalogObjectPage = Schemas['CatalogObjectPage'];
export type ObjectSelection = Schemas['ObjectSelectionItem'];

export type ReviewStreamEvent = Schemas['ReviewStreamEvent'];
export type ReviewPhase = NonNullable<ReviewStreamEvent['phase']>;
export type RuleResult = Schemas['RuleResultItem'];
export type Finding = Schemas['FindingItem'];
export type ObjectResult = Schemas['ObjectResultItem'];
export type LiveObjectResult = Schemas['LiveObjectResultItem'];
export type ReviewKind = Schemas['ReviewRunSummary']['kind'];
export type ReviewRunStatus = Schemas['ReviewRunSummary']['status'];
export type ReviewRunSummary = Schemas['ReviewRunSummary'];
export type ReviewRunDetail = Schemas['ReviewRunDetail'];
export type ReviewRunPage = Schemas['ReviewRunPage'];
export type FalsePositiveState = Schemas['FalsePositiveState'];
export type DeletedRuns = Schemas['DeletedRuns'];
