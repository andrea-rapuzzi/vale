import { createServerClient, parseCookieHeader } from '@supabase/ssr'
import type { MiddlewareHandler } from 'astro'

export const onRequest: MiddlewareHandler = async (context, next) => {
  const pathname = context.url.pathname

  // Pages that don't require auth
  if (pathname === '/login' || pathname === '/register') {
    return next()
  }

  const supabase = createServerClient(
    import.meta.env.PUBLIC_SUPABASE_URL,
    import.meta.env.PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return parseCookieHeader(context.request.headers.get('Cookie') ?? '')
        },
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

  // Check approval status against the backend
  const backendUrl = import.meta.env.BACKEND_URL ?? 'http://localhost:8000'
  let approved = false
  try {
    const res = await fetch(`${backendUrl}/api/auth/me`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      signal: AbortSignal.timeout(3000),
    })
    approved = res.ok
  } catch {
    // Backend unreachable — let through rather than blocking the user
    approved = true
  }

  if (!approved) {
    if (pathname === '/pending') return next()
    return context.redirect('/pending')
  }

  // If approved and trying to visit /pending, redirect home
  if (pathname === '/pending') {
    return context.redirect('/')
  }

  context.locals.accessToken = session.access_token
  context.locals.userEmail = session.user.email ?? ''

  return next()
}
