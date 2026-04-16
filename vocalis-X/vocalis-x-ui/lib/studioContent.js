export const NAV_ITEMS = [
  { href: "/", label: "DiffRhythm" },
  { href: "/musicgen", label: "MusicGen" },
  { href: "/lyrics", label: "Lyrics" },
  { href: "/beta", label: "Beta Lab" },
];

export const GUEST_LIBRARY = [];

export const FEATURE_CARDS = [
  {
    title: "Shared studio shell",
    body: "Every route keeps the same cinematic shell, auth model, library treatment, and card language so the product feels like one app.",
    accent: "sunset",
  },
  {
    title: "Focused generation modes",
    body: "DiffRhythm, MusicGen, and lyrics each get their own dedicated workflow instead of forcing everything into one overloaded composer.",
    accent: "ember",
  },
  {
    title: "Validation first",
    body: "Each page blocks bad requests early, shows actionable errors, and keeps the backend payload clean instead of sending half-filled forms.",
    accent: "lime",
  },
];

export const FAQS = [
  "Can MusicGen generate instrumental audio without vocals?",
  "Will DiffRhythm still skip OpenUtau when the toggle is off?",
  "Does the lyrics tool validate BPM and time signature before generation?",
];

export const EMPTY_AUTH = { displayName: "", email: "", password: "" };
