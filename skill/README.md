# painpoint, as a Claude Code skill

`/painpoint <your idea>` — inside the tool you already have open.

## Install

```bash
git clone https://github.com/gokulsai1004-create/painpoint-finder.git
cp -r painpoint-finder/skill/painpoint ~/.claude/skills/
```

On Windows PowerShell:

```powershell
git clone https://github.com/gokulsai1004-create/painpoint-finder.git
Copy-Item -Recurse painpoint-finder\skill\painpoint $HOME\.claude\skills\
```

Then in Claude Code:

```
/painpoint i wanna build a tool that helps restaurant owners manage rotas
```

The first run clones the searcher next to the skill and checks for `requests`.
Everything after that is instant to start.

## Why a skill and not just the CLI

The CLI works, and it is the same code. The skill exists because the reading is
the hard part.

The output has a coverage line that must be read before the verdict, a verdict
that is a ratio and not a judgement, a competition section that usually matters
more than the leads, and a classifier that shows the words behind each call so
you can overrule it. A person skims past all of that and reads the leads. The
skill makes Claude read it in the right order and say the uncomfortable parts
out loud — that a partially blocked search proves nothing, that MODERATE is not
permission, that a competitor at 3,400 stars changes the plan.

It also refuses to send anything, same as the tool does.
