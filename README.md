# Salt.Box Core

This is Salt.Box backend repository.

To consult SLS package format look at [`sls_package.md`](./sls_package.md).

For common inner flows description consult with
[`common_flows.md`](./common_flows.md).

## Development

This project uses the following tools.

- [pytest](https://docs.pytest.org/) for writing tests
- [ruff](https://astral.sh/ruff) for Python source linting and formatting
- [mypy](https://mypy.readthedocs.io/en/stable/) for static type checking
- [pre-commit](https://pre-commit.com/) for Git hooks

### Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip3 install -e .[dev]  # pip install -e .\[dev\]  in some cases
```

After deploying dev environment install pre-commit hooks with
`pre-commit install` command.

### Verifying your setup

To verify that your setup is working, run the following commands:

```bash
SALTBOX_CORE_ENV_FILE=tests/test.env pytest
ruff check
mypy .
pre-commit run --all-files
```

If any of the above processes fail, please reach out to the project maintainers for support!

### Testing

To run tests use:

```bash
SALTBOX_CORE_ENV_FILE=tests/test.env pytest
```

### Run

To build the Core image:

```bash
sudo docker build --target=main --tag saltbox-core:dev .
```

Additional settings need to be passed as environment variables to start. Check
[`salt_box_core/config.py`](salt_box_core/config.py).

Use [Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose) repo to run the whole system.
