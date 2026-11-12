/**
 * The component gallery shows every component, and ships in no build
 * (ON-64).
 *
 * The acceptance criterion is "every component renders all of its states in
 * the kitchen-sink route", which is the kind of claim that is true on the
 * day it is written. So the list of components is read from the library's
 * own barrel file rather than typed out here: adding a component without
 * putting it on this page fails the first test below.
 */
import { readFileSync } from 'node:fs'

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import ComponentGallery from './ComponentGallery'
import { fromSrc } from '../test/paths'

/** Every component the library exports, from `components/index.ts`. */
function exportedComponents(): string[] {
  const barrel = readFileSync(fromSrc('components', 'index.ts'), 'utf8')
  return [...barrel.matchAll(/default as (\w+)/g)].map((match) => match[1])
}

describe('the component gallery', () => {
  it('reads a library to check itself against', () => {
    // Without this, a barrel file that stopped parsing would make the test
    // below pass by looping over nothing.
    const components = exportedComponents()

    expect(components.length).toBeGreaterThanOrEqual(13)
    expect(components).toContain('Button')
    expect(components).toContain('FileDropzone')
  })

  it.each(exportedComponents())('has a section for %s', (name) => {
    render(<ComponentGallery />)

    expect(screen.getByRole('heading', { name })).toBeInTheDocument()
  })

  it('shows a loading state somewhere', () => {
    const { container } = render(<ComponentGallery />)

    expect(container.querySelectorAll('[aria-busy="true"]').length).toBeGreaterThan(0)
  })

  it('shows a disabled state somewhere', () => {
    const { container } = render(<ComponentGallery />)

    expect(container.querySelectorAll(':disabled').length).toBeGreaterThan(0)
  })

  it('shows an error state somewhere', () => {
    render(<ComponentGallery />)

    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
  })

  it('uses no image asset', () => {
    // Epic ON-62: original design, no third-party template assets. The
    // icons are SVG drawn by Lucide, which is a dependency rather than a
    // file copied into the repository.
    const { container } = render(<ComponentGallery />)

    expect(container.querySelectorAll('img')).toHaveLength(0)
  })
})
