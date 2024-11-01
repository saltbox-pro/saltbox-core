# FastMS Core

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
sudo docker build --target=main --tag fastms-core .
```

Additional settings need to be passed as environment variables to start. Check
[fastms\_core/config.py](./fastms_core/config.py).

Use [FastMS Compose](https://gitlab.com/fastms/fastms-compose) repo to run
whole system.
