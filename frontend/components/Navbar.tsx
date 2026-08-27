"use client";

import React from 'react';
import { useAuth } from '../lib/auth/auth-context';
import { 
  Sparkles, 
  LogOut, 
  User, 
  Layers, 
  Activity, 
  Lock, 
  ShieldCheck, 
  ExternalLink 
} from 'lucide-react';

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();

  const getRoleBadge = () => {
    if (user?.is_superuser) {
      return { label: 'Admin', icon: '👑', color: 'bg-amber-500/15 text-amber-300 border-amber-500/30' };
    }
    return { label: 'Researcher', icon: '🔬', color: 'bg-sky-500/15 text-sky-300 border-sky-500/30' };
  };

  const badge = getRoleBadge();

  return (
    <header className="sticky top-0 z-50 w-full backdrop-blur-md bg-[#090d16]/85 border-b border-slate-800 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand / Logo */}
        <div className="flex items-center gap-6">
          <a href="/" className="flex items-center gap-3 no-underline group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-sky-600 to-sky-400 flex items-center justify-center shadow-lg shadow-sky-500/20 group-hover:scale-105 transition-transform">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-extrabold text-base tracking-tight bg-gradient-to-r from-slate-100 to-slate-300 bg-clip-text text-transparent group-hover:from-white group-hover:to-sky-200 transition-colors">
                Schwarz Research Intelligence
              </div>
              <div className="text-[10px] text-slate-500 font-semibold tracking-wider uppercase">
                Enterprise Systematic Review
              </div>
            </div>
          </a>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
            <a
              href="/"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
            >
              <Layers className="w-3.5 h-3.5 text-sky-400" />
              Workspaces
            </a>
            <a
              href="/status"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-400" />
              System Status
            </a>
            <a
              href="/admin/"
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-colors"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
              Django Admin
              <ExternalLink className="w-3 h-3 text-slate-500" />
            </a>
          </nav>
        </div>

        {/* Right Auth Controls */}
        <div className="flex items-center gap-3">
          {isAuthenticated && user ? (
            <div className="flex items-center gap-3">
              {/* User Profile Pill */}
              <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800">
                <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-sky-400">
                  {user.first_name ? user.first_name[0].toUpperCase() : user.username[0].toUpperCase()}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-200">
                    {user.first_name || user.username}
                  </span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${badge.color}`}>
                    {badge.icon} {badge.label}
                  </span>
                </div>
              </div>

              {/* Logout Button */}
              <button
                onClick={logout}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 transition-all cursor-pointer"
                title="Sign out of current session"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <a
                href="/login"
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold text-white bg-sky-600 hover:bg-sky-500 shadow-md shadow-sky-600/30 hover:shadow-sky-500/40 hover:-translate-y-0.5 transition-all"
              >
                <Lock className="w-3.5 h-3.5" />
                Sign In
              </a>
            </div>
          )}
        </div>

      </div>
    </header>
  );
}
