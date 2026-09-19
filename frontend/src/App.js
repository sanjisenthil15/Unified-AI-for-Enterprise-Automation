// Root application component.
// Routes authenticated users by role:
//   admin / other  → /dashboard  (existing admin dashboard)
//   hr             → /hr         (HR Recruitment Dashboard)

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import Login              from './pages/Login/Login';
import AppLayout          from './layouts/AppLayout';
import Dashboard          from './pages/Dashboard/Dashboard';
import Recruitment        from './pages/Recruitment/Recruitment';
import CustomerSupport    from './pages/CustomerSupport/CustomerSupport';
import IncidentManagement from './pages/IncidentManagement/IncidentManagement';
import Meetings           from './pages/Meetings/Meetings';
import Analytics          from './pages/Analytics/Analytics';
import HRDashboard        from './pages/HRDashboard/HRDashboard';

import './App.css';

/** Redirect to /login if no token in localStorage (temporarily bypassed for Customer Support dev/testing). */
function ProtectedRoute({ children }) {
  // Temporary Dev Bypass: Allow direct access to Customer Support without requiring login
  return children;
  // Production auth check (preserved):
  // return localStorage.getItem('access_token') ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* All authenticated routes share AppLayout (sidebar is role-filtered inside) */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>

          {/* Development default landing page: Customer Support module */}
          <Route path="/"                 element={<CustomerSupport />} />

          {/* Admin / default routes */}
          <Route path="/dashboard"        element={<Dashboard />} />
          <Route path="/recruitment"      element={<Recruitment />} />
          <Route path="/customer-support" element={<CustomerSupport />} />
          <Route path="/incidents"        element={<IncidentManagement />} />
          <Route path="/meetings"         element={<Meetings />} />
          <Route path="/analytics"        element={<Analytics />} />

          {/* HR-specific route */}
          <Route path="/hr" element={<HRDashboard />} />

        </Route>

        {/* Fallback route: default to /customer-support during development */}
        <Route path="*" element={<Navigate to="/customer-support" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
