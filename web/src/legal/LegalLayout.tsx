// Shared chrome + typography for the public legal pages (Terms, Privacy,
// Acceptable Use / Refund). Self-contained: its own header + footer so the pages
// work as standalone public routes. Styled to the v3 "quiet workspace" system —
// Inter, hairline borders, whitespace as the material, one accent-free column.
//
// No @tailwindcss/typography plugin is installed, so the prose primitives below
// (H2/H3/P/UL/LI) carry their own utility classes.

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

const LEGAL_NAV = [
  { to: "/legal/terms", label: "Terms of Service" },
  { to: "/legal/privacy", label: "Privacy Policy" },
  { to: "/legal/acceptable-use", label: "Acceptable Use & Refunds" },
] as const;

export function H2({ children }: { children: ReactNode }) {
  return (
    <h2 className="mt-10 mb-3 text-lg font-semibold tracking-tight text-foreground">
      {children}
    </h2>
  );
}

export function H3({ children }: { children: ReactNode }) {
  return (
    <h3 className="mt-6 mb-2 text-sm font-semibold text-foreground">{children}</h3>
  );
}

export function P({ children }: { children: ReactNode }) {
  return (
    <p className="mb-4 text-sm leading-relaxed text-muted-foreground">{children}</p>
  );
}

export function UL({ children }: { children: ReactNode }) {
  return (
    <ul className="mb-4 flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed text-muted-foreground">
      {children}
    </ul>
  );
}

export function LI({ children }: { children: ReactNode }) {
  return <li>{children}</li>;
}

/** Bold inline emphasis in body copy, kept in foreground color. */
export function B({ children }: { children: ReactNode }) {
  return <span className="font-medium text-foreground">{children}</span>;
}

interface Props {
  title: string;
  /** Human "last updated" date shown under the title. */
  updated: string;
  children: ReactNode;
}

export default function LegalLayout({ title, updated, children }: Props) {
  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <header className="sticky top-0 z-50 bg-background border-b border-border">
        <div className="mx-auto max-w-3xl px-6 h-12 flex items-center justify-between">
          <Link
            to="/"
            className="font-mono text-sm hover:opacity-70 transition-opacity"
          >
            simulation labs
          </Link>
          <Link
            to="/"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            ← back to app
          </Link>
        </div>
      </header>

      <main className="flex-1">
        <article className="mx-auto max-w-3xl px-6 py-12">
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            last updated {updated}
          </p>

          <div className="mt-6 rounded-lg border border-border bg-hover p-3.5 text-sm leading-relaxed text-foreground">
            <B>DRAFT — review by legal counsel before launch.</B> This document is
            a good-faith first draft and is not legal advice.
          </div>

          <div className="mt-8">{children}</div>

          <nav
            aria-label="Legal"
            className="mt-14 flex flex-wrap gap-x-6 gap-y-2 border-t border-border pt-6"
          >
            {LEGAL_NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </article>
      </main>

      <footer className="border-t border-border py-8 px-6">
        <div className="mx-auto max-w-3xl flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 text-xs text-muted-foreground">
          <span className="font-mono">simulation labs</span>
          <span>© 2026 Simulation Labs</span>
        </div>
      </footer>
    </div>
  );
}
