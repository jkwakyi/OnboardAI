/**
 * Join class names, dropping the ones that are not there (ON-64).
 *
 * Every component builds its class list from a base, some modifiers that
 * depend on props, and whatever the caller passed in. Written by hand that
 * is a template literal with holes in it, and an absent modifier leaves
 * `class="oa-button  undefined"` behind.
 */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter((part): part is string => Boolean(part)).join(' ')
}
