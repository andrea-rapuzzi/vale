import { createServerClient, parseCookieHeader } from '@supabase/ssr'
import type { MiddlewareHandler } from 'astro'
import { getLang } from './lib/i18n'

function isPublicRoute(pathname: string): boolean {
  if (pathname === '/' || pathname === '/channels') return true
  if (pathname === '/login' || pathname === '/register') return true
  if (pathname === '/privacy') return true
  if (/^\/channel\/\d+/.test(pathname)) return true
  if (/^\/video\/\d+/.test(pathname)) return true
  if (/^\/scrape\/[a-zA-Z0-9-]+/.test(pathname)) return true
  return false
}

export const onRequest: MiddlewareHandler = async (context, next) => {
  const pathname = context.url.pathname
  const cookieHeader = context.request.headers.get('Cookie') ?? ''

  // Resolve language from cookie or Accept-Language header
  const lang = getLang(cookieHeader, context.request.headers.get('Accept-Language') ?? '')
  context.locals.lang = lang

  // Generate or read anonymous session token
  const existingSession = cookieHeader.match(/(?:^|;\s*)vale-session=([^;]+)/)?.[1]
  const sessionToken = existingSession ?? crypto.randomUUID()
  context.locals.sessionToken = sessionToken

  if (!existingSession) {
    context.cookies.set('vale-session', sessionToken, {
      path: '/',
      maxAge: 60 * 60 * 24 * 365,
      httpOnly: false,
      sameSite: 'lax',
    })
  }

  if (isPublicRoute(pathname)) {
    // Still try to hydrate auth data for logged-in users on public routes
    if (import.meta.env.PUBLIC_SUPABASE_URL && import.meta.env.PUBLIC_SUPABASE_ANON_KEY) {
      const supabase = createServerClient(
        import.meta.env.PUBLIC_SUPABASE_URL,
        import.meta.env.PUBLIC_SUPABASE_ANON_KEY,
        {
          cookies: {
            getAll() { return parseCookieHeader(cookieHeader) },
            setAll(cookiesToSet) {
              cookiesToSet.forEach(({ name, value, options }) =>
                context.cookies.set(name, value, options as Parameters<typeof context.cookies.set>[2]),
              )
            },
          },
        },
      )
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        context.locals.accessToken = session.access_token
        context.locals.userEmail = session.user.email ?? ''
      } else {
        context.locals.accessToken = ''
        context.locals.userEmail = ''
      }
    } else {
      context.locals.accessToken = ''
      context.locals.userEmail = ''
    }
    return next()
  }

  // Gated routes: require authentication
  if (!import.meta.env.PUBLIC_SUPABASE_URL || !import.meta.env.PUBLIC_SUPABASE_ANON_KEY) {
    return context.redirect('/login')
  }

  const supabase = createServerClient(
    import.meta.env.PUBLIC_SUPABASE_URL,
    import.meta.env.PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() { return parseCookieHeader(cookieHeader) },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            context.cookies.set(name, value, options as Parameters<typeof context.cookies.set>[2]),
          )
        },
      },
    },
  )

  const { data: { session } } = await supabase.auth.getSession()

  if (!session) {
    return context.redirect('/login')
  }

  // Check approval status against the backend.
  // Default to approved — only an explicit 403 means "not approved yet".
  const backendUrl = import.meta.env.BACKEND_URL ?? 'http://localhost:8000'
  let approved = true
  try {
    const res = await fetch(`${backendUrl}/api/auth/me`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      signal: AbortSignal.timeout(3000),
    })
    if (res.status === 403) approved = false
  } catch {
    // Backend unreachable — let through
  }

  if (!approved) {
    if (pathname === '/pending') return next()
    return context.redirect('/pending')
  }

  if (pathname === '/pending') {
    return context.redirect('/')
  }

  context.locals.accessToken = session.access_token
  context.locals.userEmail = session.user.email ?? ''

  return next()
}
