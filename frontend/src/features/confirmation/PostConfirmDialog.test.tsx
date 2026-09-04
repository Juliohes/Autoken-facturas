import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { PostConfirmDialog } from './PostConfirmDialog'

describe('PostConfirmDialog (R-052)', () => {
  it('C2/C3: permite revisar la siguiente o volver a la bandeja', async () => {
    const onReview = vi.fn()
    const onClose = vi.fn()
    render(<PostConfirmDialog onReview={onReview} onClose={onClose} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: 'Sí, revisar' }))
    await user.click(screen.getByRole('button', { name: 'No, volver a mis facturas' }))

    expect(onReview).toHaveBeenCalledOnce()
    expect(onClose).toHaveBeenCalledOnce()
  })
})
