import { getBackendBaseURL } from "@/core/config";

import type { Skill } from "./type";

export async function loadSkills() {
  const skills = await fetch(`${getBackendBaseURL()}/api/skills`);
  const json = await skills.json();
  return json.skills as Skill[];
}

export async function enableSkill(skillName: string, enabled: boolean) {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${skillName}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        enabled,
      }),
    },
  );
  return response.json();
}

export interface InstallSkillRequest {
  thread_id: string;
  path: string;
}

export interface InstallSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

export async function installSkill(
  request: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/install`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    // Handle HTTP error responses (4xx, 5xx)
    const errorData = await response.json().catch(() => ({}));
    const errorMessage =
      errorData.detail ?? `HTTP ${response.status}: ${response.statusText}`;
    return {
      success: false,
      skill_name: "",
      message: errorMessage,
    };
  }

  return response.json();
}

async function readErrorDetail(response: Response, fallback: string) {
  const data = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  const detail = data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return `${fallback} (HTTP ${response.status})`;
}

export interface CreateSkillRequest {
  name: string;
  description: string;
  instructions?: string;
}

/** Create a new custom skill from a name, description and optional instructions. */
export async function createSkill(request: CreateSkillRequest): Promise<Skill> {
  const response = await fetch(`${getBackendBaseURL()}/api/skills/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to create skill"));
  }

  return response.json();
}

/** Install a custom skill from an uploaded .skill or .zip archive. */
export async function uploadSkillPackage(file: File): Promise<Skill> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${getBackendBaseURL()}/api/skills/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to upload skill"));
  }

  return response.json();
}

export interface DeleteSkillResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

/** Delete a custom skill (built-in skills can only be disabled). */
export async function deleteSkill(
  skillName: string,
): Promise<DeleteSkillResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${encodeURIComponent(skillName)}`,
    { method: "DELETE" },
  );

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to delete skill"));
  }

  return response.json();
}

export interface SkillFileEntry {
  path: string;
  type: "file" | "dir";
  size: number;
}export interface SkillFilesResponse {
  name: string;
  category: string;
  files: SkillFileEntry[];
  truncated: boolean;
}

export interface SkillFileContent {
  path: string;
  size: number;
  binary: boolean;
  truncated: boolean;
  content: string | null;
}

/** List the files and directories inside a skill. */
export async function loadSkillFiles(
  skillName: string,
): Promise<SkillFilesResponse> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${encodeURIComponent(skillName)}/files`,
  );

  if (!response.ok) {
    throw new Error(
      await readErrorDetail(response, "Failed to load skill files"),
    );
  }

  return response.json();
}

/** Read a single text file from inside a skill directory. */
export async function loadSkillFile(
  skillName: string,
  path: string,
): Promise<SkillFileContent> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/skills/${encodeURIComponent(skillName)}/file?path=${encodeURIComponent(path)}`,
  );

  if (!response.ok) {
    throw new Error(await readErrorDetail(response, "Failed to read skill file"));
  }

  return response.json();
}
