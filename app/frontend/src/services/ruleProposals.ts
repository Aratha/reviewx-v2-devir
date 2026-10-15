import {apiRequest} from '@/lib/apiClient';
import type {
  RuleProposalCapabilities,
  RuleProposalCreate,
  RuleProposalDetail,
  RuleProposalPage,
} from '@/types/sqlReview';

type Scope = 'mine' | 'pending' | 'all';

function post<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, {method: 'POST', body: body === undefined ? undefined : JSON.stringify(body)});
}

/** Rule and group proposals (sql-review rule-proposals); every user proposes, the super admin decides. */
export const RuleProposalService = {
  capabilities(signal?: AbortSignal): Promise<RuleProposalCapabilities> {
    return apiRequest<RuleProposalCapabilities>('/rule-proposals/capabilities', {signal});
  },
  list(scope: Scope, page: number, pageSize: number, signal?: AbortSignal): Promise<RuleProposalPage> {
    return apiRequest<RuleProposalPage>(`/rule-proposals?scope=${scope}&page=${page}&page_size=${pageSize}`, {signal});
  },
  get(id: string, signal?: AbortSignal): Promise<RuleProposalDetail> {
    return apiRequest<RuleProposalDetail>(`/rule-proposals/${encodeURIComponent(id)}`, {signal});
  },
  create(body: RuleProposalCreate): Promise<RuleProposalDetail> {
    return post<RuleProposalDetail>('/rule-proposals', body);
  },
  withdraw(id: string): Promise<RuleProposalDetail> {
    return post<RuleProposalDetail>(`/rule-proposals/${encodeURIComponent(id)}/withdraw`);
  },
  approve(id: string): Promise<RuleProposalDetail> {
    return post<RuleProposalDetail>(`/rule-proposals/${encodeURIComponent(id)}/approve`);
  },
  reject(id: string, reason: string): Promise<RuleProposalDetail> {
    return post<RuleProposalDetail>(`/rule-proposals/${encodeURIComponent(id)}/reject`, {reason});
  },
};
