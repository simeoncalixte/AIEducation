import { useEffect } from "react";
import { XRFixtureStage } from "../components/XRFixtureStage";

/**
 * Fixture volcano stage for the immersive spike (SCRUM-22). Public:
 * the pilot device opens this URL directly, with no login needed.
 */
export function XRFixturePage() {
  useEffect(() => {
    document.title = "XR Fixture · EvolvingClass";
  }, []);

  return (
    <>
      <h1>XR fixture stage</h1>
      <p className="muted">
        Static spike fixture: poster first paint, live diorama, device
        capabilities, and an AR session button. Drag to orbit, scroll or
        pinch to zoom.
      </p>
      <XRFixtureStage />
    </>
  );
}
