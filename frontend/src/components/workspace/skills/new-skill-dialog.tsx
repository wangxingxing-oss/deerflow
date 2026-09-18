"use client";

import { useEffect, useRef, useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/core/i18n/hooks";
import { useCreateSkill, useUploadSkill } from "@/core/skills/hooks";

export function NewSkillDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { mutateAsync: uploadSkill, isPending: isUploading } = useUploadSkill();
  const { mutateAsync: createSkill, isPending: isCreating } = useCreateSkill();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [tab, setTab] = useState("upload");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isPending = isUploading || isCreating;
  // Mirrors the backend rule: hyphen-case names become the skill directory name.
  const nameIsInvalid = name.trim() !== "" && !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name.trim());

  useEffect(() => {
    if (!open) {
      setTab("upload");
      setFile(null);
      setName("");
      setDescription("");
      setInstructions("");
      setError(null);
    }
  }, [open]);

  const handleUpload = async () => {
    if (!file) return;
    setError(null);
    try {
      const skill = await uploadSkill(file);
      toast.success(`${t.skills.installSuccess}: ${skill.name}`);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCreate = async () => {
    setError(null);
    try {
      const skill = await createSkill({ name, description, instructions });
      toast.success(`${t.skills.createSuccess}: ${skill.name}`);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t.skills.newSkill}</DialogTitle>
          <DialogDescription>{t.skills.newSkillHint}</DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList variant="line">
            <TabsTrigger value="upload">{t.skills.uploadTab}</TabsTrigger>
            <TabsTrigger value="manual">{t.skills.manualTab}</TabsTrigger>
          </TabsList>
        </Tabs>

        {tab === "upload" ? (
          <div className="flex flex-col gap-3">
            <p className="text-muted-foreground text-sm">{t.skills.uploadHint}</p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".skill,.zip"
              className="hidden"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
            <div className="flex items-center gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
              >
                {t.skills.chooseFile}
              </Button>
              <span className="text-muted-foreground truncate text-sm">
                {file ? file.name : t.skills.noFileSelected}
              </span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">{t.skills.nameLabel}</span>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t.skills.namePlaceholder}
              />
              {nameIsInvalid && (
                <span className="text-destructive text-xs">
                  {t.skills.nameInvalid}
                </span>
              )}
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.skills.descriptionLabel}
              </span>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t.skills.descriptionPlaceholder}
                rows={3}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">
                {t.skills.instructionsLabel}
              </span>
              <Textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder={t.skills.instructionsPlaceholder}
                rows={5}
              />
            </label>
          </div>
        )}

        {error && (
          <p className="text-destructive text-sm break-words">{error}</p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {t.common.cancel}
          </Button>
          {tab === "upload" ? (
            <Button
              type="button"
              onClick={() => void handleUpload()}
              disabled={!file || isPending}
            >
              {isUploading ? t.skills.installing : t.skills.installAction}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={() => void handleCreate()}
              disabled={
                !name.trim() ||
                !description.trim() ||
                nameIsInvalid ||
                isPending
              }
            >
              {isCreating ? t.skills.creating : t.skills.createAction}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
