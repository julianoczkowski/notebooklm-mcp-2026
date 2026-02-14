"""Branded CLI with interactive setup wizard, status, and diagnostics.

Subcommands:
    setup   - Interactive setup wizard
    login   - Authenticate via Chrome
    logout  - Remove stored credentials
    status  - Check auth and configuration status
    doctor  - Diagnose common issues
    serve   - Start MCP server over stdio
    version - Print version
    help    - Show help message (default when no command given)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__

# CLI output goes to stderr so stdout stays clean for MCP stdio transport.
console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Branding
# ---------------------------------------------------------------------------

BRAND_COLOR = "bright_blue"
SUCCESS_COLOR = "green"
ERROR_COLOR = "red"
WARNING_COLOR = "yellow"
DIM_COLOR = "dim"

LOGO_LINES = [
    "  NotebookLM  MCP",
    "  ~~~~~~~~~~~~~~~",
]

LOGO_SHORT = "NotebookLM MCP"


def show_banner() -> None:
    """Display branded welcome banner."""
    title_line = Text.assemble(
        ("NotebookLM MCP Server", f"bold {BRAND_COLOR}"),
        ("  v", DIM_COLOR),
        (__version__, DIM_COLOR),
    )
    byline = Text("by Julian Oczkowski", style=DIM_COLOR)
    content = Text()
    content.append_text(title_line)
    content.append("\n")
    content.append_text(byline)

    console.print(Panel(
        content,
        box=box.DOUBLE,
        border_style=BRAND_COLOR,
        padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# MCP client detection and configuration
# ---------------------------------------------------------------------------


@dataclass
class MCPClientConfig:
    """How to detect and configure an MCP client."""

    name: str
    slug: str
    server_key: str  # "mcpServers" or "servers"

    def detect(self) -> bool:
        """Return True if this client appears to be installed."""
        path = self.config_path()
        return path is not None and path.parent.is_dir()

    def config_path(self) -> Path | None:
        """Return the config file path for this client."""
        raise NotImplementedError


class ClaudeCodeConfig(MCPClientConfig):
    def __init__(self) -> None:
        super().__init__(name="Claude Code", slug="claude-code", server_key="mcpServers")

    def detect(self) -> bool:
        # Claude Code creates ~/.claude/ on first use
        return (Path.home() / ".claude").is_dir()

    def config_path(self) -> Path:
        return Path.home() / ".claude.json"


class CursorConfig(MCPClientConfig):
    def __init__(self) -> None:
        super().__init__(name="Cursor", slug="cursor", server_key="mcpServers")

    def config_path(self) -> Path:
        return Path.home() / ".cursor" / "mcp.json"


class VSCodeConfig(MCPClientConfig):
    def __init__(self) -> None:
        super().__init__(name="VS Code (Copilot)", slug="vscode", server_key="servers")

    def detect(self) -> bool:
        path = self._user_dir()
        return path is not None and path.is_dir()

    def config_path(self) -> Path | None:
        user_dir = self._user_dir()
        return user_dir / "mcp.json" if user_dir else None

    def _user_dir(self) -> Path | None:
        system = platform.system()
        if system == "Linux":
            return Path.home() / ".config" / "Code" / "User"
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Code" / "User"
        if system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            return Path(appdata) / "Code" / "User" if appdata else None
        return None


class ClaudeDesktopConfig(MCPClientConfig):
    def __init__(self) -> None:
        super().__init__(name="Claude Desktop", slug="claude-desktop", server_key="mcpServers")

    def config_path(self) -> Path | None:
        system = platform.system()
        if system == "Linux":
            return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
        if system == "Darwin":
            return (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        if system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            return Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
        return None


MCP_CLIENTS: list[MCPClientConfig] = [
    ClaudeCodeConfig(),
    CursorConfig(),
    VSCodeConfig(),
    ClaudeDesktopConfig(),
]

def _get_server_entry() -> dict[str, Any]:
    """Build the MCP server entry for config files.

    Uses the full absolute path to the ``notebooklm-mcp-2026`` executable
    so that MCP clients can find it even when the venv isn't on PATH.
    If the command is already on the system PATH, the short name is used
    for portability.
    """
    short_name = "notebooklm-mcp-2026"
    found = shutil.which(short_name)
    if found:
        # Already on PATH — use the short name for cleaner configs
        return {"command": short_name, "args": ["serve"]}

    # Not on PATH — resolve from the running interpreter's venv
    # sys.executable is e.g. /home/user/.venv/bin/python
    venv_bin = Path(sys.executable).parent
    full_path = venv_bin / short_name
    if full_path.exists():
        return {"command": str(full_path), "args": ["serve"]}

    # Last resort: python -m invocation (always works)
    return {"command": sys.executable, "args": ["-m", "notebooklm_mcp_2026", "serve"]}


# ---------------------------------------------------------------------------
# Config file merging
# ---------------------------------------------------------------------------


def merge_mcp_config(
    config_path: Path,
    server_key: str,
    server_name: str,
    server_entry: dict[str, Any],
) -> tuple[bool, str]:
    """Read an MCP client config, merge our server entry, write back.

    Returns ``(success, message)``.
    """
    config: dict[str, Any] = {}

    if config_path.exists():
        try:
            raw = config_path.read_text(encoding="utf-8")
            if raw.strip():
                config = json.loads(raw)
        except json.JSONDecodeError:
            backup = config_path.with_suffix(".json.backup")
            shutil.copy2(config_path, backup)
            return False, f"Corrupt JSON — backed up to {backup.name}"
        except OSError as exc:
            return False, f"Cannot read: {exc}"
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)

    if server_key not in config:
        config[server_key] = {}

    already_configured = server_name in config[server_key]
    config[server_key][server_name] = server_entry

    try:
        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return False, f"Cannot write: {exc}"

    if already_configured:
        return True, "Updated (was already configured)"
    return True, "Added successfully"


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def handle_setup() -> None:
    """Interactive setup wizard."""
    import questionary

    show_banner()
    console.print()

    # Step 1: Check authentication ──────────────────────────────────
    console.print("[bold]Step 1:[/bold] Checking authentication...", style=BRAND_COLOR)

    from .auth import load_tokens

    tokens = load_tokens()
    if tokens is None:
        console.print("  [yellow]Not authenticated[/yellow]")
        console.print()
        do_login = questionary.confirm(
            "Would you like to log in now?",
            default=True,
        ).ask()
        if do_login is None:  # Ctrl+C
            console.print("\n[dim]Setup cancelled.[/dim]")
            sys.exit(0)
        if do_login:
            _run_login(timeout=300)
            tokens = load_tokens()
            if tokens is None:
                console.print("[red]Login failed. Retry with: notebooklm-mcp-2026 login[/red]")
                sys.exit(1)
        else:
            console.print(
                "  [dim]Skipping — you can log in later with: "
                "notebooklm-mcp-2026 login[/dim]"
            )
    else:
        age_hours = (time.time() - tokens.extracted_at) / 3600
        console.print(
            f"  [green]Authenticated[/green] "
            f"({len(tokens.cookies)} cookies, {age_hours:.0f}h old)"
        )

    console.print()

    # Step 2: Detect MCP clients ────────────────────────────────────
    console.print("[bold]Step 2:[/bold] Detecting MCP clients...", style=BRAND_COLOR)
    detected: list[MCPClientConfig] = []
    for client_cfg in MCP_CLIENTS:
        found = client_cfg.detect()
        status = "[green]found[/green]" if found else "[dim]not found[/dim]"
        console.print(f"  {client_cfg.name}: {status}")
        if found:
            detected.append(client_cfg)

    if not detected:
        console.print("\n[yellow]No MCP clients detected.[/yellow]")
        console.print("Install Claude Code, Cursor, or VS Code, then run setup again.")
        return

    console.print()

    # Step 3: Select clients to configure ───────────────────────────
    console.print("[bold]Step 3:[/bold] Select clients to configure", style=BRAND_COLOR)
    choices = questionary.checkbox(
        "Which clients should be configured?",
        choices=[
            questionary.Choice(title=c.name, value=c.slug, checked=True)
            for c in detected
        ],
    ).ask()

    if choices is None:  # Ctrl+C
        console.print("\n[dim]Setup cancelled.[/dim]")
        sys.exit(0)

    if not choices:
        console.print("[dim]No clients selected.[/dim]")
        return

    console.print()

    # Step 4: Configure selected clients ────────────────────────────
    console.print("[bold]Step 4:[/bold] Configuring MCP clients...", style=BRAND_COLOR)
    selected = [c for c in detected if c.slug in choices]
    results: list[tuple[str, bool]] = []

    for client_cfg in selected:
        config_path = client_cfg.config_path()
        if config_path is None:
            console.print(f"  {client_cfg.name}: [yellow]skipped (unsupported platform)[/yellow]")
            continue

        with console.status(f"  Configuring {client_cfg.name}...", spinner="dots"):
            ok, msg = merge_mcp_config(
                config_path=config_path,
                server_key=client_cfg.server_key,
                server_name="notebooklm-mcp-2026",
                server_entry=_get_server_entry(),
            )

        if ok:
            console.print(f"  {client_cfg.name}: [green]{msg}[/green]")
            console.print(f"    [dim]{config_path}[/dim]")
            results.append((client_cfg.name, True))
        else:
            console.print(f"  {client_cfg.name}: [red]{msg}[/red]")
            results.append((client_cfg.name, False))

    console.print()

    # Step 5: Success summary ───────────────────────────────────────
    _show_success_panel(results)


def _show_success_panel(results: list[tuple[str, bool]]) -> None:
    """Show branded success message with next steps."""
    success_count = sum(1 for _, ok in results if ok)

    if success_count == 0:
        console.print(Panel(
            "[red bold]No clients were configured successfully.[/red bold]\n"
            "Check the error messages above and try again.",
            title="Setup Failed",
            border_style=ERROR_COLOR,
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        return

    lines = [
        f"[green bold]Setup complete![/green bold] "
        f"Configured {success_count} client(s).\n",
        "[bold]Next steps:[/bold]",
        "",
        "  1. Restart your MCP client (Claude Code, Cursor, VS Code)",
        '  2. Try asking: [italic]"List my NotebookLM notebooks"[/italic]',
        "  3. The AI assistant now has access to your NotebookLM notebooks",
        "",
        "[dim]Cookies expire in 2\u20134 weeks. Re-run: notebooklm-mcp-2026 login[/dim]",
        "[dim]More info: https://github.com/julianoczkowski/notebooklm-mcp-2026[/dim]",
    ]

    console.print(Panel(
        "\n".join(lines),
        title="[green]Success[/green]",
        border_style=SUCCESS_COLOR,
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def _run_login(timeout: int, chrome_path: str | None = None) -> None:
    """Execute the Chrome CDP login flow with rich output."""
    from .auth import extract_cookies_via_cdp, save_tokens

    console.print(Panel(
        "[bold]Chrome Login[/bold]\n\n"
        "A Chrome window will open. Log in to your Google account\n"
        "on notebooklm.google.com, then return here.",
        border_style=BRAND_COLOR,
        box=box.ROUNDED,
        padding=(1, 2),
    ))

    def _on_manual_launch(port: int, launch_args: list[str]) -> None:
        """Show manual Chrome launch instructions when auto-detect fails."""
        args_str = " ".join(launch_args)
        system = platform.system()
        if system == "Windows":
            hint = r'"C:\Program Files\Google\Chrome\Application\chrome.exe"'
        elif system == "Darwin":
            hint = '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"'
        else:
            hint = "google-chrome"

        console.print()
        console.print(Panel(
            "[bold yellow]Chrome was not found automatically.[/bold yellow]\n\n"
            "Run this command in another terminal:\n\n"
            f"  [bold cyan]{hint} {args_str}[/bold cyan]\n\n"
            "Or re-run with your Chrome path:\n\n"
            '  [bold]notebooklm-mcp-2026 login --chrome-path "/path/to/chrome"[/bold]',
            title="[yellow]Manual Chrome Launch[/yellow]",
            border_style=WARNING_COLOR,
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        console.print()

    try:
        status = console.status("Launching Chrome and waiting for login...", spinner="dots")
        status.start()

        def _on_manual_launch_wrapper(port: int, launch_args: list[str]) -> None:
            status.stop()
            _on_manual_launch(port, launch_args)
            status.update("Waiting for Chrome connection...")
            status.start()

        tokens = extract_cookies_via_cdp(
            login_timeout=timeout,
            chrome_path=chrome_path,
            on_manual_launch_needed=_on_manual_launch_wrapper,
        )
        status.stop()

        save_tokens(tokens)
        console.print()
        console.print(Panel(
            f"[green bold]Authenticated![/green bold]  "
            f"Saved {len(tokens.cookies)} cookies.\n"
            + ("  CSRF token: [green]extracted[/green]\n" if tokens.csrf_token else "")
            + ("  Session ID: [green]extracted[/green]" if tokens.session_id else ""),
            title="[green]Login Successful[/green]",
            border_style=SUCCESS_COLOR,
            box=box.ROUNDED,
            padding=(1, 2),
        ))
        console.print()
    except Exception as exc:
        try:
            status.stop()
        except Exception:
            pass
        console.print(f"\n[red]Login failed:[/red] {exc}", highlight=False)
        raise


def handle_login(timeout: int, chrome_path: str | None = None) -> None:
    """Login subcommand handler."""
    show_banner()
    console.print()
    try:
        _run_login(timeout, chrome_path=chrome_path)
        console.print(Panel(
            "[bold]Next steps:[/bold]\n"
            "\n"
            "  1. Run [bold cyan]notebooklm-mcp-2026 setup[/bold cyan] "
            "to auto-configure your MCP client\n"
            "  2. Restart your MCP client (Claude Code, Cursor, VS Code)\n"
            '  3. Try asking: [italic]"List my NotebookLM notebooks"[/italic]\n'
            "\n"
            "[dim]More info: https://github.com/julianoczkowski/notebooklm-mcp-2026[/dim]",
            title="[bold]What's Next?[/bold]",
            border_style=BRAND_COLOR,
            box=box.ROUNDED,
            padding=(1, 2),
        ))
    except Exception:
        sys.exit(1)


def handle_status() -> None:
    """Show auth and config status."""
    show_banner()
    console.print()

    # Auth status ───────────────────────────────────────────────────
    console.print("[bold]Authentication[/bold]", style=BRAND_COLOR)

    from .auth import load_tokens

    tokens = load_tokens()
    if tokens is None:
        console.print("  Status: [red]Not authenticated[/red]")
        console.print("  Run: [bold]notebooklm-mcp-2026 login[/bold]")
    else:
        age_hours = (time.time() - tokens.extracted_at) / 3600
        age_str = f"{age_hours:.0f}h" if age_hours < 48 else f"{age_hours / 24:.0f}d"
        console.print("  Status: [green]Authenticated[/green]")
        console.print(f"  Cookies: {len(tokens.cookies)}")
        console.print(f"  Age: {age_str}")
        console.print(
            f"  CSRF: {'[green]yes[/green]' if tokens.csrf_token else '[yellow]no[/yellow]'}"
        )

    console.print()

    # Client config status ──────────────────────────────────────────
    console.print("[bold]MCP Client Configuration[/bold]", style=BRAND_COLOR)
    table = Table(show_header=True, header_style="bold", box=box.SIMPLE)
    table.add_column("Client")
    table.add_column("Installed")
    table.add_column("Configured")
    table.add_column("Config Path")

    for client_cfg in MCP_CLIENTS:
        installed = client_cfg.detect()
        config_path = client_cfg.config_path()
        configured = False

        if config_path and config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                servers = data.get(client_cfg.server_key, {})
                configured = "notebooklm-mcp-2026" in servers
            except (json.JSONDecodeError, OSError):
                pass

        table.add_row(
            client_cfg.name,
            "[green]yes[/green]" if installed else "[dim]no[/dim]",
            "[green]yes[/green]" if configured else "[yellow]no[/yellow]",
            str(config_path) if config_path else "N/A",
        )

    console.print(table)


def handle_doctor() -> None:
    """Diagnose common issues."""
    show_banner()
    console.print()
    console.print("[bold]Running diagnostics...[/bold]", style=BRAND_COLOR)
    console.print()

    checks: list[tuple[str, bool, str]] = []

    # Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(("Python >= 3.11", sys.version_info >= (3, 11), py_ver))

    # Chrome available
    from .auth import get_chrome_path

    chrome = get_chrome_path()
    checks.append(("Google Chrome", chrome is not None, chrome or "not found"))

    # Auth file exists
    from .config import AUTH_FILE

    checks.append(("Auth credentials", AUTH_FILE.exists(), str(AUTH_FILE)))

    # Auth file permissions (Unix only)
    if AUTH_FILE.exists() and platform.system() != "Windows":
        mode = AUTH_FILE.stat().st_mode & 0o777
        checks.append(("Auth file permissions", mode == 0o600, f"0o{mode:03o} (want 0o600)"))

    # Tokens loadable
    from .auth import load_tokens

    tokens = load_tokens()
    checks.append(("Tokens loadable", tokens is not None, ""))

    # Required cookies present
    if tokens:
        from .auth import validate_cookies

        valid = validate_cookies(tokens.cookies)
        checks.append(("Required cookies", valid, f"{len(tokens.cookies)} cookies"))

    # FastMCP importable
    try:
        import fastmcp

        checks.append(("FastMCP", True, f"v{fastmcp.__version__}"))
    except ImportError:
        checks.append(("FastMCP", False, "not installed"))

    # Print results
    for label, ok, detail in checks:
        icon = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        detail_str = f"  [dim]{detail}[/dim]" if detail else ""
        console.print(f"  {icon}  {label}{detail_str}")

    console.print()
    fail_count = sum(1 for _, ok, _ in checks if not ok)
    if fail_count == 0:
        console.print("[green]All checks passed![/green]")
    else:
        console.print(f"[yellow]{fail_count} issue(s) found. See above.[/yellow]")


def handle_logout() -> None:
    """Remove stored credentials."""
    from .config import AUTH_FILE, CHROME_PROFILE_DIR

    removed = []

    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
        removed.append(f"Credentials: {AUTH_FILE}")

    if CHROME_PROFILE_DIR.exists():
        shutil.rmtree(CHROME_PROFILE_DIR, ignore_errors=True)
        removed.append(f"Chrome profile: {CHROME_PROFILE_DIR}")

    if removed:
        console.print(Panel(
            "[green bold]Logged out.[/green bold]\n\n"
            + "\n".join(f"  Removed: [dim]{r}[/dim]" for r in removed)
            + "\n\nRun [bold]notebooklm-mcp-2026 login[/bold] to authenticate again.",
            title="[green]Logout[/green]",
            border_style=SUCCESS_COLOR,
            box=box.ROUNDED,
            padding=(1, 2),
        ))
    else:
        console.print("[dim]No credentials found — already logged out.[/dim]")


def handle_help() -> None:
    """Show branded help with all available commands."""
    show_banner()
    console.print()

    commands = [
        ("setup", "Interactive setup wizard — authenticate and configure MCP clients"),
        ("login", "Authenticate via Chrome (opens browser window)"),
        ("logout", "Remove stored credentials and Chrome profile"),
        ("status", "Show authentication and MCP client configuration status"),
        ("doctor", "Diagnose common issues (Chrome, auth, permissions)"),
        ("serve", "Start the MCP server over stdio (used by MCP clients)"),
        ("version", "Print version"),
        ("help", "Show this help message"),
    ]

    table = Table(show_header=True, header_style="bold", box=box.SIMPLE, pad_edge=False)
    table.add_column("Command", style="bold cyan", no_wrap=True)
    table.add_column("Description")

    for cmd, desc in commands:
        table.add_row(f"notebooklm-mcp-2026 {cmd}", desc)

    console.print(table)
    console.print()
    console.print("[bold]Getting started?[/bold] Run [bold cyan]notebooklm-mcp-2026 setup[/bold cyan]")
    console.print()
    console.print("[dim]More info: https://github.com/julianoczkowski/notebooklm-mcp-2026[/dim]")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point (``notebooklm-mcp-2026`` command)."""
    parser = argparse.ArgumentParser(
        prog="notebooklm-mcp-2026",
        description="Secure MCP server for querying Google NotebookLM notebooks.",
        add_help=False,
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Run the MCP server (stdio)")
    serve_parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    # login
    login_parser = subparsers.add_parser("login", help="Authenticate via Chrome (interactive)")
    login_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Max seconds to wait for login (default: 300)",
    )
    login_parser.add_argument(
        "--chrome-path",
        help="Path to Chrome/Chromium executable (auto-detected if omitted)",
    )

    # logout
    subparsers.add_parser("logout", help="Remove stored credentials and Chrome profile")

    # setup
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # status
    subparsers.add_parser("status", help="Show auth and config status")

    # doctor
    subparsers.add_parser("doctor", help="Diagnose common issues")

    # version
    subparsers.add_parser("version", help="Print version and exit")

    # help
    subparsers.add_parser("help", help="Show help message")

    args = parser.parse_args()

    if args.command == "login":
        handle_login(args.timeout, chrome_path=args.chrome_path)
    elif args.command == "logout":
        handle_logout()
    elif args.command == "setup":
        handle_setup()
    elif args.command == "status":
        handle_status()
    elif args.command == "doctor":
        handle_doctor()
    elif args.command == "version":
        console.print(f"notebooklm-mcp-2026 {__version__}")
    elif args.command == "serve":
        debug = getattr(args, "debug", False)
        if debug:
            logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
        from .server import mcp

        mcp.run(transport="stdio")
    else:
        # No command or "help" — show branded help
        handle_help()
