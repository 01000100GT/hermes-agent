"""
CLI Utilities for Hermes Agent.
Provides helper functions for terminal interactions.
"""

try:
    from rich.console import Console
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

def read_multiline_input(prompt_msg: str) -> str:
    """
    Reads multi-line input from the user until EOF (Ctrl+D) or 'EOF' on a new line.
    Prevents premature submission when users paste multi-line content (e.g. JSON, logs).
    """
    if HAS_RICH:
        console.print(f"{prompt_msg} [dim](支持多行粘贴，按 Ctrl+D 或在新行输入 'EOF' 结束)[/dim]")
    else:
        print(f"{prompt_msg} (支持多行粘贴，按 Ctrl+D 或在新行输入 'EOF' 结束):")
        
    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == 'EOF':
                break
            lines.append(line)
    except EOFError:
        pass  # Ctrl+D triggered EOF
        
    return "\n".join(lines).strip()
