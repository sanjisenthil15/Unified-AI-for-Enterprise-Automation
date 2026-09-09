// Root application component.
// Routes authenticated users by role:
//   admin / other  → /dashboard  (existing admin dashboard)
//   hr             → /hr         (HR Recruitment Dashboard)

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import Login              from './pages/Login/Login';
import AppLayout          from './layouts/AppLayout';
import Dashboard          from './pages/Dashboard/Dashboard';
import CustomerSupport    from './pages/CustomerSupport/CustomerSupport';
import IncidentManagement from './pages/IncidentManagement/IncidentManagement';
import Meetings           from './pages/Meetings/Meetings';
import Analytics          from './pages/Analytics/Analytics';
import HRDashboard        from './pages/HRDashboard/HRDashboard';

import './App.css';

// Dev flag — when set (and the backend also has AUTH_DISABLED=true), the app
// runs without logging in. See backend/.env AUTH_DISABLED.
const AUTH_DISABLED = process.env.REACT_APP_AUTH_DISABLED === 'true';

/** Redirect to /login if not authenticated (unless auth is disabled for dev). */
function ProtectedRoute({ children }) {
  return AUTH_DISABLED || localStorage.getItem('access_token')
    ? children
    : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />

        {/* All authenticated routes share AppLayout (sidebar is role-filtered inside) */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>

          {/* Admin / default routes */}
          <Route path="/dashboard"        element={<Dashboard />} />
          <Route path="/customer-support" element={<CustomerSupport />} />
          <Route path="/incidents"        element={<IncidentManagement />} />
          <Route path="/meetings"         element={<Meetings />} />
          <Route path="/analytics"        element={<Analytics />} />

          {/* HR recruitment — the real module. /recruitment kept as an alias. */}
          <Route path="/hr"          element={<HRDashboard />} />
          <Route path="/recruitment" element={<HRDashboard />} />

        </Route>

        <Route path="*" element={<Navigate to={AUTH_DISABLED ? '/dashboard' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
