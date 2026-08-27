import { tokenStorage } from '../auth/token-storage';

export function getApiBaseUrl(): string {
  if (typeof window === 'undefined') {
    const envUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
    return envUrl.endsWith('/') ? envUrl.slice(0, -1) : envUrl;
  }

  const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  if (!isLocalhost) {
    return `${window.location.origin}/api`;
  }

  const envUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
  return envUrl.endsWith('/') ? envUrl.slice(0, -1) : envUrl;
}

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: any) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    tokenStorage.clear();
    return null;
  }

  const baseUrl = getApiBaseUrl();
  try {
    const res = await fetch(`${baseUrl}/auth/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ refresh: refreshToken }),
    });

    if (!res.ok) {
      tokenStorage.clear();
      return null;
    }

    const data = await res.json();
    const newAccess = data.access;
    if (newAccess) {
      const currentTokens = tokenStorage.getTokens();
      tokenStorage.saveTokens({
        access: newAccess,
        refresh: data.refresh || currentTokens?.refresh || refreshToken,
      });
      return newAccess;
    }
    return null;
  } catch (err) {
    tokenStorage.clear();
    return null;
  }
}

export interface ApiClientOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiClient<T>(
  endpoint: string,
  options: ApiClientOptions = {}
): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const url = `${baseUrl}${cleanEndpoint}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  headers.set('Accept', 'application/json');

  let accessToken = tokenStorage.getAccessToken();

  // Proactive refresh if token is expired or close to expiry
  if (!options.skipAuth && accessToken && tokenStorage.isTokenExpired(accessToken)) {
    accessToken = await refreshAccessToken();
  }

  if (!options.skipAuth && accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const config: RequestInit = {
    ...options,
    headers,
  };

  let response: Response;
  try {
    response = await fetch(url, config);
  } catch (networkError: any) {
    throw new Error(`Network connection error: ${networkError.message || 'Unable to reach backend API'}`);
  }

  // Handle 401 Unauthorized - Silent Refresh & Retry
  if (response.status === 401 && !options.skipAuth) {
    if (!isRefreshing) {
      isRefreshing = true;
      try {
        const newAccessToken = await refreshAccessToken();
        isRefreshing = false;
        if (newAccessToken) {
          processQueue(null, newAccessToken);
          // Retry original request with new token
          headers.set('Authorization', `Bearer ${newAccessToken}`);
          return apiClient<T>(endpoint, { ...options, headers });
        } else {
          processQueue(new Error('Session expired'), null);
          if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          throw new Error('Your session has expired. Please sign in again.');
        }
      } catch (refreshErr) {
        isRefreshing = false;
        processQueue(refreshErr, null);
        throw refreshErr;
      }
    } else {
      // If refresh is already in flight, wait for queue
      return new Promise<T>((resolve, reject) => {
        failedQueue.push({
          resolve: (token: string) => {
            headers.set('Authorization', `Bearer ${token}`);
            resolve(apiClient<T>(endpoint, { ...options, headers }));
          },
          reject: (err) => {
            reject(err);
          },
        });
      });
    }
  }

  // Parse JSON or text response
  const contentType = response.headers.get('content-type') || '';
  let responseData: any;

  if (contentType.includes('application/json')) {
    try {
      responseData = await response.json();
    } catch {
      responseData = null;
    }
  } else {
    responseData = await response.text();
  }

  if (!response.ok) {
    const errorMsg =
      (typeof responseData === 'object' && responseData !== null && (responseData.error || responseData.detail || JSON.stringify(responseData))) ||
      `HTTP Error ${response.status}: ${response.statusText}`;
    throw new Error(errorMsg);
  }

  return responseData as T;
}
