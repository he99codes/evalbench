import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * Accessible modal built on the native <dialog> element, which provides focus
 * trapping, Escape-to-close and an inert background.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className="m-auto w-full max-w-lg rounded-lg p-0 shadow-xl backdrop:bg-slate-900/40"
    >
      {open && (
        <div className="flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
            <h2 id={titleId} className="text-base font-semibold text-slate-900">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close dialog"
              className="rounded p-1 text-slate-500 hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>
          <div className="px-5 py-4">{children}</div>
          {footer && (
            <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">{footer}</div>
          )}
        </div>
      )}
    </dialog>
  );
}
