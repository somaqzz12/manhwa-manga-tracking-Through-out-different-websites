/**
 * Google Chrome pictogram (simplified silhouette; “Google Chrome” is a trademark of Google LLC).
 * Single-path mark reads clearly at small sizes on dark UI.
 */
export function ChromeIcon({ className = "h-6 w-6" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M12 0C8.21 0 4.83 1.76 2.63 4.5l3.95 6.85a5.45 5.45 0 0 1 5.42-3.8h10.69A12 12 0 0 0 12 0zM1.93 5.47A11.94 11.94 0 0 0 0 12c0 6.01 4.42 10.99 10.19 11.86l3.95-6.85a5.45 5.45 0 0 1-6.86-2.29L1.93 5.47zm13.34 2.02a5.45 5.45 0 0 1 1.77 6.29c.39.67.58 1.43.58 2.22a5.46 5.46 0 0 1-.58 2.23L12 24c6.63 0 12-5.37 12-12 0-4.13-2.09-7.76-5.27-9.91L15.27 7.49zM12 6.55a5.45 5.45 0 1 0 0 10.9 5.45 5.45 0 0 0 0-10.9z" />
    </svg>
  );
}
