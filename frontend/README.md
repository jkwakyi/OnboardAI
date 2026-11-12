# OnboardAI frontend

React + TypeScript, built with Vite. Install and run steps are in the
[repository README](../README.md#4-frontend); this file covers how the
interface is put together.

```bash
npm install
npm run dev     # http://localhost:5173
npm test
npm run lint
npm run build
```

## Design tokens

Every colour, size, radius, font and duration in the interface is a CSS
custom property declared in [`src/styles/tokens.css`](src/styles/tokens.css).
That file is the only place in `src/` allowed to contain a colour literal, and
a test fails the build if one appears anywhere else. Changing a token
restyles the whole application; a hard-coded value restyles one corner of it
and then drifts.

[`src/styles/base.css`](src/styles/base.css) holds the reset, the document's
typography, the focus ring and the scrollbar. It styles bare elements only —
components are ON-64. Both files are pulled in by `src/index.css`, in that
order, because base.css consumes the tokens.

Dark theme only for the alpha. The names say what a value is **for**, not
what it looks like (`--surface-2`, not `--dark-grey`), so a light theme can
later redefine the same names without touching a component.

### Groups

| Group | Tokens |
| --- | --- |
| Surfaces | `--bg`, `--surface-1`, `--surface-2`, `--border`, `--border-strong` |
| Text | `--text`, `--text-muted` |
| Section accents | `--accent-chat`, `--accent-documents`, `--accent-escalations`, `--accent-info` |
| Status | `--success`, `--warning`, `--danger` |
| Soft tints | the same seven at 15% alpha, as `--*-soft` |
| Spacing | `--space-1` … `--space-7` (4, 8, 12, 16, 24, 32, 48px, expressed in rem) |
| Shape | `--radius-input`, `--radius-card`, `--radius-pill`, `--border-width`, `--shadow-raised` |
| Type | `--font-sans`, `--font-mono`, `--text-xs` … `--text-xl`, `--weight-regular/medium/semibold`, `--line-height-tight/body` |
| Section label | `--label-size`, `--label-weight`, `--label-tracking`, `--label-color` |
| Focus | `--focus-ring-color`, `--focus-ring-width`, `--focus-ring-offset` |
| Motion | `--transition-duration`, `--transition-easing`, `--transition`, `--spin-duration` |
| Controls | `--control-height-sm/md`, `--icon-size-sm/md` |
| Component measurements | `--accent-edge-width`, `--ring-size`, `--ring-thickness`, `--skeleton-line-height`, `--dropzone-min-height`, `--toast-width`, `--disabled-opacity` |

The last two groups arrived with ON-64. A component stylesheet may not
contain a measurement at all, so anything a single component needs and no
scale above describes gets a token rather than an exception — which is what
keeps it visible in the gallery and changeable in one place.

Each accent and status colour is written down once, as a channel triple
(`--accent-chat-rgb: 242 123 165`), and the colour and its soft tint are both
derived from it. Components use `--accent-chat` and `--accent-chat-soft`; the
triple is plumbing.

Reduced motion is handled by redefining `--transition-duration` to `0ms`
inside a `prefers-reduced-motion` media query, so a component that uses the
token gets it for free and does not have to remember the media query.
`base.css` adds a blanket guard for anything that animates without one.

### Contrast

Measured with the WCAG 2.1 formula. Body text needs **4.5:1**; the boundary
of a control needs **3:1** (WCAG 1.4.11). Every row below is enforced by
`src/styles/tokens.test.ts`, which recomputes these from `tokens.css` — if a
value is edited to something unreadable, the test says so.

| Foreground | on `--bg` | on `--surface-1` | on `--surface-2` |
| --- | --- | --- | --- |
| `--text` | 15.87 | 14.71 | 13.41 |
| `--text-muted` | 7.24 | 6.71 | 6.11 |
| `--accent-chat` | 7.25 | 6.72 | 6.13 |
| `--accent-documents` | 9.08 | 8.42 | 7.67 |
| `--accent-escalations` | 7.61 | 7.06 | 6.43 |
| `--accent-info` | 6.87 | 6.36 | 5.80 |
| `--success` | 10.23 | 9.49 | 8.65 |
| `--warning` | 11.99 | 11.11 | 10.13 |
| `--danger` | 6.50 | 6.02 | 5.49 |
| `--border-strong` | 3.75 | 3.48 | 3.17 |

`--border` is deliberately not in that table. At **1.39 / 1.29 / 1.18** it is
a hairline between two surfaces that already differ — decorative, and not
something a user has to find. It is not good enough for the edge of an input,
which is why `--border-strong` exists and why inputs, selects and unfilled
buttons use it. Using `--border` on a control would leave it invisible to
anyone with low vision.

Soft tints are backgrounds only. Text on one is still `--text` or
`--text-muted`, both of which clear 4.5:1 against the surface underneath.

## Shared components

Thirteen components in [`src/components/`](src/components/), imported from
the barrel file rather than from the individual modules:

```tsx
import { Button, Card, StatusPill } from '../components'
```

| Component | What it is |
| --- | --- |
| `Card` | The rounded panel everything sits in. Optional uppercase label, optional accent rule along the top, optional action in the header. |
| `StatusPill` | `success`, `warning`, `danger`, `neutral`. Takes a variant, not a status name — the statuses belong to the Interface Contracts. |
| `ProgressRing` | SVG donut, 0–100, percentage in the middle. One `role="img"` named after what it measures. |
| `StatTile` | Label, value, optional caption, optional ring. Passes its label down so the ring has a subject. |
| `Button` | `primary`, `secondary`, `ghost`, `danger`; `sm` and `md`; icon, loading, disabled. |
| `QuickAction` | The left-rail button. A `Button` underneath, so it inherits the tested behaviour. |
| `FormField` | Label plus `input`, `select` or `textarea`, with helper and error text wired up. |
| `FileDropzone` | Drag or browse, PDF and TXT, shows name and size, refuses the wrong type and an empty file. |
| `CitationChip` | The source under an answer: document and location. Focusable. |
| `Toast` | A message about something that just happened, with an optional close button. |
| `EmptyState` | Title, reason, and the action that would fill it. |
| `ErrorState` | An `EmptyState` in the danger tone, always with a retry. |
| `Skeleton` | Text bars or a block, so the page does not jump when data lands. |

Icons come from [Lucide](https://lucide.dev) (ISC), installed as a
dependency and re-exported from
[`src/components/icons.ts`](src/components/icons.ts). Nothing in this
repository holds a copied SVG file. Adding an icon means adding a line to
that module, which keeps the set small and makes swapping the package one
edit.

Four things the components do that are easy to undo by accident:

- **No component stylesheet contains a measurement.** Not a padding, not a
  width. `src/components/noHardcodedSizes.test.ts` fails on any absolute or
  font-relative length; ratios (`50%`, `1fr`, `aspect-ratio: 1`) are fine.
  It also fails on a stylesheet no component imports.
- **An icon-only `Button` will not compile without an `aria-label`.** The
  props are a union — either children, or a label — so the missing name is
  a type error rather than something a screen reader finds later.
- **Every control edge is `--border-strong`.** `--border` is 1.18:1 against
  `--surface-2` and would leave an input invisible to someone with low
  vision. See the contrast table above.
- **`FileDropzone` is a `<label>` around a real file input.** It is in the
  tab order and announces itself without a key handler of ours. The usual
  div-with-`onClick` dropzone is not reachable by keyboard at all.

`Toast` is only the message. Where toasts stack and how long they stay is
the app shell's business (ON-65): a component that owns its own timer cannot
be tested without one.

## The development galleries

Two kitchen sinks, while `npm run dev` is running:

| URL | What it shows |
| --- | --- |
| <http://localhost:5173/#tokens> | Every design token, read from the live stylesheet |
| <http://localhost:5173/#components> | Every component, in every state it has |

The token gallery reads values out of the document rather than repeating
them, so a token that is renamed shows up as `not set` instead of a stale
swatch. A test fails if a token exists in `tokens.css` and the gallery
neither shows it nor lists it as internal plumbing.

The component gallery reads the component names out of the library's barrel
file, so adding a component without putting it on the page fails too. States
that are awkward to reach in the real app — a button mid-request, a dropzone
refusing a file, an error with its retry — are all one scroll away.

Two things to know:

- **Changing the hash needs a reload.** `App.tsx` reads the hash once, at
  mount, so editing `#tokens` to `#components` in the address bar does
  nothing until you refresh. Routing is ON-65's job and a gallery is not
  worth a router.
- **Neither is in the production build.** The guard is the literal
  `import.meta.env.DEV` in `App.tsx`, repeated in both branches, which Vite
  replaces with `false` when it builds; the branches become dead code and
  the bundler drops the pages. Both stylesheets are imported with `?inline`
  for the same reason — a plain CSS import is a side effect Rollup has to
  keep. The CI frontend job greps `dist/` to prove it (TD-14).

## Layout

```
src/
  styles/       tokens.css and base.css, plus their tests
  components/   the shared library: one .tsx, .css and .test.tsx each
  dev/          the two galleries and the development routes
  test/         Vitest setup and path helpers
  App.tsx       shell placeholder until ON-65
```

TypeScript is split into three projects: `tsconfig.app.json` for the
application, `tsconfig.node.json` for the Vite config, and
`tsconfig.test.json` for the tests. Only the last two have Node types, which
is what stops a component importing `node:fs`.
