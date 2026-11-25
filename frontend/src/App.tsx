import { Route, Routes } from 'react-router';
import { AppShell } from './app/AppShell';
import { NotFoundPage } from './app/ErrorPages';
import { RequireCoordinator, RequireUser } from './app/guards';
import { TeamPage } from '@/features/admin/TeamPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { AcceptInvitePage, RegisterPage } from '@/features/auth/RegisterPage';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route element={<RequireUser />}>
        <Route path="/admin" element={<RequireCoordinator />}>
          <Route element={<AppShell portal="admin" />}>
            <Route path="team" element={<TeamPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
        <Route element={<AppShell portal="student" />}>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
