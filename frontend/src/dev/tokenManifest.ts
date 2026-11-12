/**
 * What the token gallery shows, and how to show it (ON-63).
 *
 * A test reads `styles/tokens.css` and fails if a token declared there is
 * missing from this file, so the gallery cannot quietly fall behind the
 * tokens it is meant to document.
 */

/** How a token's value should be previewed. */
export type TokenPreview =
  | 'color'
  | 'space'
  | 'radius'
  | 'shadow'
  | 'font-family'
  | 'font-size'
  | 'font-weight'
  | 'value'

export interface TokenGroup {
  title: string
  /** Why these tokens exist, in one line. */
  note: string
  preview: TokenPreview
  tokens: string[]
}

/**
 * Tokens the gallery deliberately leaves out.
 *
 * The `-rgb` triples exist only so a colour and its 15% tint can be written
 * from one value; nothing styles anything with them directly. `--soft-alpha`
 * is the tint strength those triples are multiplied by. Showing them would
 * suggest a component should use them.
 */
export const INTERNAL_TOKENS = [
  '--accent-chat-rgb',
  '--accent-documents-rgb',
  '--accent-escalations-rgb',
  '--accent-info-rgb',
  '--success-rgb',
  '--warning-rgb',
  '--danger-rgb',
  '--soft-alpha',
]

export const TOKEN_GROUPS: TokenGroup[] = [
  {
    title: 'Surfaces',
    note: 'Three levels of dark, plus the lines between them.',
    preview: 'color',
    tokens: ['--bg', '--surface-1', '--surface-2', '--border', '--border-strong'],
  },
  {
    title: 'Text',
    note: 'Both pass AA on all three surfaces.',
    preview: 'color',
    tokens: ['--text', '--text-muted'],
  },
  {
    title: 'Section accents',
    note: 'One per area, so a screen says where it is without a label.',
    preview: 'color',
    tokens: ['--accent-chat', '--accent-documents', '--accent-escalations', '--accent-info'],
  },
  {
    title: 'Status',
    note: 'Never the only signal: each pairs with text or an icon.',
    preview: 'color',
    tokens: ['--success', '--warning', '--danger'],
  },
  {
    title: 'Soft tints',
    note: '15% alpha, for the background of a pill or a tinted panel.',
    preview: 'color',
    tokens: [
      '--accent-chat-soft',
      '--accent-documents-soft',
      '--accent-escalations-soft',
      '--accent-info-soft',
      '--success-soft',
      '--warning-soft',
      '--danger-soft',
    ],
  },
  {
    title: 'Spacing',
    note: 'In rem, so the layout grows with the browser font size.',
    preview: 'space',
    tokens: [
      '--space-1',
      '--space-2',
      '--space-3',
      '--space-4',
      '--space-5',
      '--space-6',
      '--space-7',
    ],
  },
  {
    title: 'Radii',
    note: 'Named for what they go on.',
    preview: 'radius',
    tokens: ['--radius-input', '--radius-card', '--radius-pill'],
  },
  {
    title: 'Elevation',
    note: 'One shadow, for anything floating above a surface.',
    preview: 'shadow',
    tokens: ['--shadow-raised'],
  },
  {
    title: 'Controls',
    note: 'The two heights a button, input or select is drawn at.',
    preview: 'space',
    tokens: [
      '--control-height-sm',
      '--control-height-md',
      '--icon-size-sm',
      '--icon-size-md',
    ],
  },
  {
    title: 'Component measurements',
    note: 'Sizes one component needs; no stylesheet may hold its own.',
    preview: 'value',
    tokens: [
      '--accent-edge-width',
      '--ring-size',
      '--ring-thickness',
      '--skeleton-line-height',
      '--dropzone-min-height',
      '--toast-width',
      '--disabled-opacity',
    ],
  },
  {
    title: 'Shell measurements',
    note: 'The frame every signed-in page renders inside.',
    preview: 'value',
    tokens: ['--rail-width', '--topbar-height', '--login-width'],
  },
  {
    title: 'Font stacks',
    note: 'System fonts only: nothing downloads in the alpha.',
    preview: 'font-family',
    tokens: ['--font-sans', '--font-mono'],
  },
  {
    title: 'Type scale',
    note: 'Five sizes. A sixth means the design went wrong somewhere.',
    preview: 'font-size',
    tokens: ['--text-xs', '--text-sm', '--text-md', '--text-lg', '--text-xl'],
  },
  {
    title: 'Weights',
    note: 'Three weights, all present in every system font.',
    preview: 'font-weight',
    tokens: ['--weight-regular', '--weight-medium', '--weight-semibold'],
  },
  {
    title: 'Section label',
    note: 'The uppercase heading above a group of cards.',
    preview: 'value',
    tokens: ['--label-size', '--label-weight', '--label-tracking', '--label-color'],
  },
  {
    title: 'Focus ring',
    note: 'Violet, so it never reads as one area’s accent.',
    preview: 'value',
    tokens: ['--focus-ring-color', '--focus-ring-width', '--focus-ring-offset'],
  },
  {
    title: 'Measurements',
    note: 'The remaining numbers components read.',
    preview: 'value',
    tokens: ['--border-width', '--line-height-tight', '--line-height-body'],
  },
  {
    title: 'Motion',
    note: 'The durations become 0ms under prefers-reduced-motion.',
    preview: 'value',
    tokens: [
      '--transition-duration',
      '--transition-easing',
      '--transition',
      '--spin-duration',
    ],
  },
]

/** Every token the gallery renders, in order. */
export const GALLERY_TOKENS = TOKEN_GROUPS.flatMap((group) => group.tokens)
