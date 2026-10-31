import { useEffect } from "react";
import { Link } from "react-router-dom";

/** Error page (mirrors error.html): code, message, back home. */
export function ErrorPage({
  code,
  message,
}: {
  code: number;
  message: string;
}) {
  useEffect(() => {
    document.title = `Error ${code} · EvolvingClass`;
  }, [code]);
  return (
    <>
      <h1>Something went wrong</h1>
      <div className="error">
        <p>
          <strong>{code}</strong> — {message}
        </p>
      </div>
      <p>
        <Link to="/home">Back to home</Link>
      </p>
    </>
  );
}
