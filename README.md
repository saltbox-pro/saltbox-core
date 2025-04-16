# Salt.Box Core

## Developement

### Environment

```bash
python -m venv env
source env/bin/activate
pip3 install -e .[dev]
```

### pre-commit

After deploying dev enivronment install pre-commit hooks with
`pre-commit install` command.

### Run

To build the Core image:

```bash
sudo docker build --target=main --tag saltbox-core:dev .
```

Additional settings need to be passed as environment variables to start. Check
[`salt_box_core/config.py`](salt\_box\_core/config.py).

Use [Salt.Box Compose](https://gitlab.com/saltbox/saltbox-compose) repo to run
whole system.
