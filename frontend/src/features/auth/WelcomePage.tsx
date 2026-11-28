import {
  ArrowRight,
  BellRing,
  ClipboardCheck,
  CodeXml,
  FileSearch,
  MessageSquareText,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react';
import type { ComponentType, ReactNode, SVGProps } from 'react';
import { Link, useNavigate } from 'react-router';
import { Logo } from '@/components/Logo';
import { Button } from '@/components/ui/button';
import { homePath, useDemoAvailable, useDemoLogin, useUser } from '@/lib/auth';
import { useTitle } from '@/lib/title';

const REPO = 'https://github.com/shlok165/placement_rag';

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

const studentFeatures: { icon: Icon; title: string; text: string }[] = [
  {
    icon: FileSearch,
    title: 'Search by meaning',
    text: 'Type “remote ML internship in Pune, above 30k” and get filters plus results, ranked for your skills.',
  },
  {
    icon: SlidersHorizontal,
    title: 'See why it fits',
    text: 'Every match shows its parts: skills, preferences, profile. A formula you can read, not a black box.',
  },
  {
    icon: MessageSquareText,
    title: 'A copilot with sources',
    text: 'Ask anything about the postings. Answers cite them, and are checked before you see a word.',
  },
  {
    icon: ClipboardCheck,
    title: 'Track and get reminded',
    text: 'Move applications through stages, get deadline reminders, or add them to your own calendar.',
  },
];

function Feature({
  icon: Icon,
  title,
  children,
}: {
  icon: Icon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="bg-card rounded-xl border p-5">
      <span className="bg-accent text-accent-foreground flex size-10 items-center justify-center rounded-lg">
        <Icon className="size-5" aria-hidden />
      </span>
      <h3 className="mt-4 font-semibold">{title}</h3>
      <p className="text-muted-foreground mt-1.5 text-sm leading-relaxed">{children}</p>
    </div>
  );
}

function Screenshot({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="bg-card overflow-hidden rounded-xl border shadow-xl shadow-black/5">
      <div className="bg-muted flex gap-1.5 border-b px-3 py-2" aria-hidden>
        <span className="size-2.5 rounded-full bg-black/15" />
        <span className="size-2.5 rounded-full bg-black/15" />
        <span className="size-2.5 rounded-full bg-black/15" />
      </div>
      <img src={src} alt={alt} loading="lazy" className="block w-full" width={1280} height={820} />
    </div>
  );
}

export function WelcomePage() {
  useTitle('Internship and placement copilot');
  const { data: user } = useUser();
  const { data: demoAvailable } = useDemoAvailable();
  const demo = useDemoLogin();
  const navigate = useNavigate();

  const tryDemo = () =>
    demo.mutate(undefined, { onSuccess: (signedIn) => navigate(homePath(signedIn)) });

  const primary = user ? (
    <Button asChild size="lg">
      <Link to={homePath(user)}>
        Open your dashboard
        <ArrowRight aria-hidden />
      </Link>
    </Button>
  ) : demoAvailable ? (
    <Button size="lg" loading={demo.isPending} onClick={tryDemo}>
      Try the live demo
      <ArrowRight aria-hidden />
    </Button>
  ) : (
    <Button asChild size="lg">
      <Link to="/login">
        Sign in
        <ArrowRight aria-hidden />
      </Link>
    </Button>
  );

  return (
    <div className="bg-background min-h-dvh">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
        <Link to="/welcome" className="rounded-md">
          <Logo />
        </Link>
        <nav aria-label="Site" className="flex items-center gap-1 sm:gap-2">
          <Button asChild variant="ghost" className="hidden sm:inline-flex">
            <a href={REPO} target="_blank" rel="noopener noreferrer">
              <CodeXml aria-hidden />
              Source
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </Button>
          {!user && (
            <Button asChild variant="secondary">
              <Link to="/login">Sign in</Link>
            </Button>
          )}
        </nav>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-4 pt-10 pb-16 sm:px-6 lg:pt-16">
          <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <div>
              <p className="text-primary text-sm font-semibold tracking-wide uppercase">
                Internships and placements, IIT Ropar
              </p>
              <h1 className="mt-3 text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-5xl">
                Find the role that fits you, and know why it does.
              </h1>
              <p className="text-muted-foreground mt-5 max-w-xl text-lg leading-relaxed text-pretty">
                One place for every posting from the CAPS office: search that understands what you
                mean, a match score you can read, and a copilot that only answers from real
                postings.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                {primary}
                {!user && (
                  <Button asChild size="lg" variant="ghost">
                    <Link to="/register">Create a student account</Link>
                  </Button>
                )}
              </div>
              {demo.isError && (
                <p role="alert" className="text-danger mt-3 text-sm">
                  The demo could not start right now. Please try again in a minute.
                </p>
              )}
              {demoAvailable && !user && (
                <p className="text-muted-foreground mt-4 text-sm">
                  The demo signs you in to a shared student account with sample postings.
                </p>
              )}
            </div>
            <Screenshot
              src="/screens/student-copilot.png"
              alt="The copilot answering a question with cited postings and a button to save one"
            />
          </div>
        </section>

        <section aria-labelledby="students" className="bg-muted/50 border-y">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
            <h2 id="students" className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Built around how students actually search
            </h2>
            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {studentFeatures.map((f) => (
                <Feature key={f.title} icon={f.icon} title={f.title}>
                  {f.text}
                </Feature>
              ))}
            </div>
          </div>
        </section>

        <section aria-labelledby="fit" className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <Screenshot
              src="/screens/student-job.png"
              alt="A posting with its match score broken into skills, preferences and profile"
            />
            <div>
              <h2 id="fit" className="text-2xl font-semibold tracking-tight sm:text-3xl">
                A match score you can check
              </h2>
              <p className="text-muted-foreground mt-4 text-lg leading-relaxed">
                Each posting shows how much of the score comes from your skills, your preferences
                and your profile, which skills you are missing, and what it does not claim to know:
                your chance of selection.
              </p>
            </div>
          </div>
        </section>

        <section aria-labelledby="caps" className="bg-muted/50 border-y">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2">
            <div>
              <h2 id="caps" className="text-2xl font-semibold tracking-tight sm:text-3xl">
                For the CAPS team
              </h2>
              <ul className="text-muted-foreground mt-5 flex flex-col gap-4 text-lg">
                <li className="flex gap-3">
                  <FileSearch className="text-primary mt-1 size-5 shrink-0" aria-hidden />
                  Paste a posting, upload a PDF or a CSV. Fields are read for you and shown beside
                  the original to check.
                </li>
                <li className="flex gap-3">
                  <BellRing className="text-primary mt-1 size-5 shrink-0" aria-hidden />
                  Matching students are alerted when a posting goes live.
                </li>
                <li className="flex gap-3">
                  <ShieldCheck className="text-primary mt-1 size-5 shrink-0" aria-hidden />
                  Student data stays private: totals by default, and every look at one student is
                  recorded.
                </li>
              </ul>
            </div>
            <Screenshot
              src="/screens/admin-review.png"
              alt="A coordinator reviewing the fields read from a pasted posting next to the original text"
            />
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 text-center sm:px-6">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">See it for yourself</h2>
          <p className="text-muted-foreground mx-auto mt-3 max-w-xl text-lg">
            Open-source, from the search engine to the evaluation of every number it reports.
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-3">
            {primary}
            <Button asChild size="lg" variant="secondary">
              <a href={REPO} target="_blank" rel="noopener noreferrer">
                <CodeXml aria-hidden />
                Read the code
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="text-muted-foreground mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm sm:px-6">
          <span>placement_rag · MIT licensed</span>
          <span>Postings on this demo are synthetic samples.</span>
        </div>
      </footer>
    </div>
  );
}
