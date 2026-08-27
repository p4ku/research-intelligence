"use client";

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useAuth } from '../lib/auth/auth-context';
import { 
  Crosshair, 
  LogOut, 
  User as UserIcon, 
  Layers, 
  Activity 
} from 'lucide-react';

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-[#e5e7eb]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand */}
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-full border border-slate-900 flex items-center justify-center text-slate-900 group-hover:bg-slate-900 group-hover:text-white transition-all shadow-sm">
              <Crosshair className="w-4 h-4 stroke-[2.2]" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-bold tracking-tight text-slate-950">
                Schwarz Research Intelligence
              </span>
            </div>
          </Link>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-1 pl-4 border-l border-[#e5e7eb]">
            <Link
              href="/"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                router.pathname === '/' || router.pathname.startsWith('/dashboard')
                  ? 'text-slate-950 bg-slate-100 font-bold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Workspaces
            </Link>

            <Link
              href="/status"
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                router.pathname === '/status'
                  ? 'text-slate-950 bg-slate-100 font-bold'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              System Status
            </Link>
          </nav>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-3">
          {isAuthenticated && user ? (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#f8f9fa] border border-[#e5e7eb] text-xs">
                <div className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-bold text-[10px]">
                  {user.first_name ? user.first_name[0].toUpperCase() : user.username[0].toUpperCase()}
                </div>
                <span className="font-semibold text-slate-900">
                  {user.first_name ? `${user.first_name} ${user.last_name || ''}` : user.username}
                </span>
                {user.is_superuser ? (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-50 text-amber-800 border border-amber-200">
                    ADMIN
                  </span>
                ) : user.is_staff ? (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-50 text-indigo-800 border border-indigo-200">
                    STAFF
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-teal-50 text-teal-800 border border-teal-200">
                    RESEARCHER
                  </span>
                )}
              </div>

              <button
                onClick={logout}
                title="Sign Out"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:text-rose-600 hover:bg-rose-50 border border-[#e5e7eb] transition-all cursor-pointer"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold text-white bg-slate-950 hover:bg-slate-800 active:scale-[0.99] shadow-sm transition-all"
              >
                <UserIcon className="w-3.5 h-3.5" />
                Sign In
              </Link>
            </div>
          )}
        </div>

      </div>
    </header>
  );
}
