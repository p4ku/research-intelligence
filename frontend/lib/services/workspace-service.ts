import { apiClient } from '../api/client';

export interface WorkspaceScraper {
  id: string;
  provider: string;
  search_query: string;
  limit: number;
  is_active: boolean;
}

export interface WorkspaceExtractionDefinition {
  id: string;
  name: string;
  llm_model: string;
  is_active: boolean;
}

export interface WorkspaceItem {
  id: string;
  name: string;
  abstract_acceptance_criteria: string;
  abstract_rejection_criteria: string;
  full_text_acceptance_criteria: string;
  full_text_rejection_criteria: string;
  ocr_provider: string | null;
  screening_llm_model: string;
  llm_provider: string;
  digest_schedule: string;
  monthly_token_limit: number;
  tokens_consumed_this_month: number;
  monthly_usd_limit: number;
  usd_spent_this_month: number;
  user_role?: 'admin' | 'manager' | 'researcher' | string | null;
  scrapers: WorkspaceScraper[];

  extraction_definitions: WorkspaceExtractionDefinition[];
  created_at: string;
}

export const workspaceService = {
  async getWorkspaces(): Promise<WorkspaceItem[]> {
    return apiClient<WorkspaceItem[]>('/workspaces/');
  },

  async getWorkspace(id: string): Promise<WorkspaceItem> {
    return apiClient<WorkspaceItem>(`/workspaces/${id}/`);
  },

  async createWorkspace(data: Partial<WorkspaceItem>): Promise<WorkspaceItem> {
    return apiClient<WorkspaceItem>('/workspaces/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
