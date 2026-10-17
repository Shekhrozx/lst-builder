from __future__ import annotations

import keyword
import re
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import click

ASSETS_DIR = Path(__file__).parent / "assets"
TEMPLATE_PACKAGE = "app"
TEMPLATE_PACKAGE_DIR = Path("src") / TEMPLATE_PACKAGE
DOMAIN_TEMPLATE_DIR = ASSETS_DIR / "src" / TEMPLATE_PACKAGE / "domain" / "samples"
MODEL_TEMPLATE_FILE = ASSETS_DIR / "src" / TEMPLATE_PACKAGE / "db" / "models" / "sample.py"
PROJECT_SAMPLE_PATHS = (
    TEMPLATE_PACKAGE_DIR / "domain" / "samples",
    TEMPLATE_PACKAGE_DIR / "db" / "models" / "sample.py",
)
IGNORED_NAMES = {".git", "__pycache__", ".venv", ".DS_Store"}
PACKAGE_REF = re.compile(r"(?<![\w.])app(?=\.|\s+import\b)")


def to_snake(value: str) -> str:
    value = re.sub(r"[\s\-]+", "_", value.strip())
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def to_pascal(value: str) -> str:
    return "".join(part.capitalize() for part in to_snake(value).split("_"))


def validate_identifier(value: str, what: str) -> str:
    if not value.isidentifier() or keyword.iskeyword(value):
        raise click.BadParameter(f"{value!r} is not a valid Python identifier for the {what}.")
    return value


def is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    return True


def render_project(text: str, project: str, package: str) -> str:
    text = re.sub(r'^name = "app"$', f'name = "{project}"', text, flags=re.MULTILINE)
    text = re.sub(r'^app = "app\.', f'{project} = "{package}.', text, flags=re.MULTILINE)
    text = text.replace('"Litestar Fullstack Template"', repr(project))
    text = text.replace('DEFAULT_MODULE_NAME = "app"', f'DEFAULT_MODULE_NAME = "{package}"')
    text = text.replace("litestar-init", project)
    text = text.replace("from app.db.models.sample import Sample\n", "")
    text = text.replace('    "Sample",\n', "")
    return PACKAGE_REF.sub(package, text)


def render_domain(text: str, package: str, name: str) -> str:
    pascal = to_pascal(name)
    for old, new in (
        ("Samples", pascal),
        ("samples", name),
        ("Sample", pascal),
        ("sample", name),
        ("data_path,project_id", "name,description"),
        ("inference_service_filter_dependency", f"{name}_service_filter_dependency"),
    ):
        text = text.replace(old, new)
    return PACKAGE_REF.sub(package, text)


