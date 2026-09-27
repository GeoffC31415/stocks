import { type ReactNode } from 'react';
import { useAuth } from './AuthProvider';
import { SignIn } from './SignIn';
export function AuthGate({children}: {children: ReactNode}) {
  const { session, loading, error, refresh, logout, loggingOut, logoutError } = useAuth();
  if (loading) return <main><p role="status">Checking session…</p></main>;
  if (error) return <main><p role="alert">{error}</p><button onClick={() => void refresh()}>Retry session</button></main>;
  if (loggingOut) return <main className="auth-page"><p role="status">Logging out…</p></main>;
  if (logoutError) return <main className="auth-page"><p role="alert">{logoutError}</p><button onClick={() => void logout()}>Retry logout</button></main>;
  if (!session?.authenticated) return <SignIn />;
  if (session.mode === 'local') return <>{children}</>;
  return <>
    {session.mode === 'basic' && <aside className="auth-migration">
      <p>Set up and test a passkey. Your old password remains required until an administrator completes the cutoff.</p>
      {session.passkey_authenticated && <p>Passkey verified for this session; this site is not yet passwordless.</p>}
    </aside>}
    {children}
  </>;
}
