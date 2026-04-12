"""Knowledge base management for SNS Analyzer skills."""

from pathlib import Path

from utils.analyzer import _load_skill_files

SKILLS_DIR = Path(__file__).parent.parent / "skills"
REFS_DIR = SKILLS_DIR / "references"


def list_knowledge_files():
    """List all knowledge files in references/.

    Returns:
        List of (filename, size_bytes) tuples.
    """
    if not REFS_DIR.exists():
        return []
    return [
        (f.name, f.stat().st_size)
        for f in sorted(REFS_DIR.glob("*.md"))
    ]


def read_knowledge_file(filename):
    """Read a knowledge file's content.

    Returns:
        File content string, or None if not found.
    """
    path = REFS_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def save_knowledge_file(filename, content):
    """Save a knowledge file and clear the skill cache.

    Args:
        filename: Filename (must end with .md).
        content: File content string.
    """
    REFS_DIR.mkdir(parents=True, exist_ok=True)
    path = REFS_DIR / filename
    path.write_text(content, encoding="utf-8")
    _load_skill_files.cache_clear()


def delete_knowledge_file(filename):
    """Delete a knowledge file and clear the skill cache."""
    path = REFS_DIR / filename
    if path.exists():
        path.unlink()
        _load_skill_files.cache_clear()
