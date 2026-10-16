# Litestar Builder

Litestar Builder creates Litestar projects and adds domain modules to projects using
the bundled template in `src/litestar_builder/assets`.

## Create a project

```console
lst-builder project my-project
cd my-project
uv sync
```

The command creates `./my-project` by default. To use an existing or custom
directory as the project root, pass it as the second argument; files are created
directly in that directory:

```console
lst-builder project my-project ./workspace
```

The generated project uses a `src/<package>` layout. The package name defaults to
the snake_case project name and can be set explicitly:

```console
lst-builder project my-project --package my_app
```

## Add a domain

Run the command from inside a generated project:

```console
lst-builder domain inventory
```

The command creates a domain module under `<package>/domain/inventory` and a
matching database model under `<package>/db/models`. Controllers are discovered
by the generated project's domain plugin; the model is registered in
`db/models/__init__.py` for migration discovery.