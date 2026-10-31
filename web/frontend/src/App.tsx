import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ErrorPage } from "./components/ErrorPage";
import { Layout } from "./Layout";
import { AssignmentProgressPage } from "./pages/AssignmentProgressPage";
import { AssignmentsPage } from "./pages/AssignmentsPage";
import { AuditPage } from "./pages/AuditPage";
import { BriefComposerPage } from "./pages/BriefComposerPage";
import { BriefingPage } from "./pages/BriefingPage";
import { ChallengePage } from "./pages/ChallengePage";
import { DebriefPage } from "./pages/DebriefPage";
import { DirectivesPage } from "./pages/DirectivesPage";
import { EditDirectivePage } from "./pages/EditDirectivePage";
import { EditDraftPage } from "./pages/EditDraftPage";
import { HomePage } from "./pages/HomePage";
import { LessonsPage } from "./pages/LessonsPage";
import { LoginPage } from "./pages/LoginPage";
import { LogoutPage } from "./pages/LogoutPage";
import { ReviewDossierPage } from "./pages/ReviewDossierPage";
import { ReviewQueuesPage } from "./pages/ReviewQueuesPage";
import { SessionProvider, useSession } from "./session";

/** Root path (mirrors /): logged out goes to login, else home. */
function IndexRoute() {
  const { user, loading } = useSession();
  if (loading) {
    return <p className="loading">Loading…</p>;
  }
  return <Navigate to={user === null ? "/login" : "/home"} replace />;
}

/**
 * Client routes for every current Flask page path. Migrated pages
 * render their React implementation; the rest render a placeholder
 * linking to the live Flask route until their page task ships.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<IndexRoute />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/logout" element={<LogoutPage />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/play/:assignmentId" element={<BriefingPage />} />
        <Route
          path="/play/attempt/:attemptId/challenge/:index"
          element={<ChallengePage />}
        />
        <Route
          path="/play/attempt/:attemptId/debrief"
          element={<DebriefPage />}
        />
        <Route path="/review" element={<ReviewQueuesPage />} />
        <Route
          path="/review/:kind/:versionId"
          element={<ReviewDossierPage />}
        />
        <Route
          path="/review/:kind/:versionId/edit"
          element={<EditDraftPage />}
        />
        <Route path="/lessons" element={<LessonsPage />} />
        <Route
          path="/lessons/:lessonId/brief"
          element={<BriefComposerPage />}
        />
        <Route
          path="/lessons/:lessonId/directives"
          element={<DirectivesPage />}
        />
        <Route
          path="/directives/:directiveId/edit"
          element={<EditDirectivePage />}
        />
        <Route path="/assignments" element={<AssignmentsPage />} />
        <Route
          path="/assignments/:assignmentId"
          element={<AssignmentProgressPage />}
        />
        <Route path="/audit" element={<AuditPage />} />
        <Route
          path="*"
          element={
            <ErrorPage code={404} message="This page does not exist." />
          }
        />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </SessionProvider>
  );
}
