import type {ModeItem} from '@/components/layout/ModeSwitch';
import type {IconName} from '@/components/ui/Icon';

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Address prefixes that belong to this item (it is the current page on any of them). */
  match: string[];
  /** Pending decisions shown next to the label (rule-proposals Requirement 7). */
  count?: number;
}

export type AdminSectionId = 'kurallar' | 'onaylar' | 'sql' | 'llm' | 'llm-cagrilari' | 'zamanlama' | 'kullanicilar';

export interface AdminSection {
  id: AdminSectionId;
  label: string;
  icon: IconName;
  summary: string;
  count?: number;
}

export interface AppNavigation {
  primary: NavItem[];
  /** The three ways to review, under "İnceleme". */
  reviewModes: ModeItem[];
  /** Published rules and, when allowed, the user's proposals, under "Kural kitaplığı". */
  libraryModes: ModeItem[];
  /** What the Yönetim page offers this user; empty when it offers nothing. */
  adminSections: AdminSection[];
  canPropose: boolean;
  pending: number;
}

export const REVIEW_PATHS = ['/inceleme', '/sql-inceleme', '/zamanlanmis-incelemeler'];
export const LIBRARY_PATHS = ['/yayimlanmis-kurallar', '/kural-onerilerim'];

/** Whether `pathname` belongs to `item`; the home item matches only itself. */
export function isCurrent(item: Pick<NavItem, 'match'>, pathname: string): boolean {
  return item.match.some((prefix) =>
    prefix === '/' ? pathname === '/' : pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}
