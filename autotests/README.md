# Autotests for Salt.Box Core

## Environment

```bash
python -m venv venv
source env/bin/activate
pip install -r requirements.txt
```

## Run tests

Start the salt.box system and tune the `.env` file. Then run:

```bash
pytest -sv
```


### Missing `salt_box_core` modules

In order to solve the following issue:
```
ModuleNotFoundError: No module named 'salt_box_core'
```

install the Salt.Box Core as adviced in `README.md` or extend the `PYTHONPATH`:

```bash
export PYTHONPATH="$PYTHONPATH:/path/to/salt-box-core/"
```
