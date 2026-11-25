import { Route, Routes } from 'react-router';
import { AppShell } from './app/AppShell';
import { NotFoundPage } from './app/ErrorPages';
import { RequireCoordinator, RequireUser } from './app/guards';
import { AddPostingPage } from '@/features/admin/AddPostingPage';
import { AnnouncementsPage } from '@/features/admin/AnnouncementsPage';
import { DashboardPage } from '@/features/admin/DashboardPage';
import { EvalsPage } from '@/features/admin/EvalsPage';
import { PostingDetailPage } from '@/features/admin/PostingDetailPage';
import { PostingsPage } from '@/features/admin/PostingsPage';
import { StudentsPage } from '@/features/admin/StudentsPage';
import { TeamPage } from '@/features/admin/TeamPage';
import { UsagePage } from '@/features/admin/UsagePage';
import { LoginPage } from '@/features/auth/LoginPage';
import { AcceptInvitePage, RegisterPage } from '@/features/auth/RegisterPage';
import { CopilotPage } from '@/features/copilot/CopilotPage';
import { MemoryPage } from '@/features/copilot/MemoryPage';
import { AccountPage } from '@/features/student/AccountPage';
import { ApplicationsPage } from '@/features/student/ApplicationsPage';
import { BrowsePage } from '@/features/student/BrowsePage';
import { HomePage } from '@/features/student/HomePage';
import { HelpPage, PrivacyPage } from '@/features/student/InfoPages';
import { JobDetailPage } from '@/features/student/JobDetailPage';
import { NotificationsPage, SavedPage } from '@/features/student/ListPages';
import { OnboardingPage } from '@/features/student/OnboardingPage';
import { StudentShell } from '@/features/student/StudentShell';
import { SurveyPage } from '@/features/student/SurveyPage';

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
            <Route path="evals" element={<EvalsPage />} />
            <Route path="usage" element={<UsagePage />} />
            <Route path="announcements" element={<AnnouncementsPage />} />
            <Route path="team" element={<TeamPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route element={<StudentShell />}>
          <Route index element={<HomePage />} />
          <Route path="jobs" element={<BrowsePage />} />
          <Route path="jobs/:id" element={<JobDetailPage />} />
          <Route path="copilot" element={<CopilotPage />} />
          <Route path="copilot/:id" element={<CopilotPage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="saved" element={<SavedPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="survey" element={<SurveyPage />} />
          <Route path="help" element={<HelpPage />} />
          <Route path="privacy" element={<PrivacyPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
