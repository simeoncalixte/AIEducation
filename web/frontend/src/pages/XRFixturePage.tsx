import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { XRFixtureStage } from "../components/XRFixtureStage";

/**
 * Fixture volcano stage for the immersive spike (SCRUM-22). Public:
 * the pilot device opens this URL directly, with no login needed.
 *
 * With ?attempt=<id>&stage=<stageVersionId> (SCRUM-127) the stage
 * links to the attempt: launch gating, telemetry, and checkpoint
 * save/resume activate. The full E2E wiring (SCRUM-35/128) serves
 * one challenge in scene (?challenge=<n>, default 1): prompt,
 * hints, goal feedback, completion, and retry, with verdicts from
 * the record. Guides come from the served challenge view with web
 * identity.
 */
export function XRFixturePage() {
  const [params] = useSearchParams();
  useEffect(() => {
    document.title = "XR Fixture · EvolvingClass";
  }, []);

  const attempt = Number(params.get("attempt"));
  const stage = Number(params.get("stage"));
  const challengeParam = Number(params.get("challenge"));
  const linked = Number.isInteger(attempt) && Number.isInteger(stage);
  const challengeNo =
    Number.isInteger(challengeParam) && challengeParam >= 1
      ? challengeParam
      : 1;

  return (
    <>
      <h1>XR fixture stage</h1>
      <p className="muted">
        Static spike fixture: poster first paint, live diorama, device
        capabilities, and an AR session button. Drag to orbit, scroll or
        pinch to zoom.
        {linked &&
          " Linked to an attempt: challenges play in scene, progress " +
            "saves and resumes."}
      </p>
      {linked ? (
        <XRFixtureStage
          attemptId={attempt}
          stageVersionId={stage}
          challengeIndex={challengeNo}
        />
      ) : (
        <XRFixtureStage />
      )}
    </>
  );
}
