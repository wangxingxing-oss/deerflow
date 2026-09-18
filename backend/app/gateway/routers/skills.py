import json
import logging
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from deerflow.skills import Skill, load_skills
from deerflow.skills.loader import get_skills_root_path
from deerflow.skills.validation import _validate_skill_frontmatter

logger = logging.getLogger(__name__)

# Guards for browsing skill contents from the API.
MAX_LISTED_ENTRIES = 2000
MAX_PREVIEW_BYTES = 200 * 1024


def _is_unsafe_zip_member(info: zipfile.ZipInfo) -> bool:
    """Return True if the zip member path is absolute or attempts directory traversal."""
    name = info.filename
    if not name:
        return False
    path = Path(name)
    if path.is_absolute():
        return True
    if ".." in path.parts:
        return True
    return False


def _is_symlink_member(info: zipfile.ZipInfo) -> bool:
    """Detect symlinks based on the external attributes stored in the ZipInfo."""
    # Upper 16 bits of external_attr contain the Unix file mode when created on Unix.
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _safe_extract_skill_archive(
    zip_ref: zipfile.ZipFile,
    dest_path: Path,
    max_total_size: int = 512 * 1024 * 1024,
) -> None:
    """Safely extract a skill archive into dest_path with basic protections.

    Protections:
    - Reject absolute paths and directory traversal (..).
    - Skip symlink entries instead of materialising them.
    - Enforce a hard limit on total uncompressed size to mitigate zip bombs.
    """
    dest_root = Path(dest_path).resolve()
    total_size = 0

    for info in zip_ref.infolist():
        # Reject absolute paths or any path that attempts directory traversal.
        if _is_unsafe_zip_member(info):
            raise HTTPException(
                status_code=400,
                detail=f"Archive contains unsafe member path: {info.filename!r}",
            )

        # Skip any symlink entries instead of materialising them on disk.
        if _is_symlink_member(info):
            logger.warning("Skipping symlink entry in skill archive: %s", info.filename)
            continue

        # Basic unzip-bomb defence: bound the total uncompressed size we will write.
        total_size += max(info.file_size, 0)
        if total_size > max_total_size:
            raise HTTPException(
                status_code=400,
                detail="Skill archive is too large or appears highly compressed.",
            )

        member_path = dest_root / info.filename
        member_path_parent = member_path.parent
        member_path_parent.mkdir(parents=True, exist_ok=True)

        if info.is_dir():
            member_path.mkdir(parents=True, exist_ok=True)
            continue

        with zip_ref.open(info) as src, open(member_path, "wb") as dst:
            shutil.copyfileobj(src, dst)


router = APIRouter(prefix="/api", tags=["skills"])


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


class SkillDeleteResponse(BaseModel):
    """Response model for skill deletion."""

    success: bool = Field(..., description="Whether the deletion was successful")
    skill_name: str = Field(..., description="Name of the deleted skill")
    message: str = Field(..., description="Deletion result message")


def _should_ignore_archive_entry(path: Path) -> bool:
    return path.name.startswith(".") or path.name == "__MACOSX"


def _resolve_skill_dir_from_archive_root(temp_path: Path) -> Path:
    extracted_items = [item for item in temp_path.iterdir() if not _should_ignore_archive_entry(item)]
    if len(extracted_items) == 0:
        raise HTTPException(status_code=400, detail="Skill archive is empty")
    if len(extracted_items) == 1 and extracted_items[0].is_dir():
        return extracted_items[0]
    return temp_path


def _get_custom_skills_dir() -> Path:
    """Return the custom skills directory, creating it when missing."""
    custom_skills_dir = get_skills_root_path() / "custom"
    custom_skills_dir.mkdir(parents=True, exist_ok=True)
    return custom_skills_dir


