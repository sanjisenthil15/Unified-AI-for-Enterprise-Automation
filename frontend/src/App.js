// Root application component.
// Routes authenticated users by role:
//   admin / other  → /dashboard  (existing admin dashboard)
//   hr             → /hr         (HR Recruitment Dashboard)

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import Login              from './pages/Login/Login';
import Register           from './pages/Login/Register';
import AppLayout          from './layouts/AppLayout';
import Dashboard          from './pages/Dashboard/Dashboard';
import CustomerSupport    from './pages/CustomerSupport/CustomerSupport';
import IncidentManagement from './pages/IncidentManagement/IncidentManagement';
import MeetingsHub        from './pages/Meetings/MeetingsHub';
import Meetings           from './pages/Meetings/Meetings';
import OnlineMeeting      from './pages/Meetings/OnlineMeeting';
import Analytics          from './pages/Analytics/Analytics';
import HRDashboard        from './pages/HRDashboard/HRDashboard';
import EmployeeManagement from './pages/EmployeeManagement/EmployeeManagement';
import Profile            from './pages/Profile/Profile';
import Attendance         from './pages/Attendance/Attendance';
import Sprints            from './pages/Sprints/Sprints';
import Chat               from './pages/Chat/Chat';
import Notifications      from './pages/Notifications/Notifications';

import './App.css';

// Dev flag — when set (and the backend also has AUTH_DISABLED=true), the app
// runs without logging in. See backend/.env AUTH_DISABLED.
const AUTH_DISABLED = process.env.REACT_APP_AUTH_DISABLED === 'true';

/** The cached role from the last login — AUTH_DISABLED always acts as the
 * seeded admin backend-side, so it's treated the same way here. */
function currentRole() {
  if (AUTH_DISABLED) return 'admin';
  try {
    const user = JSON.parse(localStorage.getItem('user') || 'null');
    return user?.role?.name?.toLowerCase() || null;
  } catch {
    return null;
  }
}

/** Redirect to /login if not authenticated (unless auth is disabled for
 * dev); if allowedRoles is given, redirect non-matching roles to /dashboard
 * — real enforcement, not just hiding the sidebar link. */
function ProtectedRoute({ children, allowedRoles }) {
  if (!AUTH_DISABLED && !localStorage.getItem('access_token')) {
    return <Navigate to="/login" replace />;
  }
  if (allowedRoles && !allowedRoles.includes(currentRole())) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* All authenticated routes share AppLayout (sidebar is role-filtered inside) */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>

          {/* Development default landing page: Customer Support module */}
          <Route path="/"                 element={<CustomerSupport />} />

          {/* Admin / default routes */}
          <Route path="/dashboard"        element={<Dashboard />} />
          <Route path="/customer-support" element={<CustomerSupport />} />
          <Route path="/incidents"        element={<IncidentManagement />} />
          <Route path="/meetings"         element={<MeetingsHub />} />
          <Route path="/meetings/offline" element={<Meetings />} />
          <Route path="/meetings/online"  element={<OnlineMeeting />} />
          <Route path="/analytics"        element={<Analytics />} />

          {/* HR recruitment — the real module. /recruitment kept as an alias. */}
          <Route path="/hr"          element={<HRDashboard />} />
          <Route path="/recruitment" element={<HRDashboard />} />

          {/* Employee Management — admin/hr_manager only; My Profile is open to everyone. */}
          <Route
            path="/employees"
            element={
              <ProtectedRoute allowedRoles={['admin', 'hr_manager']}>
                <EmployeeManagement />
              </ProtectedRoute>
            }
          />
          <Route path="/profile" element={<Profile />} />

          {/* Attendance / Sprints / Team Chat / Notifications — open to every
              employee; manager-only sub-views (team attendance, sprint
              creation, team review) are gated per-request on the backend
              and simply don't render their controls client-side otherwise. */}
          <Route path="/attendance"    element={<Attendance />} />
          <Route path="/sprints"       element={<Sprints />} />
          <Route path="/chat"          element={<Chat />} />
          <Route path="/notifications" element={<Notifications />} />

        </Route>

        <Route path="*" element={<Navigate to={AUTH_DISABLED ? '/dashboard' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
