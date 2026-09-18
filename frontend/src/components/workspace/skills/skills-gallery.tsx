"use client";

import { FolderOpenIcon, PlusIcon, SparklesIcon, Trash2Icon } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/core/i18n/hooks";
import { useDeleteSkill, useEnableSkill, useSkills } from "@/core/skills/hooks";
import type { Skill } from "@/core/skills/type";
import { env } from "@/env";

import { NewSkillDialog } from "./new-skill-dialog";
import { SkillDetailDialog } from "./skill-detail-dialog";

export function SkillsGallery() {
  const { t } = useI18n();
  const { skills, isLoading, error } = useSkills();
  const { mutate: enableSkill } = useEnableSkill();
  const deleteSkill = useDeleteSkill();
  const [category, setCategory] = useState<string>("custom");
  const [newSkillOpen, setNewSkillOpen] = useState(false);
  const [detailSkill, setDetailSkill] = useState<Skill | null>(null);
  const [menuSkill, setMenuSkill] = useState<Skill | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);

  const filteredSkills = useMemo(
    () => skills.filter((skill) => skill.category === category),
    [skills, category],
  );

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSkill.mutateAsync(deleteTarget.name);
      toast.success(t.skills.deleteSuccess);
      setDeleteTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex size-full flex-col">
      <NewSkillDialog open={newSkillOpen} onOpenChange={setNewSkillOpen} />
      <SkillDetailDialog
        skillName={detailSkill?.name ?? null}
        open={detailSkill !== null}
        onOpenChange={(open) => {
          if (!open) setDetailSkill(null);
        }}
      />
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.skills.deleteConfirmTitle}</DialogTitle>
            <DialogDescription>
              {t.skills.deleteConfirmDescription(deleteTarget?.name ?? "")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteSkill.isPending}
            >
              {t.common.cancel}
            </Button>
            <Button
              variant="destructive"
              onClick={() => void handleDelete()}
              disabled={deleteSkill.isPending}
            >
              {t.skills.delete}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Page header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">{t.skills.title}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {t.skills.description}
          </p>
        </div>
        <Button onClick={() => setNewSkillOpen(true)}>
          <PlusIcon className="mr-1.5 h-4 w-4" />
          {t.skills.newSkill}
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
          <Tabs value={category} onValueChange={setCategory}>
            <TabsList variant="line">
              <TabsTrigger value="custom">{t.common.custom}</TabsTrigger>
              <TabsTrigger value="public">{t.common.public}</TabsTrigger>
            </TabsList>
          </Tabs>
          {isLoading ? (
            <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
              {t.common.loading}
            </div>
          ) : error ? (
            <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
              {error.message}
            </div>
          ) : filteredSkills.length === 0 ? (
            category === "custom" ? (
              <EmptySkills onCreateSkill={() => setNewSkillOpen(true)} />
            ) : (
              <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
                {t.common.noResults}
              </div>
            )
          ) : (
            filteredSkills.map((skill) => (
              <DropdownMenu
                key={skill.name}
                open={menuSkill?.name === skill.name}
                onOpenChange={(open) => setMenuSkill(open ? skill : null)}
              >
                <Item
                  className="hover:bg-muted/40 relative w-full cursor-pointer transition-colors"
                  variant="outline"
                  onClick={() => setDetailSkill(skill)}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    setMenuSkill(skill);
                  }}
                >
                  <DropdownMenuTrigger asChild>
                    <span
                      className="absolute right-4 bottom-4 h-0 w-0"
                      aria-hidden
                    />
                  </DropdownMenuTrigger>
                  <ItemContent>
                    <ItemTitle>
                      <div className="flex items-center gap-2">{skill.name}</div>
                    </ItemTitle>
                    <ItemDescription className="line-clamp-4">
                      {skill.description}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <span className="text-muted-foreground hidden items-center gap-1 text-xs sm:flex">
                      <FolderOpenIcon className="size-3.5" />
                      {t.skills.viewFiles}
                    </span>
                    <Switch
                      checked={skill.enabled}
                      disabled={env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"}
                      onClick={(event) => event.stopPropagation()}
                      onCheckedChange={(checked) =>
                        enableSkill({ skillName: skill.name, enabled: checked })
                      }
                    />
                  </ItemActions>
                </Item>
                <DropdownMenuContent align="end">
                  {skill.category === "custom" ? (
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => setDeleteTarget(skill)}
                    >
                      <Trash2Icon />
                      {t.skills.delete}
                    </DropdownMenuItem>
                  ) : (
                    <DropdownMenuItem disabled>
                      <Trash2Icon />
                      {t.skills.builtinNotDeletable}
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function EmptySkills({ onCreateSkill }: { onCreateSkill: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
      <div className="bg-muted flex h-14 w-14 items-center justify-center rounded-full">
        <SparklesIcon className="text-muted-foreground h-7 w-7" />
      </div>
      <div>
        <p className="font-medium">{t.skills.emptyTitle}</p>
        <p className="text-muted-foreground mt-1 text-sm">
          {t.skills.emptyDescription}
        </p>
      </div>
      <Button variant="outline" className="mt-2" onClick={onCreateSkill}>
        <PlusIcon className="mr-1.5 h-4 w-4" />
        {t.skills.newSkill}
      </Button>
    </div>
  );
}
