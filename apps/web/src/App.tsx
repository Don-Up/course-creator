import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/layout";
import { CourseWorkspace, Dashboard, NewCourse } from "./pages/course-pages";
import { WorkflowPage } from "./pages/workflow-page";
import { RunList, RunWorkspace } from "./features/run/run-workspace";


export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="workflow" element={<WorkflowPage />} />
        <Route path="new" element={<NewCourse />} />
        <Route path="courses/:slug" element={<CourseWorkspace />} />
        <Route path="runs" element={<RunList />} />
        <Route path="runs/:runId" element={<RunWorkspace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
