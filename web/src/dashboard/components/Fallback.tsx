// Route-loading fallback used as the <Suspense fallback> while a lazy dashboard
// page chunk is fetched. Accessible by default: the wrapper is role="status" with
// an sr-only label so screen readers announce the load, and the visible spinner is
// aria-hidden. The spinner uses `animate-spin`, which the global
// prefers-reduced-motion rule in styles.css already neutralizes. Full-height and
// centered so swapping a page for the fallback causes no layout shift.

export default function Fallback() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-live="polite"
      aria-label="Loading page"
    >
      <span
        className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-foreground"
        aria-hidden="true"
      />
      <span className="sr-only">Loading page…</span>
    </div>
  );
}
