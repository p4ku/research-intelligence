"use client";

import React, { useState, useEffect } from 'react';
import { useAuth } from '../../lib/auth/auth-context';
import { 
  Lock, 
  Mail, 
  Eye, 
  EyeOff, 
  Sparkles, 
  ShieldAlert, 
  ArrowRight, 
  ArrowLeft 
} from 'lucide-react';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      window.location.href = '/';
    }
  }, [isLoading, isAuthenticated]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) {
      setError('Please enter both your email/username and password.');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      await login(identifier, password);
      window.location.href = '/';
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-65px)] bg-[#090d16] bg-[radial-gradient(circle_at_50%_20%,#1e1b4b_0%,#090d16_65%)] text-slate-100 flex flex-col items-center justify-center p-4 sm:p-6 lg:p-8">
      <div className="max-w-md w-full">
        
        {/* Back Link */}
        <div className="mb-6">
          <a
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Home
          </a>
        </div>

        {/* Header Branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-600 to-sky-400 shadow-xl shadow-sky-500/20 mb-4">
            <Sparkles className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-slate-100 via-slate-200 to-slate-400 bg-clip-text text-transparent mb-2">
            Sign In to Workspaces
          </h1>
          <p className="text-sm text-slate-400">
            Enter your credentials to access assigned SLR projects
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl backdrop-blur-xl">
          {error && (
            <div className="flex items-start gap-3 bg-rose-500/10 border border-rose-500/25 rounded-xl p-3.5 text-rose-400 text-sm mb-6 leading-snug">
              <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div>{error}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Email / Username Field */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Email or Username
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="admin or researcher@schwarz.de"
                  autoComplete="username"
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 pl-10 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400 transition-all"
                />
                <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            {/* Password Field */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 pl-10 pr-10 text-sm text-slate-100 placeholder:text-slate-500 outline-none focus:border-sky-400 focus:ring-1 focus:ring-sky-400 transition-all"
                />
                <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors p-1"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 flex items-center justify-center gap-2 w-full py-3 px-4 rounded-xl text-sm font-bold text-white bg-sky-600 hover:bg-sky-500 active:scale-[0.99] disabled:opacity-70 disabled:cursor-not-allowed shadow-lg shadow-sky-600/30 hover:shadow-sky-500/40 transition-all cursor-pointer"
            >
              {isSubmitting ? (
                <span>Signing In...</span>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Footer note */}
          <div className="mt-6 pt-5 border-t border-slate-800/80 text-xs text-slate-500 text-center leading-relaxed">
            Secure JWT token session with automatic renewal.
          </div>
        </div>
      </div>
    </div>
  );
}
