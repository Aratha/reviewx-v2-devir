/**
 * The ReviewX backdrop, kept quiet: the product's "X" as a large, faint watermark and one thin
 * review line that crosses the screen now and then. Pure CSS from tokens (rules/32); decorative
 * and hidden from assistive technology; the line stays still for users who prefer less motion.
 */
export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <svg className="backdrop-mark" viewBox="0 0 100 100" focusable="false">
        <defs>
          <linearGradient id="backdrop-mark-light" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" className="backdrop-mark-stop-1" />
            <stop offset="1" className="backdrop-mark-stop-2" />
          </linearGradient>
        </defs>
        <path d="M18 18 82 82M82 18 18 82" />
      </svg>
      <div className="backdrop-scan" />
    </div>
  );
}
