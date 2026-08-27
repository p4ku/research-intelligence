"use client";

import React from 'react';
import ProtectedRoute from '../../components/auth/ProtectedRoute';
import DashboardPage from './DashboardPage';

export { default as LandingPage } from './LandingPage';
export { default as DashboardPage } from './DashboardPage';

export default function DashboardRoute() {
  return (
    <ProtectedRoute>
      <DashboardPage />
    </ProtectedRoute>
  );
}
