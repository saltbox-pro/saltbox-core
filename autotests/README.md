# Autotests for FastMS Core

## Environment

```bash
python -m venv venv
source env/bin/activate
pip install -r requirements.txt
```

## Run tests

Start the FastMS system and optionally set `FASTMS_CORE_URL` environment
variable. Then run:

```bash
pytest -sv
```


### Missing `fastms_core` modules

In order to solve the following issue:
```
ModuleNotFoundError: No module named 'fastms_core'
```

install the FastMS Core as adviced in `README.md` or extend the `PYTHONPATH`:

```bash
export PYTHONPATH="$PYTHONPATH:/path/to/fastms-core/"
```
