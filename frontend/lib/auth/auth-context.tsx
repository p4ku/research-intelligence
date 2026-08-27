"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { UserProfile, AuthTokens, LoginResponse } from './types';
import { tokenStorage } from './token-storage';
import { apiClient, refreshAccessToken } from '../api/client';

interface AuthContextType {
  user: UserProfile | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (usernameOrEmail: string, password: string) => Promise<UserProfile>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Initialize session on client mount
  useEffect(() => {
    const initAuth = async () => {
      const storedTokens = tokenStorage.getTokens();
      const storedUser = tokenStorage.getUser();

      if (!storedTokens) {
        setIsLoading(false);
        return;
      }

      setTokens(storedTokens);
      if (storedUser) {
        setUser(storedUser);
      }

      // Verify token validity and sync fresh profile
      try {
        let access = storedTokens.access;
        if (tokenStorage.isTokenExpired(access)) {
          const newAccess = await refreshAccessToken();
          if (!newAccess) {
            tokenStorage.clear();
            setUser(null);
            setTokens(null);
            setIsLoading(false);
            return;
          }
          access = newAccess;
        }

        const freshProfile = await apiClient<UserProfile>('/auth/me/');
        setUser(freshProfile);
        tokenStorage.saveUser(freshProfile);
      } catch (err) {
        console.warn('Session verification failed, clearing auth state:', err);
        tokenStorage.clear();
        setUser(null);
        setTokens(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = async (usernameOrEmail: string, password: string): Promise<UserProfile> => {
    setIsLoading(true);
    try {
      const res = await apiClient<LoginResponse>('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({
          username_or_email: usernameOrEmail.trim(),
          password,
        }),
        skipAuth: true,
      });

      const newTokens: AuthTokens = {
        access: res.access,
        refresh: res.refresh,
      };

      tokenStorage.saveTokens(newTokens);
      tokenStorage.saveUser(res.user);

      setTokens(newTokens);
      setUser(res.user);
      return res.user;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    tokenStorage.clear();
    setUser(null);
    setTokens(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  };

  const refreshProfile = async () => {
    try {
      const profile = await apiClient<UserProfile>('/auth/me/');
      setUser(profile);
      tokenStorage.saveUser(profile);
    } catch (err) {
      console.error('Failed to refresh user profile:', err);
    }
  };

  const isAuthenticated = Boolean(user && tokens?.access);

  return (
    <AuthContext.Provider
      value={{
        user,
        tokens,
        isAuthenticated,
        isLoading,
        login,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
