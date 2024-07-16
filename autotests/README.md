# Autotests for FastMS Core

## Environment

```bash
python -m venv venv
source env/bin/activate
pip install -r requirements.txt
```

Optionally [Allure Report](https://github.com/allure-framework/allure2)
required. Look for `allure-commandline` package.

## Run tests

Start the FastMS system and optionally set `FASTMS_CORE_URL` environment
variable. Then run:

```bash
pytest -sv
```

## Generate Allure report


```bash
# Clean up old allure results
rm -rf allure-results/

# Run the tests and create allure result files
pytest --alluredir allure-results

# Serve the allure report.
# Allure commandline utilities required.
allure serve allure-results
```

## Troubleshooting

### Failed to run `allure`

Check that:
1. [Allure Report is installed](https://allurereport.org/docs/install/).
2. `java --version` gives reasonable output.
3. `allure` command is in path PATH environment variable.

Path may be extended with following command:

```bash
export PATH="$PATH:/path/to/allure/bin/"
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
