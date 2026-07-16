// Error boundary for the hosted dashboard subtree. React error boundaries must be
// class components (there is no hook equivalent for componentDidCatch), so this is
// the one class component in the app. It catches render/lifecycle errors below it
// and swaps the crashed subtree for a themed recover card instead of unmounting to
// a white screen. Two recovery paths: a full reload, and a hard nav back to the
// runs list. Theme-aware via the CSS variable tokens; motion is limited to the
// hover opacity transition, which the global prefers-reduced-motion rule neutralizes.

import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface the crash for debugging without taking down the whole app.
    console.error("Dashboard render error:", error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  private handleBackToRuns = (): void => {
    // Hard navigation clears the crashed React tree entirely and remounts fresh.
    window.location.assign("/app/runs");
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background px-6"
        role="alert"
      >
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 text-center shadow-sm">
          <h1 className="text-lg font-semibold text-foreground">
            Something went wrong
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This page hit an unexpected error. Your data is safe — try reloading,
            or head back to your runs.
          </p>
          {this.state.error?.message ? (
            <p className="mt-4 rounded-md border border-border bg-background px-3 py-2 text-left font-mono text-xs text-muted-foreground break-words">
              {this.state.error.message}
            </p>
          ) : null}
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={this.handleReload}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              Reload page
            </button>
            <button
              type="button"
              onClick={this.handleBackToRuns}
              className="rounded-lg border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              Back to runs
            </button>
          </div>
        </div>
      </div>
    );
  }
}
