// Root application component.
// Routes authenticated users by role:
//   admin / other  → /dashboard  (existing admin dashboard)
//   hr             → /hr         (HR Recruitment Dashboard)

import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import Login              from './pages/Login/Login';
import Register           from './pages/Login/Register';
import ChangePassword     from './pages/ChangePassword/ChangePassword';
import AppLayout          from './layouts/AppLayout';
import Dashboard          from './pages/Dashboard/Dashboard';
import CustomerSupport    from './pages/CustomerSupport/CustomerSupport';
import IncidentManagement from './pages/IncidentManagement/IncidentManagement';
import MeetingsHub        from './pages/Meetings/MeetingsHub';
import Meetings           from './pages/Meetings/Meetings';
import OnlineMeeting      from './pages/Meetings/OnlineMeeting';
import ScheduledMeetings  from './pages/Meetings/ScheduledMeetings';
import HRDashboard        from './pages/HRDashboard/HRDashboard';
import EmployeeManagement from './pages/EmployeeManagement/EmployeeManagement';
import Profile            from './pages/Profile/Profile';
import Projects           from './pages/Projects/Projects';
import Leave              from './pages/Leave/Leave';
import AuditLog           from './pages/AuditLog/AuditLog';
import Attendance         from './pages/Attendance/Attendance';
import Sprints            from './pages/Sprints/Sprints';
import Chat               from './pages/Chat/Chat';
import Notifications      from './pages/Notifications/Notifications';
import Analytics          from './pages/Analytics/Analytics';
import Intelligence      from './pages/Intelligence/Intelligence';

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

function mustChangePassword() {
  if (AUTH_DISABLED) return false;
  try {
    return Boolean(JSON.parse(localStorage.getItem('user') || 'null')?.must_change_password);
  } catch {
    return false;
  }
}

/** Redirect to /login if not authenticated (unless auth is disabled for
 * dev); accounts still on an HR-issued temporary password go to the
 * mandatory /change-password screen; if allowedRoles is given, redirect
 * non-matching roles to /dashboard. The backend enforces all of these too. */
function ProtectedRoute({ children, allowedRoles, blockCustomer = false }) {
  if (!AUTH_DISABLED && !localStorage.getItem('access_token')) {
    return <Navigate to="/login" replace />;
  }
  if (mustChangePassword()) {
    return <Navigate to="/change-password" replace />;
  }
  const role = currentRole();
  if (role === 'customer' && blockCustomer) {
    return <Navigate to="/customer-support" replace />;
  }
  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to={role === 'customer' ? '/customer-support' : '/dashboard'} replace />;
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

        {/* Mandatory first-login password change — outside AppLayout (no
            sidebar), guards its own access (token + must_change flag). */}
        <Route path="/change-password" element={<ChangePassword />} />

        {/* All authenticated routes share AppLayout (sidebar is role-filtered inside) */}
        <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>

          {/* Development default landing page: Customer Support module */}
          <Route path="/"                 element={<CustomerSupport />} />

          {/* Admin / default routes */}
          <Route path="/dashboard"        element={<ProtectedRoute blockCustomer><Dashboard /></ProtectedRoute>} />
          <Route
            path="/analytics"
            element={
              <ProtectedRoute allowedRoles={['admin', 'manager', 'viewer']}>
                <Analytics />
              </ProtectedRoute>
            }
          />
          <Route path="/intelligence" element={<ProtectedRoute blockCustomer><Intelligence /></ProtectedRoute>} />
          <Route path="/customer-support" element={<CustomerSupport />} />
          <Route path="/incidents"        element={<ProtectedRoute blockCustomer><IncidentManagement /></ProtectedRoute>} />
          <Route path="/meetings"         element={<ProtectedRoute blockCustomer><MeetingsHub /></ProtectedRoute>} />
          <Route path="/meetings/offline" element={<ProtectedRoute blockCustomer><Meetings /></ProtectedRoute>} />
          <Route path="/meetings/online"  element={<ProtectedRoute blockCustomer><OnlineMeeting /></ProtectedRoute>} />
          <Route path="/meetings/scheduled" element={<ProtectedRoute blockCustomer><ScheduledMeetings /></ProtectedRoute>} />

          {/* HR recruitment — admin/hr_manager/recruiter only; regular
              employees don't need visibility into hiring. /recruitment
              kept as an alias. */}
          <Route
            path="/hr"
            element={
              <ProtectedRoute allowedRoles={['admin', 'hr_manager', 'recruiter']}>
                <HRDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/recruitment"
            element={
              <ProtectedRoute allowedRoles={['admin', 'hr_manager', 'recruiter']}>
                <HRDashboard />
              </ProtectedRoute>
            }
          />

          {/* Employee Management — admin/hr_manager only; My Profile is open to everyone. */}
          <Route
            path="/employees"
            element={
              <ProtectedRoute allowedRoles={['admin', 'hr_manager', 'manager']}>
                <EmployeeManagement />
              </ProtectedRoute>
            }
          />
          <Route path="/profile" element={<Profile />} />

          {/* Projects — open to everyone; the backend scopes which projects
              each role sees and which lifecycle actions it may take. */}
          <Route path="/projects" element={<ProtectedRoute blockCustomer><Projects /></ProtectedRoute>} />

          {/* Leave — everyone requests; Admin / HR Manager approve (backend-enforced). */}
          <Route path="/leave" element={<ProtectedRoute blockCustomer><Leave /></ProtectedRoute>} />

          {/* Audit Log — Admin only, read-only. */}
          <Route
            path="/audit-log"
            element={
              <ProtectedRoute allowedRoles={['admin']}>
                <AuditLog />
              </ProtectedRoute>
            }
          />

          {/* Attendance / Sprints / Team Chat / Notifications — open to every
              employee; manager-only sub-views (team attendance, sprint
              creation, team review) are gated per-request on the backend
              and simply don't render their controls client-side otherwise. */}
          <Route path="/attendance"    element={<ProtectedRoute blockCustomer><Attendance /></ProtectedRoute>} />
          <Route path="/sprints"       element={<ProtectedRoute blockCustomer><Sprints /></ProtectedRoute>} />
          <Route path="/chat"          element={<ProtectedRoute blockCustomer><Chat /></ProtectedRoute>} />
          <Route path="/notifications" element={<ProtectedRoute blockCustomer><Notifications /></ProtectedRoute>} />

        </Route>

        <Route path="*" element={<Navigate to={AUTH_DISABLED ? '/dashboard' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