def _install_skill_archive(skill_file_path: Path) -> str:
    """Validate a skill archive and copy the skill it contains into skills/custom.

    Returns:
        The installed skill name.
    """
    if not skill_file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {skill_file_path.name}")

    if not zipfile.is_zipfile(skill_file_path):
        raise HTTPException(status_code=400, detail="File is not a valid ZIP archive")

    custom_skills_dir = _get_custom_skills_dir()

    # Extract to a temporary directory first for validation
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        with zipfile.ZipFile(skill_file_path, "r") as zip_ref:
            _safe_extract_skill_archive(zip_ref, temp_path)

        skill_dir = _resolve_skill_dir_from_archive_root(temp_path)

        is_valid, message, skill_name = _validate_skill_frontmatter(skill_dir)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid skill: {message}")

        if not skill_name:
            raise HTTPException(status_code=400, detail="Could not determine skill name")

        target_dir = custom_skills_dir / skill_name
        if target_dir.exists():
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' already exists. Please remove it first or use a different name.")

        shutil.copytree(skill_dir, target_dir)

    logger.info(f"Skill '{skill_name}' installed successfully to {target_dir}")
    return skill_name


def _is_plain_yaml_string(value: str) -> bool:
    """Return True when `value` reads back from YAML as a plain string.

    SKILL.md frontmatter is parsed as YAML by the validator, so values such as
    a bare number ("11") or text starting with YAML syntax would be rejected.
    """
    try:
        parsed = yaml.safe_load(f"v: {value}")
    except yaml.YAMLError:
        return False
    return isinstance(parsed, dict) and isinstance(parsed.get("v"), str)


def _get_skill(skill_name: str) -> Skill:
    """Look up a skill by name, raising 404 when it does not exist."""
    skills = load_skills(enabled_only=False)
    skill = next((s for s in skills if s.name == skill_name), None)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return skill


def _resolve_skill_file(skill_dir: Path, relative_path: str) -> Path:
    """Resolve a path inside a skill directory, rejecting escapes."""
    root = skill_dir.resolve()
    target = (root / relative_path).resolve()
    if target != root and not target.is_relative_to(root):
        raise HTTPException(status_code=403, detail="Access denied: path is outside the skill directory")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
    return target


class SkillCreateRequest(BaseModel):
    """Request model for creating a new custom skill."""

    name: str = Field(..., description="Skill name in hyphen-case, used as the directory name")
    description: str = Field(..., description="Description of what the skill does and when to use it")
    instructions: str = Field("", description="Optional body of SKILL.md (instructions, workflow, rules)")


class SkillFileEntry(BaseModel):
    """A single entry (file or directory) inside a skill directory."""

    path: str = Field(..., description="Path relative to the skill directory")
    type: str = Field(..., description="Either 'file' or 'dir'")
    size: int = Field(0, description="File size in bytes (0 for directories)")


class SkillFilesResponse(BaseModel):
    """Directory listing of a skill."""

    name: str = Field(..., description="Name of the skill")
    category: str = Field(..., description="Category of the skill (public or custom)")
    files: list[SkillFileEntry] = Field(default_factory=list, description="Entries in tree order")
    truncated: bool = Field(False, description="Whether the listing was truncated")


