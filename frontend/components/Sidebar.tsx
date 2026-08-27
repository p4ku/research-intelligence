"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useAuth } from '../lib/auth/auth-context';
import { 
  Crosshair,
  Home, 
  FileText, 
  Files, 
  MessageSquare, 
  Sliders, 
  Activity,
  LogOut,
  ChevronUp,
  Shield,
  ExternalLink
} from 'lucide-react';

export default function Sidebar() {
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);

  const navItems = [
    { label: 'Dashboard', href: '/', icon: Home },
    { label: 'Briefings', href: '/briefings', icon: FileText },
    { label: 'Papers', href: '/papers', icon: Files },
    { label: 'Ask', href: '/ask', icon: MessageSquare },
    { label: 'Tuning', href: '/tuning', icon: Sliders },
    { label: 'Status', href: '/status', icon: Activity },
  ];

  const currentPath = router.pathname;

  return (
    <aside className="w-56 bg-[#f8f9fa] border-r border-[#e5e7eb] flex flex-col justify-between h-screen sticky top-0 flex-shrink-0 select-none z-40">
      <div>
        {/* Brand Header */}
        <div className="px-5 py-6 flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-full border border-slate-900 flex items-center justify-center text-slate-900">
            <Crosshair className="w-4 h-4 stroke-[2.2]" />
          </div>
          <span className="font-bold text-xs tracking-wider uppercase text-slate-900 font-mono">
            Research Scanner
          </span>
        </div>

        {/* Navigation Menu */}
        <nav className="px-3 py-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-slate-200/80 text-slate-900 font-semibold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/40'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-slate-900 stroke-[2.2]' : 'text-slate-500'}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* User / Bottom Profile */}
      <div className="p-3 border-t border-[#e5e7eb] relative">
        {isAuthenticated && user ? (
          <div>
            {showUserMenu && (
              <div className="absolute bottom-16 left-3 right-3 bg-white border border-[#e5e7eb] rounded-lg shadow-lg py-1.5 z-50 text-xs text-slate-700">
                <div className="px-3 py-1.5 border-b border-[#f1f5f9] text-[11px] text-slate-500">
                  {user.email || user.username}
                </div>
                <a
                  href="/admin/"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between px-3 py-1.5 hover:bg-slate-50 text-slate-700"
                >
                  <span className="flex items-center gap-2">
                    <Shield className="w-3.5 h-3.5 text-slate-400" />
                    Django Admin
                  </span>
                  <ExternalLink className="w-3 h-3 text-slate-400" />
                </a>
                <button
                  onClick={logout}
                  className="w-full text-left flex items-center gap-2 px-3 py-1.5 text-rose-600 hover:bg-rose-50 cursor-pointer"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Sign Out
                </button>
              </div>
            )}

            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-slate-200/50 transition-colors text-left"
            >
              <div className="flex items-center gap-2.5 truncate">
                <div className="w-6 h-6 rounded bg-slate-200 border border-slate-300 flex items-center justify-center text-xs font-bold text-slate-700">
                  {user.first_name ? user.first_name[0].toUpperCase() : (user.username[0].toUpperCase())}
                </div>
                <div className="truncate">
                  <div className="text-xs font-semibold text-slate-900 truncate">
                    {user.first_name ? `${user.first_name} ${user.last_name || ''}` : user.username}
                  </div>
                </div>
              </div>
              <ChevronUp className={`w-3.5 h-3.5 text-slate-400 transition-transform ${showUserMenu ? 'rotate-180' : ''}`} />
            </button>
          </div>
        ) : (
          <Link
            href="/login"
            className="flex items-center justify-center gap-2 w-full py-2 px-3 bg-slate-900 hover:bg-slate-800 text-white rounded-md text-xs font-semibold shadow-sm transition-colors"
          >
            Sign In
          </Link>
        )}
      </div>
    </aside>
  );
}
