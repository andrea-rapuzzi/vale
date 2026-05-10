import { en } from './translations/en'
import { it } from './translations/it'

type DeepRecord = { [key: string]: string | DeepRecord }

const translations: Record<string, DeepRecord> = { en, it }

export type Lang = 'en' | 'it'

export function getLang(cookieString: string, acceptLanguage = ''): Lang {
  const match = cookieString.match(/(?:^|;\s*)vale-lang=([^;]+)/)
  if (match) {
    const val = match[1].trim()
    if (val === 'en' || val === 'it') return val
  }
  if (acceptLanguage.toLowerCase().startsWith('it')) return 'it'
  return 'en'
}

export function t(lang: string, key: string, vars: Record<string, string | number> = {}): string {
  const dict = translations[lang] ?? translations.en
  const keys = key.split('.')
  let val: string | DeepRecord | undefined = dict
  for (const k of keys) {
    if (typeof val !== 'object' || val === null) { val = undefined; break }
    val = (val as DeepRecord)[k]
  }
  if (typeof val !== 'string') {
    let fallback: string | DeepRecord | undefined = translations.en
    for (const k of keys) {
      if (typeof fallback !== 'object' || fallback === null) { fallback = undefined; break }
      fallback = (fallback as DeepRecord)[k]
    }
    val = typeof fallback === 'string' ? fallback : key
  }
  return (val as string).replace(/\{\{(\w+)\}\}/g, (_: string, k: string) => String(vars[k] ?? `{{${k}}}`))
}
