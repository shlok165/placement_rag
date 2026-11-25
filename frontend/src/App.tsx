import { Route, Routes } from 'react-router';
import { AppShell } from './app/AppShell';
import { NotFoundPage } from './app/ErrorPages';
import { RequireCoordinator, RequireUser } from './app/guards';
import { AddPostingPage } from '@/features/admin/AddPostingPage';
import { AnnouncementsPage } from '@/features/admin/AnnouncementsPage';
import { DashboardPage } from '@/features/admin/DashboardPage';
import { PostingDetailPage } from '@/features/admin/PostingDetailPage';
import { PostingsPage } from '@/features/admin/PostingsPage';
import { StudentsPage } from '@/features/admin/StudentsPage';
import { TeamPage } from '@/features/admin/TeamPage';
import { UsagePage } from '@/features/admin/UsagePage';
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
            <Route index element={<DashboardPage />} />
            <Route path="postings" element={<PostingsPage />} />
            <Route path="postings/new" element={<AddPostingPage />} />
            <Route path="postings/:id" element={<PostingDetailPage />} />
            <Route path="students" element={<StudentsPage />} />
            <Route path="usage" element={<UsagePage />} />
            <Route path="announcements" element={<AnnouncementsPage />} />
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
