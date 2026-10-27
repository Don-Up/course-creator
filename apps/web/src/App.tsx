import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/layout";
import { CourseWorkspace, Dashboard, NewCourse, WorkflowPage } from "./pages/course-pages";


export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="workflow" element={<WorkflowPage />} />
        <Route path="new" element={<NewCourse />} />
        <Route path="courses/:slug" element={<CourseWorkspace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
