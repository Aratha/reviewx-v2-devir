import {apiRequest} from '@/lib/apiClient';
import type {ApplicationRole, UserPage, UserSummary} from '@/types/sqlReview';

type RoleResult = {role: ApplicationRole};
type ActiveResult = {active: boolean};

/** Super-admin user administration (application-foundation directory-login Requirement 5). */
export const UserAdminService = {
  list(params: {page: number; size: number; q?: string}): Promise<UserPage> {
    const query = new URLSearchParams({page: String(params.page), size: String(params.size)});
    if (params.q) query.set('q', params.q);
    return apiRequest<UserPage>(`/admin/users?${query.toString()}`);
  },
  setRole(user: Pick<UserSummary, 'public_id'>, role: ApplicationRole): Promise<RoleResult> {
    return apiRequest<RoleResult>(`/admin/users/${encodeURIComponent(user.public_id)}/role`, {
      method: 'PUT',
      body: JSON.stringify({role}),
    });
  },
  setActive(user: Pick<UserSummary, 'public_id'>, active: boolean): Promise<ActiveResult> {
    return apiRequest<ActiveResult>(`/admin/users/${encodeURIComponent(user.public_id)}/active`, {
      method: 'PUT',
      body: JSON.stringify({active}),
    });
  },
};
