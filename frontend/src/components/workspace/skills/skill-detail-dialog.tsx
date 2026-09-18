"use client";

import { FileTextIcon, FolderIcon } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { useSkillFile, useSkillFiles } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function SkillDetailDialog({
  skillName,
  open,
  onOpenChange,
}: {
  skillName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const { data, isLoading, error } = useSkillFiles(open ? skillName : null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const fileQuery = useSkillFile(
    open ? skillName : null,
    open ? selectedPath : null,
  );

  const entries = useMemo(() => data?.files ?? [], [data]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setSelectedPath(null);
        onOpenChange(next);
      }}
    >
      <DialogContent
        className="flex h-[75vh] max-h-[calc(100vh-2rem)] flex-col sm:max-w-4xl md:max-w-5xl"
        aria-describedby={undefined}
      >
        <DialogHeader className="gap-1">
          <DialogTitle>{skillName}</DialogTitle>
          <DialogDescription>{t.skills.filesTitle}</DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[minmax(0,340px)_1fr]">
          <ScrollArea className="bg-sidebar min-h-0 rounded-lg border">
            <div className="flex flex-col p-2">
              {isLoading ? (
                <p className="text-muted-foreground p-2 text-sm">
                  {t.common.loading}
                </p>
              ) : error ? (
                <p className="text-destructive p-2 text-sm break-words">
                  {error.message}
                </p>
              ) : entries.length === 0 ? (
                <p className="text-muted-foreground p-2 text-sm">
                  {t.skills.filesEmpty}
                </p>
              ) : (
                entries.map((entry) => {
                  const depth = entry.path.split("/").length - 1;
                  const name = entry.path.split("/").pop() ?? entry.path;
                  const isDir = entry.type === "dir";
                  return (
                    <button
                      key={`${entry.type}:${entry.path}`}
                      type="button"
                      disabled={isDir}
                      onClick={() => setSelectedPath(entry.path)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm",
                        isDir
                          ? "text-foreground cursor-default"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        selectedPath === entry.path &&
                          "bg-primary text-primary-foreground hover:bg-primary",
                      )}
                      style={{ paddingLeft: `${depth * 14 + 8}px` }}
                    >
                      {isDir ? (
                        <FolderIcon className="size-3.5 shrink-0" />
                      ) : (
                        <FileTextIcon className="size-3.5 shrink-0" />
                      )}
                      <span className="truncate">{name}</span>
                      {!isDir && (
                        <span className="text-muted-foreground/70 ml-auto shrink-0 text-xs">
                          {formatSize(entry.size)}
                        </span>
                      )}
                    </button>
                  );
                })
              )}
              {data?.truncated && (
                <p className="text-muted-foreground p-2 text-xs">
                  {t.skills.filesTruncated}
                </p>
              )}
            </div>
          </ScrollArea>

          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <span className="truncate text-sm font-medium">
                {selectedPath ?? t.skills.selectFileHint}
              </span>
              {fileQuery.data && (
                <span className="text-muted-foreground ml-auto text-xs">
                  {formatSize(fileQuery.data.size)}
                </span>
              )}
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="p-3">
                {fileQuery.isLoading ? (
                  <p className="text-muted-foreground text-sm">
                    {t.common.loading}
                  </p>
                ) : fileQuery.error ? (
                  <p className="text-destructive text-sm break-words">
                    {fileQuery.error.message}
                  </p>
                ) : fileQuery.data?.binary ? (
                  <p className="text-muted-foreground text-sm">
                    {t.skills.binaryFile}
                  </p>
                ) : fileQuery.data?.content != null ? (
                  <>
                    <pre className="text-xs whitespace-pre-wrap">
                      {fileQuery.data.content}
                    </pre>
                    {fileQuery.data.truncated && (
                      <p className="text-muted-foreground mt-3 text-xs">
                        {t.skills.contentTruncated}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-muted-foreground text-sm">
                    {t.skills.selectFileHint}
                  </p>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
