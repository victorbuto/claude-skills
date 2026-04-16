# Claude Skills

Коллекция моих персональных скиллов для Claude Code — для стратегии, исследований, бренд-анализа и коммуникаций.

## Description

Скиллы расширяют возможности [Claude Code](https://claude.com/claude-code): задают воркфлоу, промпты для параллельных агентов, шаблоны итоговых документов. Каждый скилл — самодостаточный модуль с `SKILL.md` и опциональными `references/`, `scripts/`, `assets/`.

## Features

- `skills/brand-analysis` — глубокий разбор одного бренда (позиционирование, ToV, ЦА, RTB, консистентность коммуникации). Три параллельных агента собирают данные (сайт + соцсети + реклама через `erid`), затем синтез в итоговый файл.

## Установка скилла

Скопируй нужный скилл в папку скиллов Claude Code:

```bash
# глобально (все проекты)
cp -R skills/brand-analysis ~/.claude/skills/

# в конкретный проект
cp -R skills/brand-analysis /path/to/project/.claude/skills/
```

Или через симлинк — тогда правки в репо сразу видны в Claude Code:

```bash
ln -s "$(pwd)/skills/brand-analysis" ~/.claude/skills/brand-analysis
```

После установки перезапусти Claude Code, чтобы он увидел новый скилл.
