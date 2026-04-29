import { createServerClient, parseCookieHeader } from '@supabase/ssr'
import type { MiddlewareHandler } from 'astro'

const PUBLIC_PATHS = new Set(['/login', '/register', '/pending'])

export const onRequest: MiddlewareHandler = async (context, next) => {
  const pathname = context.url.pathname

  // Skip auth check for public pages
  if (PUBLIC_PATHS.has(pathname)) {
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

  context.locals.accessToken = session.access_token
  context.locals.userEmail = session.user.email ?? ''

  return next()
}
