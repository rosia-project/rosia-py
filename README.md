# Rosia: Reproducible Robotic Middleware

<p align="left">
<a href="https://rosia.dev/"><b>Documentation</b></a> |
<a href="https://rosia.dev/docs/category/tutorial"><b>Tutorial</b></a> |
<a href="https://github.com/rosia-project/rosia-py/issues"><b>Issues</b></a> |
<a href="https://join.slack.com/t/rosia-group/shared_invite/zt-3txqtsyr5-ThEl4XFqwByigP7USkNJmw"><b>Join Slack</b></a> |
<a href="https://rosia.dev/blog"><b>Blog</b></a>
</p>

## Install
```bash
pip install rosia
```

Alternatively, you can install from source:

```bash
git clone https://github.com/rosia-project/rosia-py.git
cd rosia
pip install -e .
```

## Hello World


```python
from rosia import InputPort, OutputPort, reaction, Node, Application
from rosia import log

@Node
class Greeter:
    output = OutputPort[str]()
    def start(self):
        self.output("Hello, World!")

@Node
class Printer:
    message = InputPort[str]()
    @reaction([message])
    def print_message(self):
        log.info(self.message)

if __name__ == "__main__":
    app = Application()
    greeter = app.create_node(Greeter())
    printer = app.create_node(Printer())
    greeter.output >>= printer.message
    app.execute()
```

Please give us a star ⭐️ if you enjoyed Rosia! 

## Contributing
### Install Dev Dependencies
```bash
pip install --group dev .
```

### Install Pre-commit Hooks
```bash
pre-commit install --hook-type commit-msg --hook-type pre-push --hook-type pre-commit
pre-commit run --all-files
```
Code is automatically formatted before committing. Commit messages should follow conventional commit.

### Distribution Archives
```bash
python -m build
python -m twine upload dist/*
```