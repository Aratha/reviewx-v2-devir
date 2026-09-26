import type {ReactNode} from 'react';
import {Button} from './Button';
import {Dialog} from './Dialog';

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog
      title={title}
      size="sm"
      onClose={busy ? undefined : onCancel}
      busy={busy}
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Vazgeç
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} disabled={busy} busy={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
