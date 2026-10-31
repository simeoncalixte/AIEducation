import { useLocation } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";

const FLASK_BASE = (
  (import.meta.env.VITE_FLASK_URL as string | undefined) ??
  "http://127.0.0.1:5001"
).replace(/\/+$/, "");

/**
 * Stand-in for routes whose React page has not migrated yet. The Flask
 * route stays live until parity is verified, so link out to it; the
 * pilot session cookie carries over (same host).
 */
export function PlaceholderPage({ title }: { title: string }) {
  const location = useLocation();
  return (
    <>
      <h1>{title}</h1>
      <EmptyState>
        <>
          This page still lives in the Flask UI while its React migration
          ships.{" "}
          <a href={`${FLASK_BASE}${location.pathname}${location.search}`}>
            Open it in Flask
          </a>
          .
        </>
      </EmptyState>
    </>
  );
}
