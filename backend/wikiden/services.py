import difflib
import markdown
import nh3


def render_markdown(text: str) -> str:
    """Convierte Markdown a HTML seguro."""
    raw_html = markdown.markdown(
        text or "",
        extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
    )
    return nh3.clean(raw_html)


def build_diff(original_text: str, proposed_text: str) -> list[dict]:
    """Genera un diff unificado estructurado para revisión tipo Pull Request."""
    original_lines = (original_text or "").splitlines()
    proposed_lines = (proposed_text or "").splitlines()

    diff_iter = difflib.unified_diff(
        original_lines,
        proposed_lines,
        fromfile="Actual",
        tofile="Propuesto",
        lineterm="",
    )

    result = []
    for line in diff_iter:
        if line.startswith(("+++", "---", "@@")):
            line_type = "meta"
        elif line.startswith("+"):
            line_type = "add"
        elif line.startswith("-"):
            line_type = "remove"
        else:
            line_type = "context"
        result.append({"type": line_type, "text": line})
    return result