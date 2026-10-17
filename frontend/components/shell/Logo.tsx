// The PagerSage mark from docs/brand/mark.svg (keep the two in step; `npm run brand` regenerates
// the favicons from that file): an alert (orange) and the graph walk (sage) to the root cause.

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      className="block"
    >
      <rect
        x=".75"
        y=".75"
        width="62.5"
        height="62.5"
        rx="13.25"
        fill="#0f1a16"
        stroke="#2c3a34"
        strokeWidth="1.5"
      />
      <g stroke="#3a4a43" strokeWidth="2.5" strokeLinecap="round">
        <line x1="18" y1="19" x2="44" y2="16" />
        <line x1="44" y1="16" x2="46" y2="44" />
        <line x1="31" y1="33" x2="18" y2="47" />
      </g>
      <polyline
        points="18,19 31,33 46,44"
        fill="none"
        stroke="#8fc9a0"
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="44" cy="16" r="3.5" fill="#3a4a43" />
      <circle cx="18" cy="47" r="3.5" fill="#3a4a43" />
      <circle cx="31" cy="33" r="4" fill="#8fc9a0" />
      <path
        d="M10.5 12.5a10.5 10.5 0 0 0 0 13"
        fill="none"
        stroke="#ff8a4c"
        strokeWidth="2"
        strokeLinecap="round"
        opacity=".55"
      />
      <circle cx="18" cy="19" r="5.5" fill="#ff8a4c" />
      <circle
        cx="46"
        cy="44"
        r="9"
        fill="none"
        stroke="#8fc9a0"
        strokeWidth="2"
        opacity=".45"
      />
      <circle cx="46" cy="44" r="5.5" fill="#8fc9a0" />
      <circle cx="46" cy="44" r="2" fill="#0f1a16" />
    </svg>
  );
}

/** "Pager" in the text colour, "Sage" in the brand green, as in docs/brand/logo-dark.svg. */
export function Wordmark() {
  return (
    <span className="text-[15px] font-semibold tracking-[-0.01em]">
      Pager<span className="text-[#5fa874]">Sage</span>
    </span>
  );
}
