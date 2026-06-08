'use client';

// Shows a pending label while the (slow ~15s) verify action runs.
import { useFormStatus } from 'react-dom';

export function SubmitButton({
  idle,
  pending,
  className,
}: {
  idle: string;
  pending: string;
  className?: string;
}) {
  const { pending: isPending } = useFormStatus();
  return (
    <button type="submit" disabled={isPending} className={className}>
      {isPending ? pending : idle}
    </button>
  );
}
