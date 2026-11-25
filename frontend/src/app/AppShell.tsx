import { LogOut, Menu as MenuIcon, Monitor, Moon, Repeat, Sun, UserRound } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import { adminNav, adminSecondaryNav, studentNav, studentSecondaryNav, type NavItem } from './nav';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/button';
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuLabel,
  MenuSeparator,
  MenuTrigger,
  Sheet,
} from '@/components/ui/overlay';
import { useLogout, useUser } from '@/lib/auth';
import { useTheme, type Theme } from '@/lib/theme';
import { cn } from '@/lib/utils';

function NavLinks({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const { pathname } = useLocation();
  return (
    <ul className="flex flex-col gap-1">
      {items.map(({ to, label, icon: Icon, end }) => {
        const deeper = items.some(
          (other) => other.to !== to && other.to.startsWith(to) && pathname.startsWith(other.to),
        );
        return (
          <li key={to}>
            <NavLink
              to={to}
              end={end || deeper}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  'flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium',
                  isActive
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )
              }
            >
              <Icon className="size-4.5 shrink-0" aria-hidden />
              {label}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

const themeOptions: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light theme', icon: Sun },
  { value: 'dark', label: 'Dark theme', icon: Moon },
  { value: 'system', label: 'Match system', icon: Monitor },
];

function UserMenu({ portal }: { portal: 'student' | 'admin' }) {
  const { data: user } = useUser();
  const logout = useLogout();
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();
  if (!user) return null;
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" className="px-2 sm:px-3" aria-label="Account menu">
          <UserRound aria-hidden />
          <span className="hidden max-w-40 truncate sm:inline">{user.full_name}</span>
        </Button>
      </MenuTrigger>
      <MenuContent>
        <MenuLabel>{user.email}</MenuLabel>
        {user.role === 'coordinator' && (
          <MenuItem onSelect={() => navigate(portal === 'admin' ? '/' : '/admin')}>
            <Repeat aria-hidden />
            {portal === 'admin' ? 'Open student portal' : 'Open coordinator portal'}
          </MenuItem>
        )}
        <MenuSeparator />
        {themeOptions.map(({ value, label, icon: Icon }) => (
          <MenuItem key={value} onSelect={() => setTheme(value)}>
            <Icon aria-hidden />
            {label}
            {theme === value && <span className="text-muted-foreground ml-auto">On</span>}
          </MenuItem>
        ))}
        <MenuSeparator />
        <MenuItem
          onSelect={() => logout.mutate(undefined, { onSettled: () => navigate('/login') })}
        >
          <LogOut aria-hidden />
          Sign out
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}

export function AppShell({
  portal,
  topbar,
  banner,
  extras,
}: {
  portal: 'student' | 'admin';
  topbar?: ReactNode;
  banner?: ReactNode;
  extras?: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  const [primary, secondary] =
    portal === 'admin' ? [adminNav, adminSecondaryNav] : [studentNav, studentSecondaryNav];

  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [pathname]);

  const nav = (onNavigate?: () => void) => (
    <>
      <NavLinks items={primary} onNavigate={onNavigate} />
      <div className="my-3 border-t" />
      <NavLinks items={secondary} onNavigate={onNavigate} />
    </>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <a
        href="#main"
        className="bg-primary text-primary-foreground sr-only z-50 rounded-md px-4 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <div className="bg-card sticky top-0 hidden h-dvh flex-col overflow-y-auto border-r p-4 lg:flex">
        <Link to={portal === 'admin' ? '/admin' : '/'} className="mb-6 rounded-md px-1">
          <Logo />
        </Link>
        {portal === 'admin' && (
          <p className="text-muted-foreground mb-3 px-3 text-xs font-medium">Coordinator portal</p>
        )}
        <nav aria-label="Main">{nav()}</nav>
      </div>
      <div className="flex min-w-0 flex-col">
        <header className="bg-card/95 sticky top-0 z-30 flex h-14 items-center gap-2 border-b px-3 backdrop-blur sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
          >
            <MenuIcon aria-hidden />
          </Button>
          <Link
            to={portal === 'admin' ? '/admin' : '/'}
            className="rounded-md lg:hidden"
            aria-label="Home"
          >
            <Logo compact />
          </Link>
          <div className="ml-auto flex items-center gap-1">
            {topbar}
            <UserMenu portal={portal} />
          </div>
        </header>
        {banner}
        <main
          id="main"
          ref={main}
          tabIndex={-1}
          className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 outline-none sm:px-6 lg:py-8"
        >
          <Outlet />
        </main>
        {extras}
      </div>
      <Sheet open={menuOpen} onOpenChange={setMenuOpen} title="Menu">
        <nav aria-label="Main">{nav(() => setMenuOpen(false))}</nav>
      </Sheet>
    </div>
  );
}