def copy_template(
    source: Path,
    target: Path,
    render: Callable[[str], str],
    map_path: Callable[[Path], Path] | None = None,
    exclude: tuple[Path, ...] = (),
) -> None:
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if any(part in IGNORED_NAMES for part in relative.parts) or item.suffix in {".pyc", ".pyo"}:
            continue
        if any(relative == excluded or excluded in relative.parents for excluded in exclude):
            continue
        if map_path is not None:
            relative = map_path(relative)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if is_text(item):
            destination.write_text(render(item.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            shutil.copy2(item, destination)
        shutil.copymode(item, destination)


def map_project_package(relative: Path, package: str) -> Path:
    """Map the template's ``src/app`` package directory to the requested package name."""
    if relative == TEMPLATE_PACKAGE_DIR:
        return Path("src") / package
    if TEMPLATE_PACKAGE_DIR in relative.parents:
        return Path("src") / package / relative.relative_to(TEMPLATE_PACKAGE_DIR)
    return relative


def find_project_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def add_builder_dependency(pyproject: Path) -> None:
    content = pyproject.read_text(encoding="utf-8")
    project = tomllib.loads(content).get("project", {})
    dependencies = project.get("dependencies", [])
    if any(re.match(r"\s*lst[-_]builder(?:\[|[<>=!~;@ ]|$)", dependency, re.IGNORECASE) for dependency in dependencies):
        return

    project_header = re.search(r"(?m)^\[project\]\s*$", content)
    if project_header is None:
        raise click.ClickException("Generated pyproject.toml must define a [project] table.")
    next_table = re.search(r"(?m)^\[", content[project_header.end() :])
    project_end = project_header.end() + next_table.start() if next_table else len(content)
    project_content = content[project_header.end() : project_end]
    dependencies_match = re.search(r"(?m)^dependencies\s*=\s*\[", project_content)
    if dependencies_match is None:
        insert_at = project_header.end()
        content = content[:insert_at] + '\ndependencies = ["lst-builder"]\n' + content[insert_at:]
    else:
        insert_at = project_header.end() + dependencies_match.end()
        content = content[:insert_at] + '\n    "lst-builder",' + content[insert_at:]
    pyproject.write_text(content, encoding="utf-8")


def find_package_dir(root: Path, explicit: str | None) -> Path | None:
    if explicit:
        for base in (root, root / "src"):
            if (base / explicit / "domain").is_dir():
                return base / explicit
        return None
    candidates: list[str] = []
    try:
        scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        candidates += [
            value.split(".")[0].split(":")[0]
            for value in scripts.get("project", {}).get("scripts", {}).values()
        ]
    except (tomllib.TOMLDecodeError, OSError):
        pass
    for base in (root, root / "src"):
        candidates += [p.name for p in base.iterdir() if p.is_dir()] if base.is_dir() else []
    for base in (root, root / "src"):
        for candidate in candidates:
            path = base / candidate
            if (path / "domain").is_dir() and (path / "__main__.py").is_file():
                return path
    return None


def register_model(package_dir: Path, name: str) -> bool:
    """Import the new model in ``db/models/__init__.py`` so migrations can discover it."""
    init_file = package_dir / "db" / "models" / "__init__.py"
    pascal = to_pascal(name)
    if not init_file.is_file():
        return False
    content = init_file.read_text(encoding="utf-8")
    import_line = f"from {package_dir.name}.db.models.{name} import {pascal}\n"
    if import_line.rstrip() in content:
        return True
    all_match = re.search(r"^__all__\s*=\s*[\(\[]\s*\n", content, flags=re.MULTILINE)
    if all_match is None:
        return False
    imports = list(re.finditer(r"^(?:from|import)\s+\S+[^\n]*\n", content, flags=re.MULTILINE))
    if not imports:
        return False

    content = content[: imports[-1].end()] + import_line + content[imports[-1].end() :]
    all_match = re.search(r"^__all__\s*=\s*[\(\[]\s*\n", content, flags=re.MULTILINE)
    if all_match is None:
        return False
    content = content[: all_match.end()] + f'    "{pascal}",\n' + content[all_match.end() :]
    init_file.write_text(content, encoding="utf-8")
    return True


@click.command(
    name="project",
    help="Create a new litestar project. PROJECT_ROOT is used directly (default: ./NAME).",
)
@click.argument("name", required=True)
@click.argument(
    "directory",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    metavar="PROJECT_ROOT",
)
@click.option("--package", "-p", default=None, help="Python package name (defaults to the snake_case project name).")
@click.option("--force", "-f", is_flag=True, help="Allow creating the project in a non-empty directory.")
def project(name: str, directory: Path | None, package: str | None, force: bool) -> None:
    """Create NAME in PROJECT_ROOT (default: ./NAME); an explicit PROJECT_ROOT is used directly."""
    package = validate_identifier(package or to_snake(name), "package")
    root_path = directory or Path.cwd() / name
    if root_path.exists() and any(root_path.iterdir()) and not force:
        raise click.ClickException(f"{root_path} already exists and is not empty (use --force to override).")
    root_path.mkdir(parents=True, exist_ok=True)

    def render(text: str) -> str:
        return render_project(text, name, package)

    copy_template(
        ASSETS_DIR,
        root_path,
        render,
        map_path=lambda relative: map_project_package(relative, package),
        exclude=PROJECT_SAMPLE_PATHS,
    )
    add_builder_dependency(root_path / "pyproject.toml")

    try:
        subprocess.run(["git", "init"], cwd=root_path, check=True, capture_output=True)
        git_initialized = True
    except (OSError, subprocess.CalledProcessError):
        git_initialized = False
        click.echo("Warning: could not initialize a Git repository.", err=True)

    click.echo()
    click.secho("Project created successfully", fg="green", bold=True)
    click.echo(f"  Project:  {name}")
    click.echo(f"  Package:  {package}")
    click.echo(f"  Git:      {'initialized' if git_initialized else 'not initialized'}")
    click.echo()
    click.secho("Next steps", fg="cyan", bold=True)
    click.echo("  1. Install dependencies: uv sync")
    click.echo(f"  2. Explore the app:      uv run {name} --help")


@click.command(name="domain", help="Create one or more domain units inside your litestar project.")
@click.argument("names", nargs=-1, required=True, metavar="NAME...")
@click.option("--package", "-p", default=None, help="Project package name (auto-detected by default).")
@click.option("--force", "-f", is_flag=True, help="Overwrite an existing domain.")
def domain(names: tuple[str, ...], package: str | None, force: bool) -> None:
    """Create domain units (controller, services, deps, guards, schemas, model)."""
    names = tuple(validate_identifier(to_snake(name), "domain") for name in names)
    if len(names) != len(set(names)):
        raise click.BadParameter("Domain names must be unique.", param_hint="NAME...")
    root = find_project_root(Path.cwd())
    if root is None:
        raise click.ClickException("No pyproject.toml found; run this command inside a project.")
    package_dir = find_package_dir(root, package)
    if package_dir is None:
        raise click.ClickException(
            "Could not locate the project package (expected '<package>/domain' and '__main__.py')."
        )

    for name in names:
        domain_dir = package_dir / "domain" / name
        model_file = package_dir / "db" / "models" / f"{name}.py"
        if (domain_dir.exists() or model_file.exists()) and not force:
            raise click.ClickException(f"Domain {name!r} already exists (use --force to overwrite).")

    for name in names:
        domain_dir = package_dir / "domain" / name
        model_file = package_dir / "db" / "models" / f"{name}.py"

        def render(text: str) -> str:
            return render_domain(text, package_dir.name, name)

        domain_dir.mkdir(parents=True, exist_ok=True)
        (domain_dir / "__init__.py").touch(exist_ok=True)
        copy_template(DOMAIN_TEMPLATE_DIR, domain_dir, render)
        model_file.parent.mkdir(parents=True, exist_ok=True)
        model_file.write_text(render(MODEL_TEMPLATE_FILE.read_text(encoding="utf-8")), encoding="utf-8")
        model_registered = register_model(package_dir, name)

        click.echo()
        click.secho("Domain created successfully", fg="green", bold=True)
        click.echo(f"  Domain:          {name}")
        click.echo(f"  Model:           {to_pascal(name)}")
        click.echo("  Components:      controller, service, dependencies, guards, schemas")
        click.echo(f"  Migration-ready: {'yes' if model_registered else 'no'}")



@click.group(name="cli", invoke_without_command=True, help="Manage your litestar-builder CLI")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Group for managing your litestar-builder CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(project)
cli.add_command(domain)

if __name__ == "__main__":
    cli()
