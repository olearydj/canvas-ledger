"""Config command group for canvas-ledger CLI.

Commands:
- cl config init: Initialize configuration
- cl config show: Display current configuration
- cl config set: Update configuration values
"""

from __future__ import annotations

from pathlib import Path

import typer

from cl.config.secrets import get_secret_provider
from cl.config.settings import (
    Settings,
    ensure_directories,
    get_default_config_path,
    get_default_db_path,
    load_settings,
    save_settings,
)

app = typer.Typer(
    name="config",
    help="""Manage canvas-ledger configuration.

Configuration is stored in ~/.config/cl/config.toml. API tokens are NEVER
stored in the config file—use environment variables or 1Password.

Start here: Run 'cl config init' to set up your Canvas URL and token source.
""",
    no_args_is_help=True,
)


@app.command("init")
def config_init(
    canvas_url: str | None = typer.Option(
        None,
        "--canvas-url",
        "-u",
        help="Canvas base URL (e.g., https://canvas.institution.edu)",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Path to SQLite database file.",
    ),
    secret_provider: str | None = typer.Option(
        None,
        "--secret-provider",
        "-s",
        help="Secret provider for API token (env or 1password).",
    ),
    op_reference: str | None = typer.Option(
        None,
        "--op-reference",
        "-o",
        help="1Password reference (e.g., op://Dev/Canvas/credential).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration.",
    ),
) -> None:
    """Initialize canvas-ledger configuration.

    Creates a config file at ~/.config/cl/config.toml with your Canvas URL
    and token retrieval settings.
    \b
    Token options (choose one):
      • Environment variable: export CANVAS_API_TOKEN='your-token'
      • 1Password CLI: Use --secret-provider=1password --op-reference=op://...
    \b
    Examples:
      cl config init --canvas-url https://canvas.auburn.edu
      cl config init -u canvas.auburn.edu -s 1password -o op://Dev/Canvas/token
    """
    config_path = get_default_config_path()

    # Check if config already exists
    if config_path.exists() and not force:
        typer.secho(
            f"Configuration already exists at {config_path}",
            fg=typer.colors.YELLOW,
        )
        typer.echo("Use --force to overwrite.")
        raise typer.Exit(1)

    # Interactive mode if no URL provided
    if canvas_url is None:
        canvas_url = typer.prompt("Canvas base URL")

    # Validate URL format
    if not canvas_url.startswith(("http://", "https://")):
        canvas_url = f"https://{canvas_url}"

    # Create settings
    settings = Settings(
        canvas_base_url=canvas_url,
        db_path=db_path or get_default_db_path(),
        config_path=config_path,
        secret_provider=secret_provider or "env",
        op_reference=op_reference or "",
    )

    # Validate
    errors = settings.validate()
    if errors:
        for error in errors:
            typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Ensure directories exist
    ensure_directories(settings)

    # Save configuration
    save_settings(settings)

    typer.secho(f"Configuration saved to {config_path}", fg=typer.colors.GREEN)
    typer.echo()
    typer.echo("Next steps:")
    if settings.secret_provider == "1password":
        typer.echo("  1. Ensure you're signed in to 1Password CLI: op signin")
        typer.echo("  2. Initialize the database: cl db migrate")
    else:
        typer.echo("  1. Set your Canvas API token:")
        typer.echo("     export CANVAS_API_TOKEN='your-token-here'")
        typer.echo("  2. Initialize the database:")
        typer.echo("     cl db migrate")


@app.command("show")
def config_show(
    reveal: bool = typer.Option(
        False,
        "--reveal",
        "-r",
        help="Show secret provider status (never reveals actual tokens).",
    ),
) -> None:
    """Display current configuration.

    Shows all configuration values. Secrets are never displayed.
    """
    config_path = get_default_config_path()

    if not config_path.exists():
        typer.secho(
            "No configuration found. Run 'cl config init' first.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    settings = load_settings(config_path)

    typer.echo("Current configuration:")
    typer.echo(f"  Config file: {settings.config_path}")
    typer.echo(f"  Canvas URL:  {settings.canvas_base_url}")
    typer.echo(f"  Database:    {settings.db_path}")
    typer.echo(f"  Log level:   {settings.log_level}")
    typer.echo(f"  Secret provider: {settings.secret_provider}")
    if settings.op_reference:
        typer.echo(f"  1Password ref:   {settings.op_reference}")

    if reveal:
        typer.echo()
        typer.echo("Secret provider status:")
        try:
            provider = get_secret_provider(
                settings.secret_provider,
                settings.op_reference,
            )
            if provider.is_available():
                typer.secho("  Canvas API token: configured", fg=typer.colors.GREEN)
            else:
                typer.secho("  Canvas API token: not configured", fg=typer.colors.YELLOW)
        except Exception as e:
            typer.secho(f"  Error checking secrets: {e}", fg=typer.colors.RED)


@app.command("set")
def config_set(
    key: str = typer.Argument(
        ...,
        help="Configuration key to set.",
    ),
    value: str = typer.Argument(..., help="Value to set."),
) -> None:
    """Update a configuration value.

    Valid keys: canvas_base_url, db_path, log_level, secret_provider, op_reference

    Note: Tokens cannot be set via this command. Use environment
    variables or 1Password instead.
    """
    config_path = get_default_config_path()

    if not config_path.exists():
        typer.secho(
            "No configuration found. Run 'cl config init' first.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    settings = load_settings(config_path)

    # Map of valid keys to their setters
    valid_keys = {
        "canvas_base_url": lambda s, v: setattr(s, "canvas_base_url", v),
        "db_path": lambda s, v: setattr(s, "db_path", Path(v)),
        "log_level": lambda s, v: setattr(s, "log_level", v),
        "secret_provider": lambda s, v: setattr(s, "secret_provider", v),
        "op_reference": lambda s, v: setattr(s, "op_reference", v),
    }

    if key not in valid_keys:
        typer.secho(
            f"Unknown configuration key: {key}",
            fg=typer.colors.RED,
            err=True,
        )
        typer.echo(f"Valid keys: {', '.join(valid_keys.keys())}")
        raise typer.Exit(1)

    # Update the setting
    valid_keys[key](settings, value)

    # Validate
    errors = settings.validate()
    if errors:
        for error in errors:
            typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    # Save
    save_settings(settings)
    typer.secho(f"Updated {key} = {value}", fg=typer.colors.GREEN)
