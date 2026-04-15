# Stacks

Preset bundles of elements, applied in one go.

## Format

One element per line. Lines starting with `#` are comments.

```
# my-stack.conf
@my-domain
skill:git-workflow
agent:reviewer
rule:code-style
```

## Usage

```bash
ai-dotfiles stack apply <name>
```
