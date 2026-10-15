// Route is intentionally pre-registered for generated routes.
import { Route } from "react-router";
// PermissionRoute is intentionally pre-registered for generated protected routes.
import { PermissionRoute } from "@/components/auth/PermissionRoute";
import { RoleRoute } from "@/components/auth/RoleRoute";
import { LibraryHub, MovedTo, ReviewHub } from "@/components/layout/Hubs";
import {
  AdminPage,
  ObjectReviewPage,
  PublishedRulesPage,
  RuleProposalsPage,
  ScheduledReviewsPage,
  ScriptReviewPage,
  ReviewHistoryPage,
} from "@/generated/lazyPages";
// kt-scaffold:imports

void Route;
void PermissionRoute;

/**
 * sql-review and application-foundation pages; the backend authorizes every request. Reviews
 * share "İnceleme", rules for readers share "Kural kitaplığı" and every administration screen
 * lives on the single Yönetim page.
 */
export const GeneratedRoutes = (
  <>
    {/* kt-scaffold:routes */}
    <Route path="/inceleme" element={<RoleRoute require="review"><ReviewHub><ObjectReviewPage /></ReviewHub></RoleRoute>} />
    <Route path="/sql-inceleme" element={<RoleRoute require="review"><ReviewHub><ScriptReviewPage /></ReviewHub></RoleRoute>} />
    <Route
      path="/zamanlanmis-incelemeler"
      element={<RoleRoute require="review"><ReviewHub><ScheduledReviewsPage /></ReviewHub></RoleRoute>}
    />
    <Route path="/gecmis" element={<RoleRoute require="review"><ReviewHistoryPage /></RoleRoute>} />
    <Route
      path="/yayimlanmis-kurallar"
      element={<RoleRoute require="review"><LibraryHub><PublishedRulesPage /></LibraryHub></RoleRoute>}
    />
    <Route
      path="/kural-onerilerim"
      element={<RoleRoute require="review"><LibraryHub><RuleProposalsPage /></LibraryHub></RoleRoute>}
    />
    <Route path="/yonetim" element={<AdminPage />} />
    <Route path="/yonetim/:section" element={<AdminPage />} />
    <Route path="/kurallar" element={<MovedTo section="kurallar" />} />
    <Route path="/kural-onaylari" element={<MovedTo section="onaylar" />} />
    <Route path="/ayarlar/sql" element={<MovedTo section="sql" />} />
    <Route path="/ayarlar/llm" element={<MovedTo section="llm" />} />
    <Route path="/llm-cagrilari" element={<MovedTo section="llm-cagrilari" />} />
    <Route path="/ayarlar/zamanlama" element={<MovedTo section="zamanlama" />} />
    <Route path="/kullanicilar" element={<MovedTo section="kullanicilar" />} />
  </>
);
