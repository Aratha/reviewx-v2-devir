import type {AuthenticatedUser} from '@/types/auth';

export const ROLE_REVIEWER = 'inceleyici';
export const ROLE_RULE_MANAGER = 'kural-yoneticisi';

/** What the navigation offers to the signed-in user. It never replaces backend authorization. */
export interface Access {
  /** inceleyici or kural-yoneticisi (the super admin passes every role check on the backend). */
  review: boolean;
  /** kural-yoneticisi: rules, connection settings and LLM call summaries. */
  manageRules: boolean;
  /** Application super admin: user administration. */
  administerUsers: boolean;
}

export type AccessRequirement = keyof Access;

export function accessOf(user: AuthenticatedUser | null): Access {
  if (user === null) return {review: false, manageRules: false, administerUsers: false};
  const superAdmin = Boolean(user.is_super_admin);
  const ruleManager = user.role === ROLE_RULE_MANAGER;
  return {
    review: superAdmin || ruleManager || user.role === ROLE_REVIEWER,
    manageRules: superAdmin || ruleManager,
    administerUsers: superAdmin,
  };
}

export function roleLabel(role: string | null | undefined): string {
  if (role === ROLE_RULE_MANAGER) return 'Kural yöneticisi';
  if (role === ROLE_REVIEWER) return 'İnceleyici';
  return 'Rol yok';
}
