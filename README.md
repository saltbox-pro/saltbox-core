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

To run in developement mode:

```bash
# docker-compose up --buil --watch
```

`--build` flag rebuilds images, `--watch` flag rebuilds some images on src files
changes.
