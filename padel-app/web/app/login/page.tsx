import { login } from './actions';

export const dynamic = 'force-dynamic';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const { error, next } = await searchParams; // searchParams is async in Next 16

  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <form
        action={login}
        className="w-full max-w-sm rounded-xl border border-white/10 bg-white/[0.02] p-6"
      >
        <h1 className="text-xl font-semibold tracking-tight">
          Key Biscayne Court Booker
        </h1>
        <p className="mt-1 text-sm text-white/45">
          Enter the password to continue.
        </p>

        <input type="hidden" name="next" value={next ?? '/'} />
        <input
          name="password"
          type="password"
          required
          autoFocus
          placeholder="Password"
          className="mt-4 w-full rounded-md border border-white/15 bg-black px-3 py-2 text-white focus:border-accent focus:outline-none"
        />
        {error ? (
          <p className="mt-2 text-sm text-red-400">Incorrect password.</p>
        ) : null}

        <button
          type="submit"
          className="mt-4 w-full rounded-md bg-accent px-4 py-2 font-semibold text-black transition hover:opacity-90"
        >
          Unlock
        </button>
      </form>
    </div>
  );
}
