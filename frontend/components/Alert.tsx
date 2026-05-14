type Props = { type: "success" | "error"; message: string };

export default function Alert({ type, message }: Props) {
  const styles =
    type === "success"
      ? "bg-green-50 border-green-300 text-green-800"
      : "bg-red-50 border-red-300 text-red-800";

  return (
    <div className={`border rounded-md px-4 py-3 text-sm ${styles}`}>
      {message}
    </div>
  );
}
