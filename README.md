# Litestar Builder

Litestar Builder creates Litestar projects and adds domain modules to projects using
the bundled template in `src/lst_builder/assets`.

## Why use Litestar Builder?

Starting a backend project often means repeatedly setting up the same
application structure, configuration, database integration, and feature-module
boilerplate before you can focus on your product. Litestar Builder automates
that setup by generating a ready-to-customize Litestar project from a
consistent template, including a `src`-based package layout and starter
application components.

The `lst-build domain` command extends a generated project with a feature
module's controller, schemas, service, dependencies, guards, and database
model. This gives new domains a consistent starting structure and avoids
manually creating and wiring those files each time. The generated code is
intended as a starting point that you can adapt; Litestar Builder does not
replace Litestar or make application-specific design decisions for you.

## Create a project

```console
lst-build project my-project
cd my-project
uv sync
```

The command creates `./my-project` by default. To use an existing or custom
directory as the project root, pass it as the second argument; files are created
directly in that directory:

```console
lst-build project my-project ./workspace
```

The generated project uses a `src/<package>` layout. The package name defaults to
the snake_case project name and can be set explicitly:

```console
lst-build project my-project --package my_app
```

## Generated project structure

A generated project uses a `src` layout. The package directory is named after
the selected package name (shown as `my_app` here):

```text
my-project/
├── .env.example
├── .gitignore
├── .python-version
├── README.md
├── pyproject.toml
├── uv.lock
└── src/
    └── my_app/
        ├── __main__.py
        ├── __metadata__.py
        ├── cli/
        ├── core/
        │   ├── server/
        │   ├── settings/
        │   └── utils/
        ├── db/
        │   ├── fixtures/
        │   ├── migrations/
        │   └── models/
        └── domain/
            └── accounts/
                ├── controller/
                ├── schemas/
                ├── services/
                ├── deps.py
                └── guards.py
```

- The project-root files contain package metadata and dependencies
  (`pyproject.toml`, `uv.lock`), Python-version and Git settings, and the
  template README and environment example.
- `__main__.py` starts the Litestar CLI. `core/server/` configures the
  application and its plugins, `core/settings/` holds application and
  infrastructure settings, and `core/utils/` contains shared helpers.
- `db/models/` holds SQLAlchemy models, `db/migrations/` contains Alembic
  configuration and migration history, and `db/fixtures/` is the location for
  fixture data.
- `domain/accounts/` is the starter account feature. Its controllers define
  routes, schemas describe request and response data, services hold business
  and persistence operations, `deps.py` provides injected dependencies, and
  `guards.py` contains route access checks.

The template's sample CRUD domain and sample model are not copied into a new
project. Add a feature domain with `lst-build domain inventory`; this creates
`src/my_app/domain/inventory/` with controller, schema, service, dependency,
and guard modules, plus `src/my_app/db/models/inventory.py`.

## Add a domain

Run the command from inside a generated project:

```console
lst-build domain inventory
```

Add multiple domains by separating their names with spaces:

```console
lst-build domain inventory billing notifications
```

The command creates a domain module under `<package>/domain/inventory` and a
matching database model under `<package>/db/models`. Controllers are discovered
by the generated project's domain plugin; the model is registered in
`db/models/__init__.py` for migration discovery.