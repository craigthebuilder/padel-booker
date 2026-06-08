import Link from 'next/link';
import { listAccounts, type SafeAccount } from '@/lib/db';
import { updateAccountAction, verifyAndAddAccount } from './actions';
import { SubmitButton } from './SubmitButton';

export const dynamic = 'force-dynamic';

function Field({
  name,
  label,
  defaultValue,
  type = 'text',
  required = false,
  placeholder,
}: {
  name: string;
  label: string;
  defaultValue?: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-white/70">{label}</span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? ''}
        required={required}
        placeholder={placeholder}
        className="rounded-md border border-white/15 bg-black px-3 py-2 text-white focus:border-accent focus:outline-none"
      />
    </label>
  );
}

// Simple add: name + email + password → "Verify and add" runs the discovery.
function AddAccountForm() {
  return (
    <form
      action={verifyAndAddAccount}
      className="rounded-xl border border-white/10 bg-white/[0.02] p-5"
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <Field name="label" label="Account name" required />
        <Field name="email" label="Email" type="email" required />
        <Field name="password" label="Password" type="password" required />
      </div>
      <p className="mt-3 text-xs text-white/45">
        On verify, a browser window briefly opens to log in and auto-fetch this
        account’s user ID, card, and guest. Nothing is booked.
      </p>
      <SubmitButton
        idle="Verify and add account"
        pending="Verifying… (a browser window will open) "
        className="mt-4 rounded-md bg-accent px-4 py-2 font-semibold text-black transition hover:opacity-90 disabled:opacity-60"
      />
    </form>
  );
}

// Full edit form (manual fields) for an existing account.
function EditAccountForm({ account }: { account: SafeAccount }) {
  const numStr = (n: number | null | undefined) => (n != null ? String(n) : '');
  return (
    <form
      action={updateAccountAction}
      className="rounded-xl border border-white/10 bg-white/[0.02] p-5"
    >
      <input type="hidden" name="id" value={account.id} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field name="label" label="Account name" defaultValue={account.label} required />
        <Field name="email" label="Email" type="email" defaultValue={account.email} required />
        <Field
          name="password"
          label="Password (blank = keep current)"
          type="password"
          placeholder="••••••••"
        />
        <label className="flex items-center gap-2 self-end text-sm">
          <input
            type="checkbox"
            name="is_default"
            defaultChecked={account.is_default === 1}
            className="size-4 accent-[var(--accent)]"
          />
          <span className="text-white/70">Default account</span>
        </label>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-white/40">
          Booking details (auto-filled on verify — edit if needed)
        </summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field name="rckb_user_id" label="User ID" type="number" defaultValue={numStr(account.rckb_user_id)} />
          <Field name="card_id" label="Card ID" type="number" defaultValue={numStr(account.card_id)} />
          <Field name="card_last_four" label="Card last 4" defaultValue={account.card_last_four ?? ''} />
          <Field name="card_brand" label="Card brand" defaultValue={account.card_brand ?? ''} />
          <Field name="guest_user_id" label="Guest user ID" type="number" defaultValue={numStr(account.guest_user_id)} />
          <Field name="guest_name" label="Guest name" defaultValue={account.guest_name ?? ''} />
        </div>
      </details>

      <button
        type="submit"
        className="mt-4 rounded-md bg-accent px-4 py-2 font-semibold text-black transition hover:opacity-90"
      >
        Save changes
      </button>
    </form>
  );
}

export default async function AccountsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; added?: string }>;
}) {
  const { error, added } = await searchParams;
  const accounts = listAccounts();

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Accounts</h1>
        <Link
          href="/"
          className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-white/80 transition hover:border-accent hover:text-accent"
        >
          ← Booker
        </Link>
      </header>

      {error ? (
        <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      ) : null}
      {added ? (
        <div className="mb-6 rounded-lg border border-accent/30 bg-accent/10 p-3 text-sm text-accent">
          Added “{added}”.
        </div>
      ) : null}

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">Add account</h2>
        <AddAccountForm />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">
          Your accounts ({accounts.length})
        </h2>
        <div className="flex flex-col gap-5">
          {accounts.map((a) => (
            <div key={a.id}>
              <div className="mb-2 text-sm text-white/50">
                {a.label}
                {a.is_default === 1 ? (
                  <span className="text-accent"> · default</span>
                ) : null}
              </div>
              <EditAccountForm account={a} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
