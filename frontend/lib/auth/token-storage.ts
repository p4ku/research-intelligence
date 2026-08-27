import { AuthTokens, UserProfile } from './types';

const ACCESS_TOKEN_KEY = 'sri_access_token';
const REFRESH_TOKEN_KEY = 'sri_refresh_token';
const USER_PROFILE_KEY = 'sri_user_profile';

export const tokenStorage = {
  saveTokens(tokens: AuthTokens): void {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
      localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
    } catch (e) {
      console.error('Failed to save auth tokens to localStorage', e);
    }
  },

  getTokens(): AuthTokens | null {
    if (typeof window === 'undefined') return null;
    try {
      const access = localStorage.getItem(ACCESS_TOKEN_KEY);
      const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!access || !refresh) return null;
      return { access, refresh };
    } catch {
      return null;
    }
  },

  getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },

  getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },

  saveUser(user: UserProfile): void {
    if (typeof window === 'undefined') return;
    try {
      localStorage.setItem(USER_PROFILE_KEY, JSON.stringify(user));
    } catch (e) {
      console.error('Failed to save user profile', e);
    }
  },

  getUser(): UserProfile | null {
    if (typeof window === 'undefined') return null;
    try {
      const raw = localStorage.getItem(USER_PROFILE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  clear(): void {
    if (typeof window === 'undefined') return;
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
      localStorage.removeItem(USER_PROFILE_KEY);
    } catch (e) {
      console.error('Failed to clear auth storage', e);
    }
  },

  /**
   * Decodes the payload from a JWT token without external dependencies.
   */
  decodeJwtPayload(token: string): any | null {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return null;
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(
        atob(base64)
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(jsonPayload);
    } catch {
      return null;
    }
  },

  /**
   * Checks whether the token has expired (or is within bufferSeconds of expiring).
   */
  isTokenExpired(token: string, bufferSeconds: number = 30): boolean {
    const payload = this.decodeJwtPayload(token);
    if (!payload || !payload.exp) return true;
    const now = Math.floor(Date.now() / 1000);
    return payload.exp <= now + bufferSeconds;
  },
};
