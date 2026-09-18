"use client";

import { SparklesIcon } from "lucide-react";
import { useMemo } from "react";

import {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
  usePromptInputController,
} from "@/components/ai-elements/prompt-input";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/core/i18n/hooks";
import { useSkills } from "@/core/skills/hooks";
import { cn } from "@/lib/utils";

/**
 * Quick skill picker shown next to the mode selector. Picking a skill writes an
 * explicit "use this skill" directive into the input box, which is how the
 * agent is told to load a specific skill (see <skill_system> in the prompt).
 */
export function SkillQuickPicker({ disabled }: { disabled?: boolean }) {
  const { t } = useI18n();
  const { skills } = useSkills();
  const controller = usePromptInputController();

  const customSkills = useMemo(
    () => skills.filter((skill) => skill.category === "custom"),
    [skills],
  );

  const handleSelect = (name: string) => {
    const directive = t.inputBox.useSkillDirective(name);
    const current = controller.textInput.value.trim();
    controller.textInput.setInput(
      current ? `${directive}\n\n${current}` : `${directive}\n`,
    );
    // Keep focus in the textarea with the caret at the end of the new text.
    const textarea = document.querySelector("textarea");
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }
  };

  return (
    <PromptInputActionMenu>
      <PromptInputActionMenuTrigger
        className="gap-1! px-2!"
        disabled={disabled}
      >
        <SparklesIcon className="size-3" />
        <span className="text-xs font-normal">{t.skills.title}</span>
      </PromptInputActionMenuTrigger>
      <PromptInputActionMenuContent className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground text-xs">
            {t.skills.useSkillLabel}
          </DropdownMenuLabel>
          {customSkills.length === 0 ? (
            <div className="text-muted-foreground px-2 py-2 text-xs">
              {t.skills.useSkillEmpty}
            </div>
          ) : (
            customSkills.map((skill) => (
              <PromptInputActionMenuItem
                key={skill.name}
                disabled={!skill.enabled}
                onSelect={() => handleSelect(skill.name)}
                className={cn(
                  "flex flex-col items-start gap-0.5",
                  !skill.enabled && "opacity-60",
                )}
              >
                <span className="text-xs font-medium">
                  {skill.name}
                  {!skill.enabled && ` (${t.skills.disabledLabel})`}
                </span>
                <span className="text-muted-foreground line-clamp-2 text-[11px] font-normal">
                  {skill.description}
                </span>
              </PromptInputActionMenuItem>
            ))
          )}
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}
