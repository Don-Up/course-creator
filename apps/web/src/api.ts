export type Health = {
  status: "ok";
  service: string;
};

export type Course = {
  slug: string;
  title: string;
  description: string;
  href: string;
  chapters: number;
  duration: string;
  status: string;
};

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  courses: () => request<{ items: Course[] }>("/api/courses"),
};
