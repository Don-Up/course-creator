import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/layout";
import { ChapterWorkspace, CourseWorkspace, Dashboard, NewCourse } from "./pages/course-pages";
import { WorkflowOverview } from "./pages/workflow-overview";
import { RunWorkspace } from "./features/run/run-workspace";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/new" element={<NewCourse />} />
        <Route path="/workflow" element={<WorkflowOverview />} />
        <Route path="/courses/:slug" element={<CourseWorkspace />} />
        <Route path="/courses/:slug/chapters/:key" element={<ChapterWorkspace />} />
        <Route path="/runs/:runId" element={<RunWorkspace />} />
      </Routes>
    </Layout>
  );
}