class SkillFileContentResponse(BaseModel):
    """Content of a single file inside a skill directory."""

    path: str = Field(..., description="Path relative to the skill directory")
    size: int = Field(..., description="File size in bytes")
    binary: bool = Field(..., description="Whether the file appears to be binary")
    truncated: bool = Field(..., description="Whether the returned content was truncated")
    content: str | None = Field(None, description="Text content, omitted for binary files")


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a Skill object to a SkillResponse."""
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        license=skill.license,
        category=skill.category,
        enabled=skill.enabled,
    )


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve a list of all available skills from both public and custom directories.",
)
async def list_skills() -> SkillsListResponse:
    """List all available skills.

    Returns all skills regardless of their enabled status.

    Returns:
        A list of all skills with their metadata.

    Example Response:
        ```json
        {
            "skills": [
                {
                    "name": "PDF Processing",
                    "description": "Extract and analyze PDF content",
                    "license": "MIT",
                    "category": "public",
                    "enabled": true
                },
                {
                    "name": "Frontend Design",
                    "description": "Generate frontend designs and components",
                    "license": null,
                    "category": "custom",
                    "enabled": false
                }
            ]
        }
        ```
    """
    try:
        # Load all skills (including disabled ones)
        skills = load_skills(enabled_only=False)
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
    except Exception as e:
        logger.error(f"Failed to load skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve detailed information about a specific skill by its name.",
)
async def get_skill(skill_name: str) -> SkillResponse:
    """Get a specific skill by name.

    Args:
        skill_name: The name of the skill to retrieve.

    Returns:
        Skill information if found.

    Raises:
        HTTPException: 404 if skill not found.

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": true
        }
        ```
    """
    try:
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return _skill_to_response(skill)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {str(e)}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update a skill's enabled status by modifying the extensions_config.json file.",
)
async def update_skill(skill_name: str, request: SkillUpdateRequest) -> SkillResponse:
    """Update a skill's enabled status.

    This will modify the extensions_config.json file to update the enabled state.
    The SKILL.md file itself is not modified.

    Args:
        skill_name: The name of the skill to update.
        request: The update request containing the new enabled status.

    Returns:
        The updated skill information.

    Raises:
        HTTPException: 404 if skill not found, 500 if update fails.

    Example Request:
        ```json
        {
            "enabled": false
        }
        ```

    Example Response:
        ```json
        {
            "name": "PDF Processing",
            "description": "Extract and analyze PDF content",
            "license": "MIT",
            "category": "public",
            "enabled": false
        }
        ```
    """
    try:
        # Find the skill to verify it exists
        skills = load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == skill_name), None)

        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        # Get or create config path
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            # Create new config file in parent directory (project root)
            config_path = Path.cwd().parent / "extensions_config.json"
            logger.info(f"No existing extensions config found. Creating new config at: {config_path}")

        # Load current configuration
        extensions_config = get_extensions_config()

        # Update the skill's enabled status
        extensions_config.skills[skill_name] = SkillStateConfig(enabled=request.enabled)

        # Convert to JSON format (preserve MCP servers config)
        config_data = {
            "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
            "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
        }

        # Write the configuration to file
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Skills configuration updated and saved to: {config_path}")

        # Reload the extensions config to update the global cache
        reload_extensions_config()

        # Reload the skills to get the updated status (for API response)
        skills = load_skills(enabled_only=False)
        updated_skill = next((s for s in skills if s.name == skill_name), None)

        if updated_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to reload skill '{skill_name}' after update")

        logger.info(f"Skill '{skill_name}' enabled status updated to {request.enabled}")
        return _skill_to_response(updated_skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {str(e)}")


@router.delete(
    "/skills/{skill_name}",
    response_model=SkillDeleteResponse,
    summary="Delete Skill",
    description="Delete a custom skill directory. Built-in (public) skills cannot be deleted.",
)
async def delete_skill(skill_name: str) -> SkillDeleteResponse:
    """Delete a custom skill and forget its enabled state.

    Only skills under the custom category can be removed; public (built-in)
    skills are shared by the repository and can only be disabled.

    Raises:
        HTTPException:
            - 400 if the skill is a built-in skill
            - 403 if the resolved directory is outside skills/custom
            - 404 if the skill is not found
            - 500 if deletion fails
    """
    try:
        skill = _get_skill(skill_name)

        if skill.category != "custom":
            raise HTTPException(
                status_code=400,
                detail=f"Built-in skill '{skill_name}' cannot be deleted. Disable it instead.",
            )

        custom_skills_dir = _get_custom_skills_dir().resolve()
        target_dir = Path(skill.skill_dir).resolve()
        if target_dir == custom_skills_dir or not target_dir.is_relative_to(custom_skills_dir):
            raise HTTPException(status_code=403, detail="Access denied: skill directory is outside the custom skills directory")

        shutil.rmtree(target_dir)
        logger.info(f"Skill '{skill_name}' deleted from {target_dir}")

        # Best effort: drop the skill's enabled state from extensions_config.json.
        try:
            extensions_config = get_extensions_config()
            if skill_name in extensions_config.skills:
                del extensions_config.skills[skill_name]
                config_path = ExtensionsConfig.resolve_config_path()
                if config_path is not None:
                    config_data = {
                        "mcpServers": {name: server.model_dump() for name, server in extensions_config.mcp_servers.items()},
                        "skills": {name: {"enabled": skill_config.enabled} for name, skill_config in extensions_config.skills.items()},
                    }
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(config_data, f, indent=2)
                    reload_extensions_config()
        except Exception as e:
            logger.warning(f"Failed to remove skill '{skill_name}' from extensions config: {e}")

        return SkillDeleteResponse(success=True, skill_name=skill_name, message=f"Skill '{skill_name}' deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {str(e)}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(request: SkillInstallRequest) -> SkillInstallResponse:
    """Install a skill from a .skill file.

    The .skill file is a ZIP archive containing a skill directory with SKILL.md
    and optional resources (scripts, references, assets).

    Args:
        request: The install request containing thread_id and virtual path to .skill file.

    Returns:
        Installation result with skill name and status message.

    Raises:
        HTTPException:
            - 400 if path is invalid or file is not a valid .skill file
            - 403 if access denied (path traversal detected)
            - 404 if file not found
            - 409 if skill already exists
            - 500 if installation fails

    Example Request:
        ```json
        {
            "thread_id": "abc123-def456",
            "path": "/mnt/user-data/outputs/my-skill.skill"
        }
        ```

    Example Response:
        ```json
        {
            "success": true,
            "skill_name": "my-skill",
            "message": "Skill 'my-skill' installed successfully"
        }
        ```
    """
    try:
        # Resolve the virtual path to actual file path
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)

        # Check if file exists
        if not skill_file_path.exists():
            raise HTTPException(status_code=404, detail=f"Skill file not found: {request.path}")

        # Check if it's a file
        if not skill_file_path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {request.path}")

        # Check file extension
        if not skill_file_path.suffix == ".skill":
            raise HTTPException(status_code=400, detail="File must have .skill extension")

        skill_name = _install_skill_archive(skill_file_path)
        return SkillInstallResponse(success=True, skill_name=skill_name, message=f"Skill '{skill_name}' installed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {str(e)}")


@router.post(
    "/skills/upload",
    response_model=SkillResponse,
    summary="Upload Skill",
    description="Install a skill from an uploaded .skill or .zip archive into the custom skills directory.",
)
async def upload_skill(file: UploadFile = File(..., description="The .skill or .zip archive to install")) -> SkillResponse:
    """Install a skill from an uploaded archive.

    The archive must contain a skill directory with a valid SKILL.md
    (frontmatter with hyphen-case 'name' and a 'description').

    Raises:
        HTTPException:
            - 400 if the archive is missing, not a ZIP, unsafe, or invalid as a skill
            - 409 if a skill with the same name already exists
            - 500 if installation fails
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        with tempfile.TemporaryDirectory() as temp_dir:
            upload_path = Path(temp_dir) / Path(file.filename).name
            with open(upload_path, "wb") as dst:
                while chunk := await file.read(1024 * 1024):
                    dst.write(chunk)
            skill_name = _install_skill_archive(upload_path)

        skill = next((s for s in load_skills(enabled_only=False) if s.name == skill_name), None)
        if skill is None:
            raise HTTPException(status_code=500, detail=f"Skill '{skill_name}' was installed but could not be loaded")
        return _skill_to_response(skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload skill: {str(e)}")


@router.post(
    "/skills/create",
    response_model=SkillResponse,
    summary="Create Skill",
    description="Create a new custom skill directory containing a generated SKILL.md.",
)
async def create_skill(request: SkillCreateRequest) -> SkillResponse:
    """Create a new custom skill from a name, description and optional instructions.

    Raises:
        HTTPException:
            - 400 if the name or description do not form a valid SKILL.md
            - 409 if a skill with the same name already exists
            - 500 if creation fails
    """
    try:
        name = request.name.strip()
        # A description is a single-line field: collapse newlines/whitespace.
        description = " ".join(request.description.split())
        instructions = request.instructions.strip()

        if not name:
            raise HTTPException(status_code=400, detail="Skill name is required")
        if not description:
            raise HTTPException(status_code=400, detail="Skill description is required")
        if not re.search(r"[a-z]", name):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid skill name {name!r}: use lowercase letters, digits and hyphens, "
                    "and include at least one letter."
                ),
            )
        if not _is_plain_yaml_string(description):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Skill description must be plain text — a bare number or text starting "
                    "with YAML syntax cannot be read back from SKILL.md."
                ),
            )

        custom_skills_dir = _get_custom_skills_dir()
        target_dir = custom_skills_dir / name
        if target_dir.exists():
            raise HTTPException(status_code=409, detail=f"Skill '{name}' already exists. Please use a different name.")

        if instructions:
            body = f"{instructions}\n"
        else:
            body = f"# {name}\n\n{description}\n"
        skill_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"

        # Validate by writing into a temporary directory first, so invalid names
        # or descriptions cannot create a half-built skill directory.
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_skill_dir = Path(temp_dir) / name
            temp_skill_dir.mkdir(parents=True)
            (temp_skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

            is_valid, message, skill_name = _validate_skill_frontmatter(temp_skill_dir)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid skill: {message}")
            if not skill_name:
                raise HTTPException(status_code=400, detail="Could not determine skill name")

            shutil.copytree(temp_skill_dir, target_dir)

        logger.info(f"Skill '{name}' created at {target_dir}")

        skill = next((s for s in load_skills(enabled_only=False) if s.name == name), None)
        if skill is None:
            raise HTTPException(status_code=500, detail=f"Skill '{name}' was created but could not be loaded")
        return _skill_to_response(skill)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.get(
    "/skills/{skill_name}/files",
    response_model=SkillFilesResponse,
    summary="List Skill Files",
    description="List the files and directories inside a skill, in tree order.",
)
async def list_skill_files(skill_name: str) -> SkillFilesResponse:
    """List the contents of a skill directory.

    Raises:
        HTTPException: 404 if the skill is not found, 500 if the listing fails.
    """
    try:
        skill = _get_skill(skill_name)
        root = skill.skill_dir

        entries: list[SkillFileEntry] = []
        truncated = False

        for current_root, dir_names, file_names in os.walk(root):
            dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
            file_names = sorted(name for name in file_names if not name.startswith("."))
            current_path = Path(current_root)

            for dir_name in dir_names:
                entries.append(SkillFileEntry(path=(current_path / dir_name).relative_to(root).as_posix(), type="dir", size=0))
            for file_name in file_names:
                file_path = current_path / file_name
                size = file_path.stat().st_size if file_path.is_file() else 0
                entries.append(SkillFileEntry(path=file_path.relative_to(root).as_posix(), type="file", size=size))

            if len(entries) > MAX_LISTED_ENTRIES:
                truncated = True
                entries = entries[:MAX_LISTED_ENTRIES]
                break

        return SkillFilesResponse(name=skill.name, category=skill.category, files=entries, truncated=truncated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list files for skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list skill files: {str(e)}")


@router.get(
    "/skills/{skill_name}/file",
    response_model=SkillFileContentResponse,
    summary="Read Skill File",
    description="Read a single text file from inside a skill directory.",
)
async def read_skill_file(skill_name: str, path: str) -> SkillFileContentResponse:
    """Read a file inside a skill directory.

    Text files are returned up to MAX_PREVIEW_BYTES; binary files are flagged
    and returned without content.

    Raises:
        HTTPException: 403 on path traversal, 404 if skill or file is missing, 500 on failure.
    """
    try:
        skill = _get_skill(skill_name)
        target = _resolve_skill_file(skill.skill_dir, path)

        size = target.stat().st_size
        with open(target, "rb") as f:
            raw = f.read(MAX_PREVIEW_BYTES)

        binary = b"\x00" in raw
        content = None if binary else raw.decode("utf-8", errors="replace")

        return SkillFileContentResponse(
            path=path,
            size=size,
            binary=binary,
            truncated=size > MAX_PREVIEW_BYTES,
            content=content,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read file {path} for skill {skill_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read skill file: {str(e)}")
