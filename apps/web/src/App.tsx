import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/layout";
import { CoursesPage, NewCoursePage, WorkflowPage } from "./pages";


export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<CoursesPage />} />
        <Route path="workflow" element={<WorkflowPage />} />
        <Route path="new" element={<NewCoursePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
