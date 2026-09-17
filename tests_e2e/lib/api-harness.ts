export interface AuthTokens {
  access: string;
  refresh?: string;
  userId?: number;
  username: string;
}

export interface WorkspaceData {
  id: string;
  name: string;
}

export interface PipelineRunData {
  id: string;
  status: string;
  workspace_id: string;
}

export class ApiHarness {
  readonly baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL.replace(/\/+$/, '');
  }

  async login(username: string, password: string): Promise<AuthTokens> {
    const res = await fetch(`${this.baseURL}/api/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      throw new Error(`Login failed (${res.status}): ${await res.text()}`);
    }
    const data = await res.json();
    return {
      access: data.access,
      refresh: data.refresh,
      userId: data.user_id,
      username: data.username,
    };
  }

  async createWorkspace(
    token: string,
    payload: {
      name: string;
      abstract_acceptance_criteria?: string;
      abstract_rejection_criteria?: string;
      full_text_acceptance_criteria?: string;
      full_text_rejection_criteria?: string;
      screening_llm_model?: string;
    },
  ): Promise<WorkspaceData> {
    const res = await fetch(`${this.baseURL}/api/workspaces/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        abstract_acceptance_criteria: 'Accept relevant research papers.',
        abstract_rejection_criteria: 'Reject irrelevant papers.',
        full_text_acceptance_criteria: 'Accept empirical papers.',
        full_text_rejection_criteria: 'Reject pure opinion.',
        screening_llm_model: 'google/gemini-3.8-flash',
        ...payload,
      }),
    });
    if (!res.ok) {
      throw new Error(`Create workspace failed (${res.status}): ${await res.text()}`);
    }
    return await res.json();
  }

  async createScraper(
    token: string,
    payload: {
      workspace: string;
      provider?: string;
      search_query: string;
      limit?: number;
    },
  ): Promise<any> {
    const res = await fetch(`${this.baseURL}/api/scrapers/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        provider: 'arxiv',
        limit: 2,
        ...payload,
      }),
    });
    if (!res.ok) {
      throw new Error(`Create scraper failed (${res.status}): ${await res.text()}`);
    }
    return await res.json();
  }

  async createExtractionDefinition(
    token: string,
    payload: {
      workspace: string;
      name: string;
      system_prompt?: string;
      user_prompt_template?: string;
      response_schema?: any;
      exit_metrics?: string[];
      primary_frontend_metric?: string;
    },
  ): Promise<any> {
    const res = await fetch(`${this.baseURL}/api/extraction-definitions/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        system_prompt: 'Evaluate metric (0-100).',
        user_prompt_template: 'Paper: {{title}}\nAbstract: {{abstract}}\nEvaluate.',
        response_schema: {
          type: 'object',
          properties: { score: { type: 'number', minimum: 0, maximum: 100 } },
          required: ['score'],
        },
        exit_metrics: ['score'],
        primary_frontend_metric: 'score',
        is_active: true,
        ...payload,
      }),
    });
    if (!res.ok) {
      throw new Error(`Create extraction definition failed (${res.status}): ${await res.text()}`);
    }
    return await res.json();
  }

  async startPipelineRun(
    token: string,
    payload: {
      workspace_id: string;
      name?: string;
      limit?: number;
      reprocess_existing?: boolean;
    },
  ): Promise<any> {
    const res = await fetch(`${this.baseURL}/api/pipeline-runs/start/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        autonomous: true,
        limit: 2,
        ...payload,
      }),
    });
    if (!res.ok) {
      throw new Error(`Start pipeline run failed (${res.status}): ${await res.text()}`);
    }
    return await res.json();
  }

  async pollRunUntilComplete(
    token: string,
    runId: string,
    maxSeconds: number = 300,
    intervalMs: number = 3000,
  ): Promise<any> {
    const start = Date.now();
    while (Date.now() - start < maxSeconds * 1000) {
      const res = await fetch(`${this.baseURL}/api/pipeline-runs/${runId}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const status = data.status;
        if (status === 'completed' || status === 'failed' || status === 'aborted') {
          return data;
        }
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new Error(`PipelineRun ${runId} timed out after ${maxSeconds} seconds`);
  }

  async deleteWorkspace(token: string, workspaceId: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseURL}/api/workspaces/${workspaceId}/`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status === 200 || res.status === 204;
    } catch {
      return false;
    }
  }

  /**
   * Pure HTTP API: Creates a new user account.
   */
  async createUser(
    token: string,
    payload: {
      username: string;
      password: string;
      email?: string;
      first_name?: string;
      last_name?: string;
      is_staff?: boolean;
    },
  ): Promise<any> {
    const res = await fetch(`${this.baseURL}/api/auth/users/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errText = await res.text();
      console.warn(`[api-harness] createUser failed (${res.status}): ${errText}`);
      return null;
    }
    return await res.json();
  }

  /**
   * Pure HTTP API: Adds a user to a workspace with a role ('admin', 'manager', 'researcher').
   */
  async addWorkspaceMember(
    token: string,
    workspaceId: string,
    usernameOrEmail: string,
    role: 'admin' | 'manager' | 'researcher' = 'researcher',
  ): Promise<any> {
    const res = await fetch(`${this.baseURL}/api/workspaces/${workspaceId}/members/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        username: usernameOrEmail,
        role,
      }),
    });
    if (!res.ok) {
      const errText = await res.text();
      console.warn(`[api-harness] addWorkspaceMember failed (${res.status}): ${errText}`);
      return null;
    }
    return await res.json();
  }

  /**
   * Pure HTTP API: Deletes a user account by username.
   */
  async deleteUser(token: string, username: string): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseURL}/api/auth/users/${encodeURIComponent(username)}/`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.status === 200 || res.status === 204;
    } catch {
      return false;
    }
  }
}

/**
 * Injects authenticated JWT session cookies directly into the Playwright browser context,
 * bypassing repeated form logins and avoiding login rate throttles.
 */
export async function setAuthCookies(
  context: any,
  tokens: AuthTokens,
  baseURL: string,
): Promise<void> {
  const parsed = new URL(baseURL);
  const domain = parsed.hostname;
  await context.addCookies([
    {
      name: 'sri_access',
      value: tokens.access,
      domain,
      path: '/',
      httpOnly: true,
      secure: parsed.protocol === 'https:',
      sameSite: 'Lax',
    },
    ...(tokens.refresh
      ? [
          {
            name: 'sri_refresh',
            value: tokens.refresh,
            domain,
            path: '/',
            httpOnly: true,
            secure: parsed.protocol === 'https:',
            sameSite: 'Lax',
          },
        ]
      : []),
    {
      name: 'sri_user',
      value: Buffer.from(
        JSON.stringify({
          id: tokens.userId || 1,
          username: tokens.username,
          email: `${tokens.username}@schwarz-digits.cloud`,
          name: tokens.username,
          isStaff: true,
        }),
        'utf8',
      ).toString('base64url'),
      domain,
      path: '/',
      httpOnly: false,
      secure: parsed.protocol === 'https:',
      sameSite: 'Lax',
    },
  ]);
}
