'use server';

import { execFile } from 'node:child_process';
import path from 'node:path';
import { promisify } from 'node:util';
import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { createAccount, updateAccount, type AccountInput } from '@/lib/db';

const pExecFile = promisify(execFile);

function parse(fd: FormData): AccountInput {
  const num = (k: string) => {
    const v = String(fd.get(k) ?? '').trim();
    return v ? Number(v) : null;
  };
  const str = (k: string) => {
    const v = String(fd.get(k) ?? '').trim();
    return v || null;
  };
  return {
    label: String(fd.get('label') ?? '').trim(),
    email: String(fd.get('email') ?? '').trim(),
    password: String(fd.get('password') ?? ''),
    rckb_user_id: num('rckb_user_id'),
    card_id: num('card_id'),
    card_last_four: str('card_last_four'),
    card_brand: str('card_brand'),
    guest_user_id: num('guest_user_id'),
    guest_name: str('guest_name'),
    is_default: fd.get('is_default') === 'on',
  };
}

export async function updateAccountAction(fd: FormData) {
  const id = Number(fd.get('id'));
  if (!id) throw new Error('Missing account id.');
  const a = parse(fd);
  if (!a.label || !a.email) {
    throw new Error('Account name and email are required.');
  }
  updateAccount(id, a); // blank password = keep current
  revalidatePath('/accounts');
  revalidatePath('/');
}

// Log in to RCKB (headless is bot-blocked, so the Python discoverer runs headed),
// auto-fetch the account's user_id + card + guest, then save it. Books nothing.
export async function verifyAndAddAccount(fd: FormData) {
  const label = String(fd.get('label') ?? '').trim();
  const email = String(fd.get('email') ?? '').trim();
  const password = String(fd.get('password') ?? '');
  const fail = (m: string): never =>
    redirect('/accounts?error=' + encodeURIComponent(m));

  if (!label || !email || !password) {
    fail('Account name, email, and password are required.');
  }

  const projectRoot = path.resolve(process.cwd(), '..'); // padel-app
  const python = path.resolve(projectRoot, '..', 'padel-booking', '.venv', 'bin', 'python');
  const script = path.resolve(projectRoot, 'worker', 'discover.py');

  let stdout = '';
  try {
    const r = await pExecFile(python, [script, '--headed'], {
      env: { ...process.env, RCKB_EMAIL: email, RCKB_PASSWORD: password },
      timeout: 120_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    stdout = r.stdout;
  } catch (e) {
    // Non-zero exit still carries stdout (with our sentinel + JSON).
    stdout = (e as { stdout?: string })?.stdout ?? '';
  }

  const marker = '@@DISCOVER_RESULT@@';
  const at = stdout.indexOf(marker);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let result: any = null;
  if (at >= 0) {
    try {
      result = JSON.parse(stdout.slice(at + marker.length));
    } catch {
      /* fall through to error */
    }
  }

  if (!result) {
    fail('Verification could not run. Make sure macOS allowed the browser window, then retry.');
  }
  if (!result.ok) {
    fail(result.error || 'Verification failed — check the email and password.');
  }
  if (!result.user_id) {
    fail('Logged in, but could not read the account details.');
  }

  createAccount({
    label,
    email,
    password,
    rckb_user_id: result.user_id,
    card_id: result.card_id ?? null,
    card_last_four: result.card_last_four ?? null,
    card_brand: result.card_brand ?? null,
    guest_user_id: result.guest_user_id ?? null,
    guest_name: result.guest_name ?? 'A',
    is_default: false,
  });
  revalidatePath('/accounts');
  revalidatePath('/');
  redirect('/accounts?added=' + encodeURIComponent(label));
}
