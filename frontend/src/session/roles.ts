/**
 * The two roles (ON-65).
 *
 * The strings are not a frontend choice. They are the values the `users`
 * table is constrained to in `backend/app/db/models.py`, which come from
 * the Interface Contracts, and Auth Check compares against them to decide
 * whether a request may reach an HR-only endpoint. Spelling one of them
 * differently here would produce a user interface that disagrees with the
 * server about who someone is.
 */
export const ROLES = ['employee', 'hr_administrator'] as const

export type Role = (typeof ROLES)[number]

/** How each role is written on screen. */
export const ROLE_LABELS: Record<Role, string> = {
  employee: 'Employee',
  hr_administrator: 'HR administrator',
}

export function isRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value)
}
