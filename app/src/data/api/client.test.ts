import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, buildUrl, encodePath, get } from './client'

describe('buildUrl', () => {
  it('leaves empty filters out and keeps zero and false', () => {
    expect(buildUrl('/x', { entity: null, q: '', rule: undefined, page: 0, overdue: false })).toBe('/x?page=0&overdue=false')
    expect(buildUrl('/x', { q: null })).toBe('/x')
  })
})

describe('encodePath', () => {
  it('encodes each segment and keeps the slashes of a document path', () => {
    expect(encodePath('remittance_advices/ES01/RA 1#2.txt')).toBe('remittance_advices/ES01/RA%201%232.txt')
  })
})

describe('get', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('turns a problem+json response into an ApiError with its detail', async () => {
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ title: 'Not Found', detail: 'No existe la ejecución' }), { status: 404 }))
    const error = await get('/api/runs/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'No existe la ejecución' })
  })

  it('keeps the status when the error body is not JSON', async () => {
    vi.stubGlobal('fetch', async () => new Response('<html>', { status: 502 }))
    await expect(get('/api/runs')).rejects.toMatchObject({ status: 502, message: 'Error 502' })
  })
})
