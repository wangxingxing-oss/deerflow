import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { CreateSkillRequest } from "./api";
import {
  createSkill,
  deleteSkill,
  enableSkill,
  loadSkillFile,
  loadSkillFiles,
  uploadSkillPackage,
} from "./api";

import { loadSkills } from ".";

export function useSkills() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["skills"],
    queryFn: () => loadSkills(),
  });
  return { skills: data ?? [], isLoading, error };
}

export function useEnableSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      skillName,
      enabled,
    }: {
      skillName: string;
      enabled: boolean;
    }) => {
      await enableSkill(skillName, enabled);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useCreateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateSkillRequest) => createSkill(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useUploadSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadSkillPackage(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillName: string) => deleteSkill(skillName),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
}

export function useSkillFiles(skillName: string | null | undefined) {
  return useQuery({
    queryKey: ["skills", skillName, "files"],
    queryFn: () => loadSkillFiles(skillName!),
    enabled: Boolean(skillName),
  });
}

export function useSkillFile(
  skillName: string | null | undefined,
  path: string | null | undefined,
) {
  return useQuery({
    queryKey: ["skills", skillName, "file", path],
    queryFn: () => loadSkillFile(skillName!, path!),
    enabled: Boolean(skillName && path),
  });
}
