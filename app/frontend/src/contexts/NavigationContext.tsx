import {createContext, useContext, type ReactNode} from 'react';
import {useLocation} from 'react-router';
import {useAuth} from '@/contexts/AuthContext';
import {useConnectionMenu} from '@/hooks/useConnectionMenu';
import {useRuleProposalMenu} from '@/hooks/useRuleProposalMenu';
import {LIBRARY_PATHS, REVIEW_PATHS, type AdminSection, type AppNavigation, type NavItem} from '@/lib/navigation';

const NavigationContext = createContext<AppNavigation | null>(null);

/** Computes the navigation once for the signed-in layout; pages below read it from context. */
export function NavigationProvider({children}: {children: ReactNode}) {
  const navigation = useNavigationModel(true);
  return <NavigationContext.Provider value={navigation}>{children}</NavigationContext.Provider>;
}

/**
 * The role-aware destinations of the application. Hiding a destination is not authorization;
 * every page's data comes from role-checked endpoints.
 */
export function useAppNavigation(): AppNavigation {
  const shared = useContext(NavigationContext);
  const own = useNavigationModel(shared === null);
  return shared ?? own;
}

function useNavigationModel(enabled: boolean): AppNavigation {
  const {access} = useAuth();
  const {pathname} = useLocation();
  const connections = useConnectionMenu(enabled && access.manageRules);
  const proposals = useRuleProposalMenu(enabled && access.review, pathname);

  const adminSections: AdminSection[] = [
    ...(access.manageRules
      ? [{id: 'kurallar' as const, label: 'Kurallar', icon: 'pencil' as const, summary: 'Kural taslağını düzenleyin; yayımlayın ya da onaya gönderin.'}]
      : []),
    ...(proposals.canDecide
      ? [{id: 'onaylar' as const, label: 'Kural onayları', icon: 'inbox' as const, summary: 'Bekleyen kural önerilerine ve yayın isteklerine karar verin.', count: proposals.pending}]
      : []),
    ...(access.manageRules && connections.sql
      ? [{id: 'sql' as const, label: 'SQL bağlantısı', icon: 'plug' as const, summary: 'Nesne listelerinin okunduğu SQL Server bağlantısı.'}]
      : []),
    ...(access.manageRules && connections.llm
      ? [{id: 'llm' as const, label: 'LLM bağlantısı', icon: 'sparkles' as const, summary: 'İncelemelerin gönderildiği kurum içi LLM ucu.'}]
      : []),
    ...(access.manageRules
      ? [{id: 'llm-cagrilari' as const, label: 'LLM çağrıları', icon: 'activity' as const, summary: 'Çağrı özetleri, süreler ve hatalar.'}]
      : []),
    ...(access.administerUsers
      ? [{id: 'zamanlama' as const, label: 'Zamanlama ve e-posta', icon: 'clock' as const, summary: 'Eşzamanlı koşum sınırı, e-posta durumu ve deneme e-postası.'}]
      : []),
    ...(access.administerUsers
      ? [{id: 'kullanicilar' as const, label: 'Kullanıcılar', icon: 'users' as const, summary: 'Roller, hesap durumları ve oturumlar.'}]
      : []),
  ];

  const primary: NavItem[] = [
    {to: '/', label: 'Ana sayfa', icon: 'home', match: ['/']},
    ...(access.review
      ? [
          {to: '/inceleme', label: 'İnceleme', icon: 'database' as const, match: REVIEW_PATHS},
          {to: '/gecmis', label: 'Geçmiş', icon: 'history' as const, match: ['/gecmis']},
          {to: '/yayimlanmis-kurallar', label: 'Kural kitaplığı', icon: 'book' as const, match: LIBRARY_PATHS},
        ]
      : []),
    ...(adminSections.length > 0
      ? [{to: '/yonetim', label: 'Yönetim', icon: 'sliders' as const, match: ['/yonetim'], count: proposals.canDecide ? proposals.pending : undefined}]
      : []),
  ];

  return {
    primary,
    reviewModes: [
      {to: '/inceleme', label: 'Nesneler', icon: 'database'},
      {to: '/sql-inceleme', label: 'SQL betiği', icon: 'code'},
      {to: '/zamanlanmis-incelemeler', label: 'Zamanlanmış', icon: 'clock'},
    ],
    libraryModes: [
      {to: '/yayimlanmis-kurallar', label: 'Yayımlanmış kurallar', icon: 'book'},
      ...(proposals.canPropose ? [{to: '/kural-onerilerim', label: 'Kural önerilerim', icon: 'lightbulb' as const}] : []),
    ],
    adminSections,
    canPropose: proposals.canPropose,
    pending: proposals.pending,
  };
}
