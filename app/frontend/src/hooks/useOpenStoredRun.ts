import {useNavigate} from 'react-router';
import {useReviewSession} from '@/contexts/ReviewSessionContext';

/**
 * Open the stored run on the history page. A run with more objects than one result page is not
 * shown in the results window; its results are read there page by page
 * (sql-review object-review Requirement 14, review-history-export Requirement 3).
 */
export function useOpenStoredRun(): (runId: string) => void {
  const navigate = useNavigate();
  const {closeWindows} = useReviewSession();
  return (runId) => {
    closeWindows();
    void navigate(`/gecmis?run=${encodeURIComponent(runId)}`);
  };
}
