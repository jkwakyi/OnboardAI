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
| Motion | `--transition-duration`, `--transition-easing`, `--transition` |

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

## The token gallery

Every token, rendered from the live stylesheet, at **<http://localhost:5173/#tokens>**
while `npm run dev` is running. Swatches, the type scale, the spacing scale,
the radii, the shadow, and three controls to tab through so the focus ring
can be checked by eye.

It reads the values out of the document rather than repeating them, so a
token that is renamed shows up as `not set` instead of a stale swatch. A test
fails if a token exists in `tokens.css` and the gallery neither shows it nor
lists it as internal plumbing.

Two things to know:

- **Changing the hash needs a reload.** `App.tsx` reads the hash once, at
  mount. Open the URL directly, or refresh after editing it. Routing is
  ON-65's job and the gallery is not worth a router.
- **It is not in the production build.** The guard is the literal
  `import.meta.env.DEV` in `App.tsx`, which Vite replaces with `false` when
  it builds, so the branch is dead code and the bundler drops the component.
  Its stylesheet is imported with `?inline` for the same reason — a plain CSS
  import is a side effect Rollup has to keep. See TD-14 in
  [`TECHNICAL-DEBT.md`](../TECHNICAL-DEBT.md) for what is still only checked
  by hand.

## Layout

```
src/
  styles/     tokens.css and base.css, plus their tests
  dev/        the token gallery and the development flag
  test/       Vitest setup and path helpers
  App.tsx     shell placeholder until ON-65
```

TypeScript is split into three projects: `tsconfig.app.json` for the
application, `tsconfig.node.json` for the Vite config, and
`tsconfig.test.json` for the tests. Only the last two have Node types, which
is what stops a component importing `node:fs`.
