"use client";

type ToastProps = {
  kind: "error" | "success";
  message: string;
};

const colors: Record<ToastProps["kind"], string> = {
  error: "#7f1d1d",
  success: "#14532d",
};

export function Toast({ kind, message }: ToastProps): JSX.Element {
  return (
    <div
      role="alert"
      style={{
        background: colors[kind],
        color: "#fff",
        borderRadius: 8,
        padding: "10px 12px",
        marginTop: 12,
        fontSize: 14,
      }}
    >
      {message}
    </div>
  );
}
