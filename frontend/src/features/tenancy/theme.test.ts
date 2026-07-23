// Tests de comportamiento de S4.2 (lógica pura): mapeo branding->tema y su aplicación al DOM.
import { afterEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_APP_NAME,
  DEFAULT_COLOR_PRIMARY,
  DEFAULT_COLOR_SECONDARY,
  applyTenantTheme,
  resolveTheme,
} from './theme'
import type { CurrentTenant } from './types'

function makeTenant(over: Partial<CurrentTenant> = {}): CurrentTenant {
  return {
    slug: 'ilex',
    name: 'I-Lex Asesoría',
    is_demo: false,
    logo_url: null,
    color_primary: null,
    color_secondary: null,
    app_name: null,
    favicon: null,
    ...over,
  }
}

afterEach(() => {
  document.title = ''
  document.documentElement.style.removeProperty('--color-primary')
  document.documentElement.style.removeProperty('--color-secondary')
})

describe('resolveTheme (S4.2)', () => {
  it('C5: con branding completo, usa esos valores tal cual', () => {
    const theme = resolveTheme(
      makeTenant({ app_name: 'I-Lex', color_primary: '#112233', color_secondary: '#445566' }),
    )
    expect(theme.appName).toBe('I-Lex')
    expect(theme.colorPrimary).toBe('#112233')
    expect(theme.colorSecondary).toBe('#445566')
  })

  it('C6: sin branding (tenant undefined), cae a los valores por defecto', () => {
    const theme = resolveTheme(undefined)
    expect(theme.appName).toBe(DEFAULT_APP_NAME)
    expect(theme.colorPrimary).toBe(DEFAULT_COLOR_PRIMARY)
    expect(theme.colorSecondary).toBe(DEFAULT_COLOR_SECONDARY)
  })

  it('C6: con tenant resuelto pero branding a null, cae a los valores por defecto', () => {
    const theme = resolveTheme(makeTenant())
    expect(theme.appName).toBe(DEFAULT_APP_NAME)
    expect(theme.colorPrimary).toBe(DEFAULT_COLOR_PRIMARY)
    expect(theme.colorSecondary).toBe(DEFAULT_COLOR_SECONDARY)
  })

  it('caso límite: cada campo cae a su propio default de forma independiente', () => {
    const theme = resolveTheme(makeTenant({ color_primary: '#abcdef' }))
    expect(theme.colorPrimary).toBe('#abcdef')
    expect(theme.colorSecondary).toBe(DEFAULT_COLOR_SECONDARY)
    expect(theme.appName).toBe(DEFAULT_APP_NAME)
  })

  it('C7: logoUrl es null cuando el tenant no tiene logo', () => {
    expect(resolveTheme(makeTenant()).logoUrl).toBeNull()
  })

  it('C7: logoUrl se propaga tal cual cuando existe', () => {
    expect(resolveTheme(makeTenant({ logo_url: 'https://cdn.x/logo.png' })).logoUrl).toBe(
      'https://cdn.x/logo.png',
    )
  })
})

describe('applyTenantTheme (S4.2)', () => {
  it('aplica el título y las variables CSS al DOM', () => {
    applyTenantTheme({
      appName: 'I-Lex',
      colorPrimary: '#112233',
      colorSecondary: '#445566',
      logoUrl: null,
    })
    expect(document.title).toBe('I-Lex')
    expect(document.documentElement.style.getPropertyValue('--color-primary')).toBe('#112233')
    expect(document.documentElement.style.getPropertyValue('--color-secondary')).toBe('#445566')
  })
})
