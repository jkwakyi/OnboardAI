/**
 * FileDropzone (ON-64), used by the admin upload page (ON-42).
 *
 * Both rejections are tested through the component rather than only through
 * `validateFile`, because the part that goes wrong is not the predicate -
 * it is forgetting to clear the previously accepted file when the next one
 * is rejected, which leaves the page showing a name it is not going to
 * upload.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import FileDropzone, {
  EMPTY_FILE_MESSAGE,
  WRONG_TYPE_MESSAGE,
  formatFileSize,
  validateFile,
} from './FileDropzone'

function file(name: string, contents = 'Leave policy.'): File {
  return new File([contents], name, { type: 'text/plain' })
}

const ZONE_LABEL = /Drop a document here/

describe('formatFileSize', () => {
  it.each([
    [0, '0 B'],
    [512, '512 B'],
    [1024, '1.0 KB'],
    [2048, '2.0 KB'],
    [1536, '1.5 KB'],
    [1024 * 1024, '1.0 MB'],
    [1024 * 1024 * 1024 * 3, '3.0 GB'],
  ])('shows %i bytes as %s', (bytes, expected) => {
    expect(formatFileSize(bytes)).toBe(expected)
  })
})

describe('validateFile', () => {
  it.each(['handbook.pdf', 'handbook.txt', 'HANDBOOK.PDF', 'Leave Policy.Txt'])(
    'accepts %s',
    (name) => {
      expect(validateFile(file(name))).toBeNull()
    },
  )

  it.each(['handbook.docx', 'handbook', 'handbook.pdf.exe', 'notes.txt.zip'])(
    'rejects %s',
    (name) => {
      expect(validateFile(file(name))).toBe(WRONG_TYPE_MESSAGE)
    },
  )

  it('rejects a file with nothing in it', () => {
    expect(validateFile(file('handbook.pdf', ''))).toBe(EMPTY_FILE_MESSAGE)
  })
})

describe('FileDropzone', () => {
  it('is a file input, reachable from the keyboard', async () => {
    render(<FileDropzone onFileSelected={vi.fn()} />)

    // Not decoration: the usual div-with-onClick dropzone is not in the tab
    // order at all, and this is the test that would catch a rewrite into
    // one.
    const input = screen.getByLabelText(ZONE_LABEL)
    await userEvent.tab()

    expect(input).toHaveFocus()
    expect(input).toHaveAttribute('type', 'file')
  })

  it('accepts a chosen TXT file and shows its name and size', async () => {
    const onFileSelected = vi.fn()
    render(<FileDropzone onFileSelected={onFileSelected} />)

    await userEvent.upload(screen.getByLabelText(ZONE_LABEL), file('leave-policy.txt'))

    expect(onFileSelected).toHaveBeenCalledOnce()
    expect(onFileSelected.mock.calls[0][0].name).toBe('leave-policy.txt')
    expect(screen.getByText('leave-policy.txt')).toBeInTheDocument()
    expect(screen.getByText('13 B')).toBeInTheDocument()
  })

  it('rejects the wrong type, and does not call back', async () => {
    const onFileSelected = vi.fn()
    const onError = vi.fn()
    render(<FileDropzone onFileSelected={onFileSelected} onError={onError} />)

    await userEvent.upload(screen.getByLabelText(ZONE_LABEL), file('contract.docx'))

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith(WRONG_TYPE_MESSAGE)
    expect(screen.getByRole('alert')).toHaveTextContent(WRONG_TYPE_MESSAGE)
  })

  it('rejects an empty file', async () => {
    const onFileSelected = vi.fn()
    render(<FileDropzone onFileSelected={onFileSelected} />)

    await userEvent.upload(screen.getByLabelText(ZONE_LABEL), file('handbook.pdf', ''))

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(EMPTY_FILE_MESSAGE)
  })

  it('forgets the accepted file when the next one is rejected', async () => {
    render(<FileDropzone onFileSelected={vi.fn()} />)
    const input = screen.getByLabelText(ZONE_LABEL)

    await userEvent.upload(input, file('leave-policy.txt'))
    expect(screen.getByText('leave-policy.txt')).toBeInTheDocument()

    await userEvent.upload(input, file('contract.docx'))

    // Otherwise the page keeps offering to upload a file the user replaced.
    expect(screen.queryByText('leave-policy.txt')).toBeNull()
  })

  it('clears the error once a good file arrives', async () => {
    render(<FileDropzone onFileSelected={vi.fn()} />)
    const input = screen.getByLabelText(ZONE_LABEL)

    await userEvent.upload(input, file('contract.docx'))
    expect(screen.getByRole('alert')).toBeInTheDocument()

    await userEvent.upload(input, file('handbook.pdf'))

    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText('handbook.pdf')).toBeInTheDocument()
  })

  it('accepts a dropped file', () => {
    const onFileSelected = vi.fn()
    const { container } = render(<FileDropzone onFileSelected={onFileSelected} />)
    const zone = container.querySelector('.oa-drop__zone')

    if (zone === null) {
      throw new Error('the dropzone has no drop target')
    }

    fireEvent.drop(zone, { dataTransfer: { files: [file('handbook.pdf')] } })

    expect(onFileSelected).toHaveBeenCalledOnce()
    expect(screen.getByText('handbook.pdf')).toBeInTheDocument()
  })

  it('highlights while a file is over it, and stops when it leaves', () => {
    const { container } = render(<FileDropzone onFileSelected={vi.fn()} />)
    const zone = container.querySelector('.oa-drop__zone')

    if (zone === null) {
      throw new Error('the dropzone has no drop target')
    }

    fireEvent.dragEnter(zone)
    expect(zone).toHaveClass('oa-drop__zone--dragging')

    fireEvent.dragLeave(zone)
    expect(zone).not.toHaveClass('oa-drop__zone--dragging')
  })

  it('stays highlighted while the pointer crosses its own children', () => {
    // Dragging over a child fires dragleave on the parent. Without the
    // depth count the highlight flickers off every time the pointer passes
    // the icon, which looks like the target rejecting the file.
    const { container } = render(<FileDropzone onFileSelected={vi.fn()} />)
    const zone = container.querySelector('.oa-drop__zone')
    const icon = container.querySelector('.oa-drop__icon')

    if (zone === null || icon === null) {
      throw new Error('the dropzone is not shaped as expected')
    }

    fireEvent.dragEnter(zone)
    fireEvent.dragEnter(icon)
    fireEvent.dragLeave(zone)

    expect(zone).toHaveClass('oa-drop__zone--dragging')
  })

  it('takes nothing while disabled', () => {
    const onFileSelected = vi.fn()
    const { container } = render(
      <FileDropzone onFileSelected={onFileSelected} disabled />,
    )
    const zone = container.querySelector('.oa-drop__zone')

    if (zone === null) {
      throw new Error('the dropzone has no drop target')
    }

    expect(screen.getByLabelText(ZONE_LABEL)).toBeDisabled()

    fireEvent.drop(zone, { dataTransfer: { files: [file('handbook.pdf')] } })

    // A disabled input still has a label around it, and a drop handler on
    // the label does not know it is disabled unless it is told.
    expect(onFileSelected).not.toHaveBeenCalled()
  })
})
