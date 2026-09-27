import {apiRequest} from '@/lib/apiClient';
import type {CatalogObjectPage, DatabasePage} from '@/types/sqlReview';

export interface ObjectQuery {
  q?: string;
  type?: string;
  fromDate?: string;
  page: number;
  pageSize: number;
}

/** SQL Server catalog lists for the object review page (sql-review object-review API contract). */
export const CatalogService = {
  databases(signal?: AbortSignal): Promise<DatabasePage> {
    return apiRequest<DatabasePage>('/databases?page=1&page_size=500', {signal});
  },
  objects(database: string, query: ObjectQuery, signal?: AbortSignal): Promise<CatalogObjectPage> {
    const params = new URLSearchParams({page: String(query.page), page_size: String(query.pageSize)});
    if (query.q) params.set('q', query.q);
    if (query.type) params.set('type', query.type);
    if (query.fromDate) params.set('from_date', query.fromDate);
    return apiRequest<CatalogObjectPage>(
      `/databases/${encodeURIComponent(database)}/objects?${params.toString()}`,
      {signal},
    );
  },
};
