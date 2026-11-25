import {
  BarChart3,
  Bell,
  Bookmark,
  Briefcase,
  ClipboardList,
  FlaskConical,
  Gauge,
  Home,
  LifeBuoy,
  type LucideIcon,
  Megaphone,
  MessageSquare,
  PlusCircle,
  Search,
  Settings,
  Users,
  UserCog,
} from 'lucide-react';

export type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };

export const studentNav: NavItem[] = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/jobs', label: 'Browse', icon: Search },
  { to: '/copilot', label: 'Copilot', icon: MessageSquare },
  { to: '/applications', label: 'Applications', icon: ClipboardList },
  { to: '/saved', label: 'Saved', icon: Bookmark },
];

export const studentSecondaryNav: NavItem[] = [
  { to: '/notifications', label: 'Notifications', icon: Bell },
  { to: '/account', label: 'Profile and privacy', icon: Settings },
  { to: '/help', label: 'Help', icon: LifeBuoy },
];

export const adminNav: NavItem[] = [
  { to: '/admin', label: 'Dashboard', icon: BarChart3, end: true },
  { to: '/admin/postings', label: 'Postings', icon: Briefcase },
  { to: '/admin/postings/new', label: 'Add posting', icon: PlusCircle },
  { to: '/admin/students', label: 'Students', icon: Users },
];

export const adminSecondaryNav: NavItem[] = [
  { to: '/admin/evals', label: 'Evals', icon: FlaskConical },
  { to: '/admin/usage', label: 'LLM usage', icon: Gauge },
  { to: '/admin/announcements', label: 'Announcements', icon: Megaphone },
  { to: '/admin/team', label: 'Team', icon: UserCog },
];
